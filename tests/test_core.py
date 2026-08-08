import json
import logging
import os
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf

from src.config import ConfigManager
from src.engine.ai_cleanup import AICleanupEngine, TextProcessingError
from src.engine.engine_manager import EngineManager
from src.engine.file_transcriber import FileTranscribeWorker, segments_to_json, segments_to_srt, segments_to_vtt
from src.engine.model_manager import ModelManager, supported_models
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.stt_cuda import CUDASTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.provider_catalog import ProviderCatalog
from src.engine.provider_transport import ProviderRequestCancelled, run_cancellable
from src.engine.hardware_capabilities import (
    BackendCapability, preferred_cuda_compute_types, recommended_local_backend,
)
from src.engine.stt_base import TranscriptionCancelled
from src.injector.paste_injector import PasteInjector
from src.operation_coordinator import OperationCoordinator
from src.audio.recorder import AudioRecorder
from src.audio.vad import is_audio_meaningful, trim_silence
from src.logging_config import SensitiveDataFilter
from src.diagnostics import create_diagnostics_bundle
from src.hotkey.listener import HotkeyListener, canonicalize_hotkey


class HotkeyListenerTests(unittest.TestCase):
    def test_sync_to_idle_clears_stale_key_state(self):
        listener = HotkeyListener()
        listener.is_recording = True
        listener.pressed_keys = {"ctrl", "v"}
        listener._combo_active = True

        listener.sync_recording_state(False)

        self.assertFalse(listener.is_recording)
        self.assertEqual(listener.pressed_keys, set())
        self.assertFalse(listener._combo_active)

    @staticmethod
    def _event(name, event_type):
        event = Mock()
        event.name = name
        event.event_type = event_type
        return event

    def test_hotkey_validation_requires_safe_complete_combination(self):
        self.assertEqual(canonicalize_hotkey("ALT + CTRL + D"), "ctrl+alt+d")
        self.assertEqual(canonicalize_hotkey("f8"), "f8")
        self.assertEqual(canonicalize_hotkey("d"), "")
        self.assertEqual(canonicalize_hotkey("ctrl+alt"), "")
        self.assertEqual(canonicalize_hotkey("ctrl+d+e"), "")

    def test_invalid_saved_hotkey_falls_back_to_safe_default(self):
        listener = HotkeyListener()
        with patch("src.hotkey.listener.config_manager.get", side_effect=["d", "invalid-mode"]), \
             patch("src.hotkey.listener.keyboard.hook", return_value=object()):
            self.assertTrue(listener.start_listening())
        self.assertEqual(listener.current_hotkey, "ctrl+alt+d")
        self.assertEqual(listener.current_mode, "toggle")

    def test_toggle_mode_ignores_key_repeat_and_toggles_after_release(self):
        started = Mock()
        stopped = Mock()
        listener = HotkeyListener(started, stopped)
        with patch("src.hotkey.listener.keyboard.hook", return_value=object()):
            self.assertTrue(listener.update_hotkey("ctrl+alt+d", "toggle"))

        for name in ("ctrl", "alt", "d", "d"):
            listener._on_keyboard_event(self._event(name, "down"))
        started.assert_called_once_with()
        stopped.assert_not_called()

        listener._on_keyboard_event(self._event("d", "up"))
        listener._on_keyboard_event(self._event("d", "down"))
        stopped.assert_called_once_with()

    def test_hold_mode_starts_on_complete_combo_and_stops_on_release(self):
        started = Mock()
        stopped = Mock()
        listener = HotkeyListener(started, stopped)
        with patch("src.hotkey.listener.keyboard.hook", return_value=object()):
            self.assertTrue(listener.update_hotkey("ctrl+shift+space", "hold"))

        for name in ("ctrl", "shift", "space"):
            listener._on_keyboard_event(self._event(name, "down"))
        started.assert_called_once_with()
        listener._on_keyboard_event(self._event("space", "up"))
        stopped.assert_called_once_with()


