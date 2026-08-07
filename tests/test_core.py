import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf

from src.config import ConfigManager
from src.engine.ai_cleanup import AICleanupEngine
from src.engine.engine_manager import EngineManager
from src.engine.file_transcriber import FileTranscribeWorker
from src.engine.model_manager import ModelManager
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.stt_cuda import CUDASTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.stt_base import TranscriptionCancelled
from src.injector.paste_injector import PasteInjector


class CleanupTests(unittest.TestCase):
    def test_rule_cleanup_removes_fillers_and_adds_punctuation(self):
        result = AICleanupEngine()._clean_rule_based("ee yani bugün toplantıya gidelim")
        self.assertEqual(result, "Bugün toplantıya gidelim.")

    def test_rule_cleanup_handles_basic_english_fillers(self):
        result = AICleanupEngine()._clean_rule_based("um we should start the meeting")
        self.assertEqual(result, "We should start the meeting.")

    def test_cleanup_uses_its_own_provider_model(self):
        engine = AICleanupEngine()
        values = {
            "ai_cleanup_enabled": True,
            "ai_cleanup_provider": "openai",
            "api_key_openai": "secret",
            "ai_model_openai": "cleanup-model",
        }
        with patch("src.engine.ai_cleanup.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.ai_cleanup.config_manager.get_effective_prompt", return_value="cleanup"), \
             patch.object(engine, "_clean_with_openai_compatible", return_value="Düzenlendi.") as cleanup:
            result = engine.clean_text("ham metin")

        self.assertEqual(result, "Düzenlendi.")
        self.assertEqual(cleanup.call_args.args[3], "cleanup-model")

    def test_cleanup_exception_log_does_not_expose_secret_or_transcript(self):
        engine = AICleanupEngine()
        error = RuntimeError("secret-key and private transcript")
        error.status_code = 429
        with patch("src.engine.ai_cleanup.requests.post", side_effect=error), \
             self.assertLogs("PrimeDictate.AICleanup", level="ERROR") as logs:
            result = engine._clean_with_openai_compatible(
                "private transcript", "https://example.test/v1", "secret-key", "model", "prompt"
            )

        output = "\n".join(logs.output)
        self.assertIsNone(result)
        self.assertIn("http_status=429", output)
        self.assertNotIn("secret-key", output)
        self.assertNotIn("private transcript", output)


class CloudSTTTests(unittest.TestCase):
    def test_gemini_uses_independent_stt_model_and_header_key(self):
        values = {
            "cloud_stt_provider": "gemini",
            "stt_model_gemini": "stt-model",
            "api_key_gemini": "secret",
        }
        response = Mock(status_code=200)
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Merhaba dünya"}]}}]
        }
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.stt_cloud.requests.post", return_value=response) as post:
            result = CloudSTTEngine().transcribe(np.zeros(1600, dtype=np.float32))

        self.assertEqual(result, "Merhaba dünya")
        self.assertIn("/stt-model:generateContent", post.call_args.args[0])
        self.assertNotIn("secret", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "secret")

    def _transcribe_with_openai(self, model, language="tr", side_effect=None):
        values = {
            "cloud_stt_provider": "openai",
            "stt_model_openai": model,
            "api_key_openai": "secret-api-key",
        }
        client = Mock()
        client.audio.transcriptions.create.return_value = Mock(text="Merhaba")
        if side_effect is not None:
            client.audio.transcriptions.create.side_effect = side_effect
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("openai.OpenAI", return_value=client):
            result = CloudSTTEngine().transcribe(
                np.zeros(1600, dtype=np.float32), language=language
            )
        return result, client.audio.transcriptions.create

    def test_openai_existing_models_use_singular_language(self):
        for model in ("gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"):
            with self.subTest(model=model):
                result, create = self._transcribe_with_openai(model)
                self.assertEqual(result, "Merhaba")
                self.assertEqual(create.call_args.kwargs["language"], "tr")
                self.assertNotIn("extra_body", create.call_args.kwargs)

    def test_openai_gpt_transcribe_uses_languages_contract(self):
        result, create = self._transcribe_with_openai("gpt-transcribe")

        self.assertEqual(result, "Merhaba")
        self.assertNotIn("language", create.call_args.kwargs)
        self.assertEqual(create.call_args.kwargs["extra_body"], {"languages": ["tr"]})

    def test_openai_unknown_model_omits_language_hint(self):
        result, create = self._transcribe_with_openai("private-transcriber")

        self.assertEqual(result, "Merhaba")
        self.assertNotIn("language", create.call_args.kwargs)
        self.assertNotIn("extra_body", create.call_args.kwargs)

    def test_openai_exception_log_does_not_include_exception_message_or_key(self):
        error = RuntimeError("secret-api-key and raw audio bytes")
        error.status_code = 429
        error.request_id = "req-safe-id"

        with self.assertLogs("PrimeDictate.STT_Cloud", level="ERROR") as logs:
            result, _ = self._transcribe_with_openai("whisper-1", side_effect=error)

        output = "\n".join(logs.output)
        self.assertEqual(result, "")
        self.assertIn("http_status=429", output)
        self.assertIn("request_id=req-safe-id", output)
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("raw audio bytes", output)

    def test_missing_cloud_key_produces_safe_user_error(self):
        values = {"cloud_stt_provider": "groq", "stt_model_groq": "whisper-large-v3-turbo"}
        engine = CloudSTTEngine()
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)):
            result = engine.transcribe(np.zeros(1600, dtype=np.float32))

        self.assertEqual(result, "")
        self.assertIn("groq", engine.last_error.casefold())
        self.assertNotIn("key", engine.last_error.casefold())


