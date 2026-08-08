import os
import shutil
import tempfile
import threading
import logging
import requests
from src.i18n import translate
from PySide6.QtCore import QObject, Signal
from src.config import APP_DIR

logger = logging.getLogger("PrimeDictate.ModelManager")

VULKAN_MODEL_FILES = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large-v3-turbo": "ggml-large-v3-turbo.bin",
}
VULKAN_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VULKAN_MODEL_DIR = os.path.join(APP_DIR, "models", "whisper.cpp")
FASTER_WHISPER_MODEL_DIR = os.path.join(APP_DIR, "models", "faster-whisper")
FASTER_WHISPER_MODEL_NAMES = frozenset({
    "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3",
})


def supported_models(backend: str) -> frozenset[str]:
    if backend == "vulkan":
        return frozenset(VULKAN_MODEL_FILES)
    if backend in {"cpu", "cuda"}:
        return FASTER_WHISPER_MODEL_NAMES
    return frozenset()

class ModelManager(QObject):
    progress = Signal(int, str)  # percentage (0-100), status message
    download_finished = Signal(str, str, bool, str)  # backend, model_name, success, error_msg

    def __init__(self):
        super().__init__()
        self._is_downloading = False
        self._download_lock = threading.Lock()

    def get_model_path(self, model_name: str, backend: str):
        if model_name not in supported_models(backend):
            raise ValueError(f"Desteklenmeyen model: {model_name}")
        if backend == "vulkan":
            filename = VULKAN_MODEL_FILES.get(model_name)
            return os.path.join(VULKAN_MODEL_DIR, filename)
        return os.path.join(FASTER_WHISPER_MODEL_DIR, model_name)

    def is_model_downloaded(self, model_name: str, backend: str = "cpu") -> bool:
        if backend == "vulkan":
            try:
                path = self.get_model_path(model_name, backend)
                return os.path.isfile(path) and os.path.getsize(path) > 1024 * 1024
            except ValueError:
                return False
        try:
            model_path = self.get_model_path(model_name, backend)
            required_files = ("config.json", "model.bin", "tokenizer.json")
            return all(
                os.path.isfile(os.path.join(model_path, filename))
                and os.path.getsize(os.path.join(model_path, filename)) > 0
                for filename in required_files
            )
        except (OSError, ValueError):
            return False

    def download_model_async(self, model_name: str, backend: str = "cpu"):
        with self._download_lock:
            if self._is_downloading:
                return False
            self._is_downloading = True
        threading.Thread(target=self._download_worker, args=(model_name, backend), daemon=True).start()
        return True

    def _download_worker(self, model_name: str, backend: str):
        logger.info("Starting download for model '%s' (%s).", model_name, backend)
        self.progress.emit(-1, translate("model.progress.downloading", model=model_name))

        try:
            if backend == "vulkan":
                self._download_vulkan_model(model_name)
            else:
                self._download_faster_whisper_model(model_name, backend)
            
            self.progress.emit(100, translate("model.progress.ready", model=model_name))
            self.download_finished.emit(backend, model_name, True, "")
        except Exception as e:
            logger.error(f"Failed to download model '{model_name}': {e}")
            self.progress.emit(0, translate("model.error.download", detail=e))
            self.download_finished.emit(backend, model_name, False, str(e))
        finally:
            with self._download_lock:
                self._is_downloading = False

    def _download_faster_whisper_model(self, model_name: str, backend: str):
        from faster_whisper.utils import _MODELS
        from huggingface_hub import snapshot_download
        from tqdm.auto import tqdm

        self.progress.emit(-1, translate("model.progress.connecting_huggingface", model=model_name))
        model_path = self.get_model_path(model_name, backend)
        parent_dir = os.path.dirname(model_path)
        os.makedirs(parent_dir, exist_ok=True)
        staging_path = tempfile.mkdtemp(prefix=f".{model_name}-", suffix=".download", dir=parent_dir)
        backup_path = None
        try:
            manager = self

            class DownloadProgress(tqdm):
                """Forward Hugging Face model-file progress to the Qt UI."""

                def __init__(self, *args, **kwargs):
                    kwargs["disable"] = True
                    super().__init__(*args, **kwargs)
                    self._prime_downloaded = self.n

                def update(self, amount=1):
                    displayed = super().update(amount)
                    self._prime_downloaded += amount
                    if self.total and self.total > 1024 * 1024:
                        percent = min(99, int(self._prime_downloaded * 100 / self.total))
                        manager.progress.emit(
                            percent,
                            translate("model.progress.downloading_percent", model=model_name, percent=percent),
                        )
                    return displayed

            snapshot_download(
                _MODELS.get(model_name, model_name),
                local_dir=staging_path,
                allow_patterns=(
                    "config.json", "preprocessor_config.json", "model.bin",
                    "tokenizer.json", "vocabulary.*",
                ),
                tqdm_class=DownloadProgress,
            )
            self._validate_faster_whisper_model(staging_path)
            if os.path.exists(model_path):
                backup_path = tempfile.mkdtemp(prefix=f".{model_name}-", suffix=".backup", dir=parent_dir)
                os.rmdir(backup_path)
                os.replace(model_path, backup_path)
            try:
                os.replace(staging_path, model_path)
            except Exception:
                if backup_path and os.path.exists(backup_path) and not os.path.exists(model_path):
                    os.replace(backup_path, model_path)
                raise
            if backup_path and os.path.exists(backup_path):
                shutil.rmtree(backup_path)
        finally:
            if os.path.exists(staging_path):
                shutil.rmtree(staging_path, ignore_errors=True)

    @staticmethod
    def _validate_faster_whisper_model(model_path: str):
        required_files = ("config.json", "model.bin", "tokenizer.json")
        missing = [
            filename for filename in required_files
            if not os.path.isfile(os.path.join(model_path, filename))
            or os.path.getsize(os.path.join(model_path, filename)) <= 0
        ]
        if missing:
            raise RuntimeError(translate("model.error.incomplete", files=", ".join(missing)))
        from faster_whisper import WhisperModel
        WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=1)

    def _download_vulkan_model(self, model_name: str):
        target_path = self.get_model_path(model_name, "vulkan")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        partial_path = target_path + ".part"
        url = f"{VULKAN_MODEL_BASE_URL}/{os.path.basename(target_path)}"

        try:
            with requests.get(url, stream=True, timeout=(10, 60)) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(partial_path, "wb") as model_file:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if not block:
                            continue
                        model_file.write(block)
                        downloaded += len(block)
                        if total_size:
                            percent = min(99, int(downloaded * 100 / total_size))
                            self.progress.emit(percent, translate("model.progress.downloading_vulkan", percent=percent))
            if os.path.getsize(partial_path) <= 1024 * 1024:
                raise RuntimeError(translate("model.error.invalid_vulkan_file"))
            os.replace(partial_path, target_path)
        except Exception:
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                except OSError:
                    pass
            raise

model_manager = ModelManager()