class LoggingSafetyTests(unittest.TestCase):
    def test_sensitive_filter_redacts_tokens_and_user_profile(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        record = logging.LogRecord(
            "PrimeDictate.Test",
            logging.ERROR,
            __file__,
            1,
            "api_key=%s Authorization: Bearer %s path=%s",
            (secret, secret, os.path.join(os.path.expanduser("~"), "private.wav")),
            None,
        )

        self.assertTrue(SensitiveDataFilter().filter(record))

        rendered = record.getMessage()
        self.assertNotIn(secret, rendered)
        self.assertNotIn(os.path.expanduser("~"), rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertIn("%USERPROFILE%", rendered)

    def test_diagnostics_bundle_excludes_secrets_history_and_transcripts(self):
        config = Mock()
        config.get.side_effect = lambda key, default=None: {
            "stt_backend": "vulkan",
            "model_size": "small",
            "api_key_openai": "must-not-appear",
        }.get(key, default)
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, "logs")
            os.makedirs(log_dir)
            with open(os.path.join(log_dir, "PrimeDictate.log"), "w", encoding="utf-8") as log_file:
                log_file.write(f"Authorization: Bearer {secret}\n")
            destination = os.path.join(temp_dir, "diagnostics.zip")

            create_diagnostics_bundle(destination, config, log_dir=log_dir)

            with zipfile.ZipFile(destination) as archive:
                report = json.loads(archive.read("diagnostics.json"))
                safe_log = archive.read("logs/PrimeDictate.log").decode("utf-8")
            self.assertNotIn(secret, safe_log)
            self.assertNotIn("api_key_openai", report["configuration"])
            self.assertFalse(report["privacy"]["contains_history"])
            self.assertFalse(report["privacy"]["contains_transcripts"])


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

    def test_failed_provider_can_return_raw_transcript_with_visible_metadata(self):
        engine = AICleanupEngine()
        values = {
            "ai_cleanup_enabled": True,
            "ai_cleanup_provider": "openai",
            "api_key_openai": "secret",
            "ai_model_openai": "cleanup-model",
            "cleanup_failure_policy": "raw",
        }
        with patch("src.engine.ai_cleanup.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.ai_cleanup.config_manager.get_effective_prompt", return_value="cleanup"), \
             patch.object(engine, "_clean_with_openai_compatible", return_value=None):
            result = engine.clean_text("ham metin")

        self.assertEqual(result, "ham metin")
        self.assertTrue(engine.last_processing_info["fallback_used"])
        self.assertEqual(engine.last_processing_info["fallback_policy"], "raw")

    def test_failed_provider_can_stop_processing(self):
        engine = AICleanupEngine()
        values = {
            "ai_cleanup_enabled": True,
            "ai_cleanup_provider": "openai",
            "api_key_openai": "secret",
            "ai_model_openai": "cleanup-model",
            "cleanup_failure_policy": "fail",
        }
        with patch("src.engine.ai_cleanup.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.ai_cleanup.config_manager.get_effective_prompt", return_value="cleanup"), \
             patch.object(engine, "_clean_with_openai_compatible", return_value=None):
            with self.assertRaises(TextProcessingError):
                engine.clean_text("ham metin")

        self.assertTrue(engine.last_processing_info["fallback_used"])
        self.assertEqual(engine.last_processing_info["fallback_policy"], "fail")


class OperationCoordinatorTests(unittest.TestCase):
    def test_only_one_transcription_operation_can_be_active(self):
        coordinator = OperationCoordinator()

        self.assertTrue(coordinator.try_begin("file_transcription"))
        self.assertFalse(coordinator.try_begin("dictation"))
        self.assertEqual(coordinator.active_operation, "file_transcription")

    def test_only_owner_can_finish_operation(self):
        coordinator = OperationCoordinator()
        coordinator.try_begin("dictation")

        self.assertFalse(coordinator.finish("file_transcription"))
        self.assertEqual(coordinator.active_operation, "dictation")
        self.assertTrue(coordinator.finish("dictation"))
        self.assertIsNone(coordinator.active_operation)


class AudioRecorderLimitTests(unittest.TestCase):
    def test_recording_limit_caps_buffer_and_notifies_once(self):
        recorder = AudioRecorder()
        recorder.is_recording = True
        recorder.max_samples = 5
        recorder.recorded_samples = 0
        recorder._limit_notified = False
        limit_callback = Mock()
        recorder.limit_callback = limit_callback

        recorder._audio_callback(np.ones((4, 1), dtype=np.float32), 4, None, None)
        recorder._audio_callback(np.ones((4, 1), dtype=np.float32), 4, None, None)
        recorder._audio_callback(np.ones((4, 1), dtype=np.float32), 4, None, None)

        self.assertEqual(recorder.recorded_samples, 5)
        self.assertEqual(sum(len(frame) for frame in recorder.frames), 5)
        limit_callback.assert_called_once_with()

    def test_finalizing_recording_releases_frame_references(self):
        recorder = AudioRecorder()
        recorder.is_recording = True
        recorder.native_sample_rate = 16000
        recorder.frames = [np.ones((3, 1), dtype=np.float32), np.ones((2, 1), dtype=np.float32)]

        result = recorder.stop_recording()

        self.assertEqual(len(result), 5)
        self.assertEqual(recorder.frames, [])

    def test_microphone_meter_uses_dbfs_scale(self):
        recorder = AudioRecorder()
        recorder.is_recording = True
        levels = []
        recorder.level_callback = levels.append

        recorder._audio_callback(np.full((320, 1), 0.01, dtype=np.float32), 320, None, None)

        self.assertEqual(len(levels), 1)
        self.assertGreater(levels[0], 0.30)
        self.assertLess(levels[0], 0.45)


class AdaptiveVADTests(unittest.TestCase):
    def test_speech_is_detected_over_steady_room_noise(self):
        rng = np.random.default_rng(42)
        noise_before = rng.normal(0, 0.0015, 6400).astype(np.float32)
        speech = (rng.normal(0, 0.0015, 6400) + 0.025 * np.sin(np.linspace(0, 80, 6400))).astype(np.float32)
        noise_after = rng.normal(0, 0.0015, 6400).astype(np.float32)

        trimmed = trim_silence(np.concatenate((noise_before, speech, noise_after)))

        self.assertTrue(is_audio_meaningful(trimmed))
        self.assertGreaterEqual(len(trimmed), len(speech))

    def test_quiet_speech_is_preserved_with_pre_and_post_roll(self):
        silence = np.zeros(6400, dtype=np.float32)
        speech = np.full(4800, 0.008, dtype=np.float32)
        audio = np.concatenate((silence, speech, silence))

        trimmed = trim_silence(audio)

        self.assertTrue(is_audio_meaningful(trimmed))
        self.assertGreaterEqual(len(trimmed), len(speech) + 6000)

    def test_short_command_is_accepted(self):
        audio = np.concatenate((
            np.zeros(1600, dtype=np.float32),
            np.full(4800, 0.03, dtype=np.float32),
            np.zeros(1600, dtype=np.float32),
        ))
        self.assertTrue(is_audio_meaningful(trim_silence(audio)))

    def test_single_impulse_is_rejected(self):
        audio = np.zeros(8000, dtype=np.float32)
        audio[4000:4100] = 0.9
        self.assertFalse(is_audio_meaningful(trim_silence(audio)))


class CloudSTTTests(unittest.TestCase):
    def test_gemini_error_body_is_not_exposed(self):
        values = {
            "cloud_stt_provider": "gemini",
            "stt_model_gemini": "stt-model",
            "api_key_gemini": "secret-key",
        }
        response = Mock(status_code=400, headers={})
        response.json.return_value = {"error": {"message": "secret-key private audio detail"}}
        engine = CloudSTTEngine()
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch.object(engine._session, "post", return_value=response), \
             self.assertLogs("PrimeDictate.STT_Cloud", level="WARNING") as logs:
            engine.transcribe(np.zeros(1600, dtype=np.float32))

        output = "\n".join(logs.output)
        self.assertNotIn("secret-key", output)
        self.assertNotIn("private audio detail", output)
        self.assertNotIn("secret-key", engine.last_error)

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
        engine = CloudSTTEngine()
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch.object(engine._session, "post", return_value=response) as post:
            result = engine.transcribe(np.zeros(1600, dtype=np.float32))

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

    def test_openai_client_is_reused_between_dictations(self):
        engine = CloudSTTEngine()
        client = Mock()
        client.audio.transcriptions.create.return_value = Mock(text="Merhaba")
        values = {
            "cloud_stt_provider": "openai",
            "stt_model_openai": "gpt-4o-mini-transcribe",
            "api_key_openai": "secret-api-key",
        }
        with patch("src.engine.stt_cloud.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("openai.OpenAI", return_value=client) as constructor:
            engine.transcribe(np.zeros(1600, dtype=np.float32))
            engine.transcribe(np.zeros(1600, dtype=np.float32))

        constructor.assert_called_once_with(api_key="secret-api-key", timeout=45, max_retries=0)
        self.assertEqual(client.audio.transcriptions.create.call_count, 2)

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
        self.assertNotIn("gsk_", engine.last_error.casefold())


class ProviderCatalogTests(unittest.TestCase):
    def test_gemini_key_is_sent_in_header_and_models_are_discovered(self):
        response = Mock(status_code=200)
        response.json.return_value = {"models": [{"name": "models/gemini-flash"}]}
        session = Mock()
        session.get.return_value = response

        result = ProviderCatalog(session=session).discover("gemini", "secret")

        self.assertTrue(result.ok)
        self.assertEqual(result.stt_models, ("gemini-flash",))
        self.assertNotIn("secret", session.get.call_args.args[0])
        self.assertEqual(session.get.call_args.kwargs["headers"]["x-goog-api-key"], "secret")
        self.assertEqual(session.get.call_args.kwargs["timeout"], (5, 15))

    def test_openai_catalog_separates_transcription_models(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [
            {"id": "gpt-4o-mini-transcribe"},
            {"id": "gpt-4o-mini"},
        ]}
        session = Mock()
        session.get.return_value = response

        result = ProviderCatalog(session=session).discover("openai", "secret")

        self.assertEqual(result.stt_models, ("gpt-4o-mini-transcribe",))
        self.assertEqual(result.text_models, ("gpt-4o-mini",))

    def test_provider_error_does_not_include_response_body_or_key(self):
        response = Mock(status_code=401, text="secret diagnostic body")
        session = Mock()
        session.get.return_value = response

        result = ProviderCatalog(session=session).discover("groq", "secret-key")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "http_401")
        self.assertEqual(result.failure.code, "authentication")
        self.assertEqual(result.failure.status_code, 401)
        self.assertNotIn("secret diagnostic body", repr(result.failure))
        self.assertNotIn("secret-key", repr(result.failure))


class ProviderTransportTests(unittest.TestCase):
    def test_waiting_provider_request_can_be_cancelled_promptly(self):
        release_request = threading.Event()
        cancel = threading.Event()
        timer = threading.Timer(0.05, cancel.set)
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(ProviderRequestCancelled):
                run_cancellable(lambda: release_request.wait(2), cancel.is_set, poll_seconds=0.01)
        finally:
            release_request.set()
            timer.cancel()
        self.assertLess(time.monotonic() - started, 0.5)


class CUDASTTTests(unittest.TestCase):
    def test_cuda_model_can_be_released_from_vram(self):
        engine = CUDASTTEngine()
        engine.model = Mock()
        engine.model_name = "base"
        engine.last_inference_device = "CUDA"

        with patch("src.engine.stt_cuda.gc.collect") as collect:
            engine.unload_model()

        self.assertFalse(engine.is_model_resident())
        self.assertIsNone(engine.model_name)
        self.assertIsNone(engine.last_inference_device)
        collect.assert_called_once_with()

    def test_cuda_compute_type_preference_uses_only_supported_types(self):
        result = preferred_cuda_compute_types({"int8", "float32", "int8_float16"})
        self.assertEqual(result, ("int8_float16", "int8", "float32"))

    def test_cuda_load_stops_before_model_creation_when_device_is_missing(self):
        engine = CUDASTTEngine()
        with patch("src.engine.stt_cuda.detect_cuda_backend", return_value=BackendCapability("cuda", False, "CUDA")), \
             patch("faster_whisper.WhisperModel") as whisper_model:
            with self.assertRaisesRegex(RuntimeError, "CUDA"):
                engine.load_model("base")
        whisper_model.assert_not_called()

    def test_cuda_load_tries_supported_compute_types_in_order(self):
        engine = CUDASTTEngine()
        model = Mock()
        with patch("src.engine.stt_cuda.detect_cuda_backend", return_value=BackendCapability("cuda", True, "GPU", "float16, int8")), \
             patch("src.engine.stt_cuda.model_manager.is_model_downloaded", return_value=True), \
             patch("src.engine.stt_cuda.model_manager.get_model_path", return_value="model"), \
             patch("faster_whisper.WhisperModel", side_effect=[RuntimeError("fp16"), model]) as whisper_model:
            engine.load_model("base")
        self.assertEqual([call.kwargs["compute_type"] for call in whisper_model.call_args_list], ["float16", "int8"])
        self.assertEqual(engine.last_inference_device, "NVIDIA CUDA GPU 0 • int8")

    def test_transcription_failure_is_raised_for_manager_fallback(self):
        engine = CUDASTTEngine()
        engine.model = Mock()
        engine.model.transcribe.side_effect = RuntimeError("CUDA failure")

        with self.assertRaisesRegex(RuntimeError, r"CUDA (transkripsiyonu başarısız|transcription failed)"):
            engine.transcribe(np.ones(1600, dtype=np.float32))


class VulkanSTTTests(unittest.TestCase):
    def test_vulkan_model_can_be_released_from_vram(self):
        engine = VulkanSTTEngine()
        engine._server_process = Mock()
        engine._server_process.poll.return_value = None
        self.assertTrue(engine.is_model_resident())

        with patch.object(engine, "_stop_server") as stop_server:
            engine.unload_model()

        stop_server.assert_called_once_with()

    def test_vulkan_engine_invokes_whisper_cli_with_selected_model(self):
        engine = VulkanSTTEngine()
        engine.executable = "whisper-cli.exe"
        engine.model_path = "ggml-base.bin"

        def complete_process(command, **_):
            output_base = command[command.index("--output-file") + 1]
            with open(output_base + ".txt", "w", encoding="utf-8") as output_file:
                output_file.write("Vulkan hazır")
            return Mock(
                returncode=0,
                stdout="",
                stderr="ggml_vulkan: 0 = Test AMD GPU | fp16: 1\nwhisper_backend_init_gpu: using Vulkan0 backend",
            )

        with patch.object(VulkanSTTEngine, "runtime_status", return_value=(True, "ready")), \
             patch("src.engine.stt_vulkan.subprocess.run", side_effect=complete_process) as run:
            result = engine.transcribe(np.zeros(1600, dtype=np.float32))

        command = run.call_args.args[0]
        self.assertEqual(result, "Vulkan hazır")
        self.assertEqual(engine.last_inference_device, "Vulkan GPU • Test AMD GPU")
        self.assertEqual(command[command.index("--model") + 1], "ggml-base.bin")
        self.assertIn("--no-timestamps", command)
        self.assertNotIn("--no-prints", command)
        self.assertEqual(command[command.index("--beam-size") + 1], "1")
        self.assertEqual(command[command.index("--best-of") + 1], "1")

    def test_vulkan_beam_size_is_sanitized(self):
        with patch("src.engine.stt_vulkan.config_manager.get", return_value=99):
            self.assertEqual(VulkanSTTEngine._beam_size(), 5)
        with patch("src.engine.stt_vulkan.config_manager.get", return_value="invalid"):
            self.assertEqual(VulkanSTTEngine._beam_size(), 1)

    def test_vulkan_reuses_recent_runtime_verification(self):
        engine = VulkanSTTEngine()
        with patch.object(VulkanSTTEngine, "runtime_status", return_value=(True, "ready")) as status:
            engine._ensure_runtime_available("whisper-cli.exe")
            engine._ensure_runtime_available("whisper-cli.exe")

        status.assert_called_once_with("whisper-cli.exe")

    def test_vulkan_rejects_unverified_cpu_fallback(self):
        engine = VulkanSTTEngine()
        engine.executable = "whisper-cli.exe"
        engine.model_path = "ggml-base.bin"

        def complete_without_gpu(command, **_):
            output_base = command[command.index("--output-file") + 1]
            with open(output_base + ".txt", "w", encoding="utf-8") as output_file:
                output_file.write("CPU sonucu")
            return Mock(returncode=0, stdout="", stderr="system_info: CPU only")

        with patch.object(VulkanSTTEngine, "runtime_status", return_value=(True, "ready")), \
             patch("src.engine.stt_vulkan.subprocess.run", side_effect=complete_without_gpu):
            with self.assertRaisesRegex(RuntimeError, "GPU"):
                engine.transcribe(np.zeros(1600, dtype=np.float32))

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
    def test_switching_to_cpu_releases_resident_gpu_models(self):
        manager = EngineManager()
        cuda_engine = Mock(model_name="base")
        vulkan_engine = Mock(model_name="small")
        manager.engines = {"cuda": cuda_engine, "vulkan": vulkan_engine}

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: {"stt_backend": "cpu", "model_size": "base"}.get(key, default)):
            manager.apply_stt_configuration("vulkan", "small")

        cuda_engine.unload_model.assert_called_once_with()
        vulkan_engine.unload_model.assert_called_once_with()

    def test_changing_vulkan_model_restarts_warmup_with_vram_released(self):
        manager = EngineManager()
        vulkan_engine = Mock(model_name="base")
        manager.engines = {"vulkan": vulkan_engine}

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: {"stt_backend": "vulkan", "model_size": "small"}.get(key, default)), \
             patch.object(manager, "start_warmup") as warmup:
            manager.apply_stt_configuration("vulkan", "base")

        vulkan_engine.unload_model.assert_called_once_with()
        warmup.assert_called_once_with()

    def test_backend_change_is_reconciled_again_after_active_warmup(self):
        manager = EngineManager()
        gpu_engine = Mock(model_name="base")
        manager.engines = {"vulkan": gpu_engine}
        active_warmup = Mock()
        active_warmup.is_alive.side_effect = [True, False]
        manager._warmup_thread = active_warmup

        values = {"stt_backend": "cpu", "model_size": "base"}
        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.engine_manager.threading.Thread") as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"]()
            manager.apply_stt_configuration("vulkan", "base")

        active_warmup.join.assert_called_once_with()
        self.assertEqual(gpu_engine.unload_model.call_count, 2)

    def test_text_processing_failure_never_reuploads_audio_as_stt_fallback(self):
        manager = EngineManager()
        local_engine = Mock()
        local_engine.transcribe.return_value = "ham metin"
        manager.get_engine = Mock(return_value=local_engine)
        values = {
            "stt_backend": "cpu",
            "model_size": "base",
            "language": "tr",
            "allow_cloud_fallback": True,
        }

        with patch("src.engine.engine_manager.config_manager.get", side_effect=lambda key, default=None: values.get(key, default)), \
             patch("src.engine.engine_manager.ai_cleanup_engine.clean_text", side_effect=TextProcessingError("cleanup failed")):
            with self.assertRaises(TextProcessingError):
                manager.process_audio(np.ones(1600, dtype=np.float32))

        manager.get_engine.assert_called_once_with("cpu")

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
        self.assertEqual(manager.last_transcription_info["audio_seconds"], 0.1)
        self.assertGreaterEqual(manager.last_transcription_info["transcription_seconds"], 0)
        self.assertGreaterEqual(manager.last_transcription_info["real_time_factor"], 0)