class CUDASTTTests(unittest.TestCase):
    def test_transcription_failure_is_raised_for_manager_fallback(self):
        engine = CUDASTTEngine()
        engine.model = Mock()
        engine.model.transcribe.side_effect = RuntimeError("CUDA failure")

        with self.assertRaisesRegex(RuntimeError, "CUDA transkripsiyonu başarısız"):
            engine.transcribe(np.ones(1600, dtype=np.float32))


class VulkanSTTTests(unittest.TestCase):
    def test_vulkan_engine_invokes_whisper_cli_with_selected_model(self):
        engine = VulkanSTTEngine()
        engine.executable = "whisper-cli.exe"
        engine.model_path = "ggml-base.bin"

        def complete_process(command, **_):
            output_base = command[command.index("--output-file") + 1]
            with open(output_base + ".txt", "w", encoding="utf-8") as output_file:
                output_file.write("Vulkan hazır")
            return Mock(returncode=0, stderr="")

        with patch.object(VulkanSTTEngine, "runtime_status", return_value=(True, "ready")), \
             patch("src.engine.stt_vulkan.subprocess.run", side_effect=complete_process) as run:
            result = engine.transcribe(np.zeros(1600, dtype=np.float32))

        command = run.call_args.args[0]
        self.assertEqual(result, "Vulkan hazır")
        self.assertEqual(command[command.index("--model") + 1], "ggml-base.bin")
        self.assertIn("--no-timestamps", command)

    def test_cached_runtime_status_still_rechecks_integrity(self):
        executable = os.path.abspath("whisper-cli.exe")
        manifest = os.path.join(os.path.dirname(executable), "SHA256SUMS")
        VulkanSTTEngine._status_cache_key = (executable, 1, 2)
        VulkanSTTEngine._status_cache_value = "Test GPU"

        def modified_time(path):
            return 2 if path == manifest else 1

        with patch("src.engine.stt_vulkan.os.path.isfile", return_value=True), \
             patch("src.engine.stt_vulkan.os.path.getmtime", side_effect=modified_time), \
             patch.object(VulkanSTTEngine, "_verify_integrity", return_value=(True, "")) as verify:
            available, _ = VulkanSTTEngine.runtime_status(executable)

        self.assertTrue(available)
        verify.assert_called_once_with(executable)


