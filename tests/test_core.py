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
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.injector.paste_injector import PasteInjector


class CleanupTests(unittest.TestCase):
    def test_rule_cleanup_removes_fillers_and_adds_punctuation(self):
        result = AICleanupEngine()._clean_rule_based("ee yani bugün toplantıya gidelim")
        self.assertEqual(result, "Bugün toplantıya gidelim.")

    def test_cleanup_uses_its_own_provider_model(self):
        engine = AICleanupEngine()
        values = {
            "ai_cleanup_enabled": True,
            "operation_mode": "dictation",
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

        with patch("src.engine.stt_vulkan.subprocess.run", side_effect=complete_process) as run:
            result = engine.transcribe(np.zeros(1600, dtype=np.float32))

        command = run.call_args.args[0]
        self.assertEqual(result, "Vulkan hazır")
        self.assertEqual(command[command.index("--model") + 1], "ggml-base.bin")
        self.assertIn("--no-timestamps", command)


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
