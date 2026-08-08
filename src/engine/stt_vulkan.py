import logging
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time

import numpy as np
import soundfile as sf

from src.config import APP_DIR, config_manager, get_resource_path
from src.engine.model_manager import model_manager
from src.engine.stt_base import BaseSTTEngine, TranscriptionCancelled
from src.i18n import translate

logger = logging.getLogger("PrimeDictate.STT_Vulkan")


class VulkanSTTEngine(BaseSTTEngine):
    """Runs an explicitly Vulkan-enabled whisper.cpp CLI build."""

    _status_cache_key = None
    _status_cache_value = None

    def __init__(self):
        self.executable = None
        self.model_path = None
        self.model_name = None
        self.last_inference_device = None
        self._runtime_verified_at = 0.0
        self._verified_executable = None

    def _ensure_runtime_available(self, executable: str, max_age_seconds: float = 30.0):
        now = time.monotonic()
        if (
            executable
            and executable == self._verified_executable
            and now - self._runtime_verified_at <= max_age_seconds
        ):
            return
        available, message = self.runtime_status(executable)
        if not available:
            raise RuntimeError(translate("vulkan.error.runtime_unavailable", detail=message))
        self._verified_executable = executable
        self._runtime_verified_at = now

    @staticmethod
    def find_executable():
        candidates = [
            config_manager.get("vulkan_executable", ""),
            os.path.join(APP_DIR, "runtime", "whisper-vulkan", "whisper-cli.exe"),
            get_resource_path(os.path.join("runtime", "whisper-vulkan", "whisper-cli.exe")),
            shutil.which("whisper-cli.exe"),
            shutil.which("whisper-cli"),
        ]
        return next(
            (os.path.abspath(path) for path in candidates if path and os.path.isfile(path)),
            None,
        )

    @classmethod
    def runtime_status(cls, candidate_path: str = None):
        executable = os.path.abspath(candidate_path) if candidate_path and os.path.isfile(candidate_path) else cls.find_executable()
        if not executable:
            return False, translate("vulkan.error.cli_missing")
        manifest_path = os.path.join(os.path.dirname(executable), "SHA256SUMS")
        cache_key = (
            executable,
            os.path.getmtime(executable),
            os.path.getmtime(manifest_path) if os.path.isfile(manifest_path) else None,
        )
        integrity_ok, integrity_message = cls._verify_integrity(executable)
        if not integrity_ok:
            return False, integrity_message
        if cache_key == cls._status_cache_key:
            return True, translate("vulkan.status.runtime_ready", device=cls._status_cache_value)
        try:
            result = subprocess.run(
                [executable, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw_output = result.stdout + result.stderr
            output = raw_output.lower()
            if "whisper" not in output or "--model" not in output:
                return False, translate("vulkan.error.incompatible_cli")
            if "ggml_vulkan" not in output or "vulkan devices" not in output:
                return False, translate("vulkan.error.backend_missing")
        except Exception as exc:
            return False, translate("vulkan.error.runtime_verification", detail=exc)
        device_match = re.search(r"ggml_vulkan:\s*0\s*=\s*([^\r\n|]+)", raw_output, re.IGNORECASE)
        device_name = device_match.group(1).strip() if device_match else "Vulkan GPU"
        cls._status_cache_key = cache_key
        cls._status_cache_value = device_name
        return True, translate("vulkan.status.runtime_ready", device=device_name)

    @staticmethod
    def _verify_integrity(executable: str):
        manifest_path = os.path.join(os.path.dirname(executable), "SHA256SUMS")
        if not os.path.isfile(manifest_path):
            return True, ""
        try:
            with open(manifest_path, "r", encoding="utf-8") as manifest:
                entries = [line.strip().split(maxsplit=1) for line in manifest if line.strip()]
            for expected_hash, filename in entries:
                file_path = os.path.join(os.path.dirname(executable), filename.strip())
                if not os.path.isfile(file_path):
                    return False, translate("vulkan.error.runtime_file_missing", file=filename.strip())
                digest = hashlib.sha256()
                with open(file_path, "rb") as runtime_file:
                    for block in iter(lambda: runtime_file.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest().casefold() != expected_hash.casefold():
                    return False, translate("vulkan.error.runtime_integrity", file=filename.strip())
        except (OSError, ValueError) as exc:
            return False, translate("vulkan.error.manifest", detail=exc)
        return True, ""

    def load_model(self, model_name: str = "base", language: str = "tr"):
        executable = self.find_executable()
        try:
            self._ensure_runtime_available(executable)
        except RuntimeError as error:
            raise RuntimeError(f"{error} {translate('vulkan.hint.select_runtime')}") from error

        model_path = model_manager.get_model_path(model_name, "vulkan")
        if not os.path.isfile(model_path):
            raise RuntimeError(
                f"{translate('vulkan.error.model_missing', model=model_name)} {translate('model.hint.download')}"
            )

        self.executable = executable
        self.model_path = model_path
        self.model_name = model_name

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr", cancel_check=None) -> str:
        if len(audio) == 0:
            return ""
        if not self.executable or not self.model_path:
            self.load_model(config_manager.get("model_size", "base"), language)
        else:
            self._ensure_runtime_available(self.executable)

        with tempfile.TemporaryDirectory(prefix="primedictate-vulkan-") as temp_dir:
            audio_path = os.path.join(temp_dir, "audio.wav")
            output_base = os.path.join(temp_dir, "transcript")
            sf.write(audio_path, audio.astype(np.float32, copy=False), sample_rate, format="WAV", subtype="PCM_16")

            command = [
                self.executable,
                "--model", self.model_path,
                "--file", audio_path,
                "--language", language if language != "auto" else "auto",
                "--output-txt",
                "--output-file", output_base,
                "--no-timestamps",
                "--beam-size", str(self._beam_size()),
                "--best-of", str(self._beam_size()),
            ]
            if cancel_check:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                while process.poll() is None:
                    if cancel_check():
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise TranscriptionCancelled()
                    time.sleep(0.1)
                stdout, stderr = process.communicate()
                result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            else:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            output_path = output_base + ".txt"
            if result.returncode != 0 or not os.path.isfile(output_path):
                detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else translate("error.unknown")
                raise RuntimeError(translate("vulkan.error.transcription", detail=detail))

            runtime_output = f"{result.stdout}\n{result.stderr}"
            device_match = re.search(r"ggml_vulkan:\s*0\s*=\s*([^\r\n|]+)", runtime_output, re.IGNORECASE)
            gpu_confirmed = re.search(r"using\s+Vulkan\d*\s+backend", runtime_output, re.IGNORECASE)
            if not gpu_confirmed:
                raise RuntimeError(translate("vulkan.error.gpu_unverified"))
            device_name = device_match.group(1).strip() if device_match else "Vulkan GPU"
            self.last_inference_device = f"Vulkan GPU • {device_name}"

            with open(output_path, "r", encoding="utf-8-sig") as output_file:
                text = output_file.read().strip()

        logger.info("Vulkan transcription completed on %s (%d characters).", self.last_inference_device, len(text))
        self.last_detected_language = None if language == "auto" else language
        self.last_language_probability = None
        return text

    @staticmethod
    def _beam_size() -> int:
        try:
            value = int(config_manager.get("vulkan_beam_size", 1))
        except (TypeError, ValueError):
            value = 1
        return max(1, min(5, value))