class EngineFallbackTests(unittest.TestCase):
    def test_local_failure_does_not_upload_without_consent(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.load_model.side_effect = RuntimeError("local failure")
        manager.get_engine = Mock(return_value=local_engine)

        values = {
            "stt_backend": "cpu",
            "model_size": "base",
            "language": "tr",
            "allow_cloud_fallback": False,
        }
        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)):
            result = manager.process_audio(np.ones(16000, dtype=np.float32))

        self.assertEqual(result, "")
        manager.get_engine.assert_called_once_with("cpu")

    def test_invalid_language_falls_back_to_auto(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.transcribe.return_value = "metin"
        manager.get_engine = Mock(return_value=local_engine)
        values = {
            "stt_backend": "cpu",
            "model_size": "base",
            "language": "invalid-language",
        }

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.engine_manager.ai_cleanup_engine.clean_text", return_value="metin"), \
             self.assertLogs("PrimeDictate.EngineManager", level="WARNING") as logs:
            result = manager.process_audio(np.ones(1600, dtype=np.float32))

        self.assertEqual(result, "metin")
        local_engine.load_model.assert_called_once_with("base", "auto")
        self.assertEqual(local_engine.transcribe.call_args.kwargs["language"], "auto")
        self.assertIn("falling back to auto", "\n".join(logs.output))

    def test_transcription_exception_uses_approved_cloud_fallback(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.transcribe.side_effect = RuntimeError("CUDA transcription failed")
        cloud_engine = Mock()
        cloud_engine.transcribe.return_value = "bulut metni"
        manager.get_engine = Mock(side_effect=lambda backend: cloud_engine if backend == "cloud" else local_engine)
        values = {
            "stt_backend": "cuda",
            "model_size": "base",
            "language": "tr",
            "allow_cloud_fallback": True,
        }

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.engine_manager.ai_cleanup_engine.clean_text", return_value="temiz metin"):
            result = manager.process_audio(np.ones(1600, dtype=np.float32))

        self.assertEqual(result, "temiz metin")
        self.assertEqual(manager.get_engine.call_args_list[-1].args, ("cloud",))

    def test_cancellation_never_triggers_cloud_fallback(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.transcribe.side_effect = TranscriptionCancelled()
        manager.get_engine = Mock(return_value=local_engine)
        values = {
            "stt_backend": "cpu",
            "model_size": "base",
            "language": "tr",
            "allow_cloud_fallback": True,
        }

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)):
            with self.assertRaises(TranscriptionCancelled):
                manager.process_audio(np.ones(1600, dtype=np.float32), cancel_check=lambda: False)

        manager.get_engine.assert_called_once_with("cpu")

    def test_detected_language_metadata_is_exposed(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.transcribe.return_value = "hello"
        local_engine.last_detected_language = "en"
        local_engine.last_language_probability = 0.96
        manager.get_engine = Mock(return_value=local_engine)
        values = {"stt_backend": "cpu", "model_size": "base", "language": "auto"}

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.engine_manager.ai_cleanup_engine.clean_text", return_value="hello"):
            result = manager.process_audio(np.ones(1600, dtype=np.float32))

        self.assertEqual(result, "hello")
        self.assertEqual(manager.last_transcription_info["detected_language"], "en")
        self.assertEqual(manager.last_transcription_info["language_probability"], 0.96)


class FileDecodeTests(unittest.TestCase):
    def test_audio_is_decoded_in_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "sample.wav")
            samples = np.zeros(33 * 16000, dtype=np.float32)
            sf.write(path, samples, 16000)

            worker = FileTranscribeWorker(path)
            chunks = list(worker._iter_audio_chunks())

        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0][0]), 30 * 16000)
        self.assertEqual(sum(len(chunk) for chunk, _ in chunks), len(samples))
        self.assertTrue(all(10 <= progress <= 92 for _, progress in chunks))

    def test_auto_language_is_locked_after_first_file_chunk(self):
        worker = FileTranscribeWorker("sample.wav")
        chunks = [
            (np.zeros(1600, dtype=np.float32), 40),
            (np.zeros(1600, dtype=np.float32), 80),
        ]
        language_overrides = []

        def process_audio(_, sample_rate=16000, language_override=None, cancel_check=None):
            language_overrides.append(language_override)
            if len(language_overrides) == 1:
                from src.engine.engine_manager import engine_manager
                engine_manager.last_transcription_info = {
                    "detected_language": "en",
                    "language_probability": 0.92,
                }
            return "text"

        with patch("src.engine.file_transcriber.os.path.exists", return_value=True), \
             patch("src.engine.file_transcriber.config_manager.get", return_value="auto"), \
             patch.object(worker, "_iter_audio_chunks", return_value=chunks), \
             patch("src.engine.file_transcriber.engine_manager.process_audio", side_effect=process_audio):
            worker.run()

        self.assertEqual(language_overrides, [None, "en"])

    def test_auto_language_is_not_locked_on_low_confidence(self):
        worker = FileTranscribeWorker("sample.wav")
        chunks = [(np.zeros(1600, dtype=np.float32), 40), (np.zeros(1600, dtype=np.float32), 80)]
        language_overrides = []

        def process_audio(_, sample_rate=16000, language_override=None, cancel_check=None):
            language_overrides.append(language_override)
            from src.engine.engine_manager import engine_manager
            engine_manager.last_transcription_info = {
                "detected_language": "en",
                "language_probability": 0.40,
            }
            return "text"

        with patch("src.engine.file_transcriber.os.path.exists", return_value=True), \
             patch("src.engine.file_transcriber.config_manager.get", return_value="auto"), \
             patch.object(worker, "_iter_audio_chunks", return_value=chunks), \
             patch("src.engine.file_transcriber.engine_manager.process_audio", side_effect=process_audio):
            worker.run()

        self.assertEqual(language_overrides, [None, None])

    def test_decode_interruption_emits_cancelled_instead_of_partial_success(self):
        worker = FileTranscribeWorker("sample.wav")
        cancelled = []
        finished = []
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.finished.connect(lambda *_: finished.append(True))
        interrupted = {"value": False}

        def interrupted_chunks():
            yield np.zeros(1600, dtype=np.float32), 40
            interrupted["value"] = True

        with patch("src.engine.file_transcriber.os.path.exists", return_value=True), \
             patch("src.engine.file_transcriber.config_manager.get", return_value="tr"), \
             patch.object(worker, "isInterruptionRequested", side_effect=lambda: interrupted["value"]), \
             patch.object(worker, "_iter_audio_chunks", side_effect=interrupted_chunks), \
             patch("src.engine.file_transcriber.engine_manager.process_audio", return_value="partial"):
            worker.run()

        self.assertEqual(cancelled, [True])
        self.assertEqual(finished, [])


