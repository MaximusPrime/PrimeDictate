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
from src.i18n import t

logger = logging.getLogger("PrimeDictate.STT_Vulkan")


class VulkanSTTEngine(BaseSTTEngine):
    """Runs an explicitly Vulkan-enabled whisper.cpp CLI build."""

    _status_cache_key = None
    _status_cache_value = None

    def __init__(self):
        self.executable = None
        self.model_path = None
        self.model_name = None

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
            return False, t("Vulkan özellikli whisper-cli bulunamadı.")
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
            return True, f"{t('Dahili Vulkan runtime hazır')} • {cls._status_cache_value}"
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
                return False, t("Seçilen dosya uyumlu bir whisper.cpp CLI değil.")
            if "ggml_vulkan" not in output or "vulkan devices" not in output:
                return False, t("Seçilen whisper.cpp runtime Vulkan backend içermiyor.")
        except Exception as exc:
            return False, f"{t('Vulkan runtime doğrulanamadı')}: {exc}"
        device_match = re.search(r"ggml_vulkan:\s*0\s*=\s*([^\r\n|]+)", raw_output, re.IGNORECASE)
        device_name = device_match.group(1).strip() if device_match else "Vulkan GPU"
        cls._status_cache_key = cache_key
        cls._status_cache_value = device_name
        return True, f"{t('Dahili Vulkan runtime hazır')} • {device_name}"

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
                    return False, f"{t('Vulkan runtime eksik dosya içeriyor')}: {filename.strip()}"
                digest = hashlib.sha256()
                with open(file_path, "rb") as runtime_file:
                    for block in iter(lambda: runtime_file.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest().casefold() != expected_hash.casefold():
                    return False, f"{t('Vulkan runtime bütünlük kontrolü başarısız')}: {filename.strip()}"
        except (OSError, ValueError) as exc:
            return False, f"{t('Vulkan runtime manifesti okunamadı')}: {exc}"
        return True, ""

    def load_model(self, model_name: str = "base", language: str = "tr"):
        executable = self.find_executable()
        available, message = self.runtime_status(executable)
        if not available:
            raise RuntimeError(
                f"{t('Vulkan runtime kullanılamıyor')}: {message} {t('Motor ayarlarından uyumlu dosyayı seçin.')}"
            )

        model_path = model_manager.get_model_path(model_name, "vulkan")
        if not os.path.isfile(model_path):
            raise RuntimeError(
                f"{t('Vulkan Whisper modeli yüklü değil')}: {model_name}. {t('Model yöneticisinden indirin.')}"
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
            available, message = self.runtime_status(self.executable)
            if not available:
                raise RuntimeError(f"{t('Vulkan runtime kullanılamıyor')}: {message}")

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
                "--no-prints",
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
                detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else t("bilinmeyen hata")
                raise RuntimeError(f"{t('Vulkan transkripsiyonu başarısız')}: {detail}")

            with open(output_path, "r", encoding="utf-8-sig") as output_file:
                text = output_file.read().strip()

        logger.info("Vulkan transcription completed (%d characters).", len(text))
        self.last_detected_language = None if language == "auto" else language
        self.last_language_probability = None
        return text