class FileDecodeTests(unittest.TestCase):
    def test_file_worker_uses_injected_engine(self):
        injected_engine = Mock()
        worker = FileTranscribeWorker("sample.wav", engine=injected_engine)
        self.assertIs(worker.engine, injected_engine)

    def test_audio_is_decoded_in_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "sample.wav")
            samples = np.zeros(33 * 16000, dtype=np.float32)
            sf.write(path, samples, 16000)

            worker = FileTranscribeWorker(path)
            chunks = list(worker._iter_audio_chunks())

        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0][0]), 30 * 16000)
        self.assertEqual(sum(len(chunk) for chunk, _ in chunks), len(samples) + worker.OVERLAP_SECONDS * 16000)
        self.assertTrue(all(10 <= progress <= 92 for _, progress in chunks))

    def test_overlap_text_is_deduplicated(self):
        merged = FileTranscribeWorker._merge_text_parts([
            "Bugün ürün planını ayrıntılı biçimde konuşacağız",
            "ayrıntılı biçimde konuşacağız ve görevleri paylaşacağız.",
        ])
        self.assertEqual(
            merged,
            "Bugün ürün planını ayrıntılı biçimde konuşacağız ve görevleri paylaşacağız.",
        )

    def test_timed_segments_remove_overlap_and_export_subtitles(self):
        worker = FileTranscribeWorker("sample.wav")
        segments = worker._build_segments(
            [
                "ilk bölüm ortak kelimeler",
                "ortak kelimeler ikinci bölüm",
            ],
            [30 * 16000, 4 * 16000],
        )

        self.assertEqual(segments[0], {"start": 0, "end": 30.0, "text": "ilk bölüm ortak kelimeler"})
        self.assertEqual(segments[1], {"start": 29, "end": 33.0, "text": "ikinci bölüm"})
        self.assertIn("00:00:29,000 --> 00:00:33,000", segments_to_srt(segments))
        self.assertTrue(segments_to_vtt(segments).startswith("WEBVTT\n"))
        self.assertIn('"text": "ikinci bölüm"', segments_to_json(segments))

    def test_file_cleanup_runs_once_after_all_stt_chunks(self):
        worker = FileTranscribeWorker("sample.wav")
        chunks = [(np.zeros(1600, dtype=np.float32), 40), (np.zeros(1600, dtype=np.float32), 80)]
        finished = []
        worker.completed.connect(lambda _, text: finished.append(text))

        with patch("src.engine.file_transcriber.os.path.exists", return_value=True), \
             patch("src.engine.file_transcriber.config_manager.get", return_value="tr"), \
             patch.object(worker, "_iter_audio_chunks", return_value=chunks), \
             patch("src.engine.file_transcriber.engine_manager.process_audio", side_effect=["ilk bölüm", "ikinci bölüm"]) as transcribe, \
             patch("src.engine.file_transcriber.engine_manager.process_text", return_value="tam metin") as cleanup:
            worker.run()

        self.assertEqual(transcribe.call_count, 2)
        self.assertTrue(all(call.kwargs["apply_text_processing"] is False for call in transcribe.call_args_list))
        cleanup.assert_called_once()
        self.assertEqual(cleanup.call_args.args, ("ilk bölüm ikinci bölüm",))
        self.assertTrue(callable(cleanup.call_args.kwargs["cancel_check"]))
        self.assertEqual(finished, ["tam metin"])

    def test_auto_language_is_locked_after_first_file_chunk(self):
        worker = FileTranscribeWorker("sample.wav")
        chunks = [
            (np.zeros(1600, dtype=np.float32), 40),
            (np.zeros(1600, dtype=np.float32), 80),
        ]
        language_overrides = []

        def process_audio(_, sample_rate=16000, language_override=None, cancel_check=None, apply_text_processing=True):
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

        def process_audio(_, sample_rate=16000, language_override=None, cancel_check=None, apply_text_processing=True):
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
        worker.completed.connect(lambda *_: finished.append(True))
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
    def test_backend_model_catalogs_are_independent(self):
        self.assertIn("large-v3", supported_models("cpu"))
        self.assertIn("large-v3", supported_models("cuda"))
        self.assertNotIn("large-v3", supported_models("vulkan"))
        self.assertTrue(supported_models("vulkan"))

    def test_faster_whisper_download_uses_prime_dictate_model_directory(self):
        manager = ModelManager()
        def create_model(_repo_id, local_dir, **_kwargs):
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                with open(os.path.join(local_dir, filename), "wb") as model_file:
                    model_file.write(b"test")

        with tempfile.TemporaryDirectory() as temp_dir, \
             patch.object(manager, "get_model_path", return_value=os.path.join(temp_dir, "base")) as model_path, \
             patch("huggingface_hub.snapshot_download", side_effect=create_model) as download, \
             patch.object(manager, "_validate_faster_whisper_model") as validate:
            manager._download_worker("base", "cpu")

        model_path.assert_called_once_with("base", "cpu")
        staging_path = download.call_args.kwargs["local_dir"]
        self.assertNotEqual(staging_path, os.path.join(temp_dir, "base"))
        validate.assert_called_once_with(staging_path)

    def test_failed_model_validation_preserves_existing_model(self):
        manager = ModelManager()
        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = os.path.join(temp_dir, "base")
            os.makedirs(model_path)
            marker = os.path.join(model_path, "existing.txt")
            with open(marker, "w", encoding="utf-8") as model_file:
                model_file.write("healthy")
            with patch.object(manager, "get_model_path", return_value=model_path), \
                 patch("huggingface_hub.snapshot_download"), \
                 patch.object(manager, "_validate_faster_whisper_model", side_effect=RuntimeError("invalid")):
                manager._download_worker("base", "cpu")
            self.assertTrue(os.path.isfile(marker))

    def test_zero_byte_model_file_is_not_ready(self):
        manager = ModelManager()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(manager, "get_model_path", return_value=temp_dir):
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                with open(os.path.join(temp_dir, filename), "wb") as model_file:
                    model_file.write(b"test")
            open(os.path.join(temp_dir, "model.bin"), "wb").close()
            self.assertFalse(manager.is_model_downloaded("base", "cpu"))

    def test_local_model_requires_complete_managed_files(self):
        manager = ModelManager()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(manager, "get_model_path", return_value=temp_dir):
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                with open(os.path.join(temp_dir, filename), "wb") as model_file:
                    model_file.write(b"test")
            self.assertTrue(manager.is_model_downloaded("base", "cpu"))
            os.remove(os.path.join(temp_dir, "model.bin"))
            self.assertFalse(manager.is_model_downloaded("base", "cpu"))