class ModelStorageTests(unittest.TestCase):
    def test_faster_whisper_download_uses_prime_dictate_model_directory(self):
        manager = ModelManager()
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch.object(manager, "get_model_path", return_value=os.path.join(temp_dir, "base")) as model_path, \
             patch("faster_whisper.utils.download_model") as download:
            manager._download_worker("base", "cpu")

        model_path.assert_called_once_with("base", "cpu")
        self.assertEqual(download.call_args.kwargs["output_dir"], os.path.join(temp_dir, "base"))

    def test_local_model_requires_complete_managed_files(self):
        manager = ModelManager()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(manager, "get_model_path", return_value=temp_dir):
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                with open(os.path.join(temp_dir, filename), "wb") as model_file:
                    model_file.write(b"test")
            self.assertTrue(manager.is_model_downloaded("base", "cpu"))
            os.remove(os.path.join(temp_dir, "model.bin"))
            self.assertFalse(manager.is_model_downloaded("base", "cpu"))


class ConfigTests(unittest.TestCase):
    def test_api_credentials_are_not_written_to_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with patch("src.config.APP_DIR", temp_dir), patch("src.config.CONFIG_PATH", config_path), patch.object(ConfigManager, "_migrate_legacy_settings"):
                manager = ConfigManager()
                with patch.object(manager, "_write_secret"):
                    manager.update({"api_key_openai": "test-only-key", "language": "en"})

            with open(config_path, "r", encoding="utf-8") as config_file:
                saved = json.load(config_file)

        self.assertNotIn("api_key_openai", saved)
        self.assertEqual(saved["language"], "en")


class PasteSafetyTests(unittest.TestCase):
    def test_paste_is_skipped_when_target_focus_cannot_be_restored(self):
        injector = PasteInjector()
        with patch("src.injector.paste_injector.pyperclip.copy"), \
             patch("src.injector.paste_injector.pyperclip.paste", return_value="old"), \
             patch("src.injector.paste_injector.win32gui.IsWindow", return_value=True), \
             patch("src.injector.paste_injector.win32gui.SetForegroundWindow"), \
             patch("src.injector.paste_injector.win32gui.GetForegroundWindow", return_value=20), \
             patch("src.injector.paste_injector.win32gui.GetWindowText", return_value="Target"), \
             patch("src.injector.paste_injector.win32process.GetWindowThreadProcessId", return_value=(1, 2)), \
             patch("src.injector.paste_injector.config_manager.get", return_value=True), \
             patch("src.injector.paste_injector.keyboard.send") as send:
            pasted = injector.paste_text("safe text", restore_clipboard=True, target_hwnd=10)

        self.assertFalse(pasted)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