class HardwareCapabilityTests(unittest.TestCase):
    def test_recommendation_prefers_cuda_then_vulkan_then_cpu(self):
        cpu = BackendCapability("cpu", True, "CPU")
        vulkan = BackendCapability("vulkan", True, "AMD GPU")
        cuda = BackendCapability("cuda", True, "NVIDIA GPU")
        self.assertEqual(recommended_local_backend({"cpu": cpu, "vulkan": vulkan, "cuda": cuda}), "cuda")
        self.assertEqual(
            recommended_local_backend({"cpu": cpu, "vulkan": vulkan, "cuda": BackendCapability("cuda", False, "CUDA")}),
            "vulkan",
        )

    def test_recommendation_falls_back_to_cpu(self):
        capabilities = {
            "cpu": BackendCapability("cpu", True, "CPU"),
            "vulkan": BackendCapability("vulkan", False, "Vulkan"),
            "cuda": BackendCapability("cuda", False, "CUDA"),
        }
        self.assertEqual(recommended_local_backend(capabilities), "cpu")

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
    def test_auto_paste_disabled_copies_without_sending_paste_keys(self):
        injector = PasteInjector()
        with patch.object(injector, "_safe_copy_to_clipboard", return_value=True) as copy, \
             patch("src.injector.paste_injector.config_manager.get", return_value=False), \
             patch.object(injector, "_force_foreground") as force_foreground, \
             patch.object(injector, "_send_paste_keys") as send_paste_keys:
            pasted = injector.paste_text(
                "clipboard only",
                restore_clipboard=True,
                target_hwnd=10,
            )

        self.assertFalse(pasted)
        copy.assert_called_once_with("clipboard only")
        force_foreground.assert_not_called()
        send_paste_keys.assert_not_called()

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
