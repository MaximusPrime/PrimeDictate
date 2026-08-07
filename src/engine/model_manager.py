import os
import threading
import logging
import requests
from src.i18n import t
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
SUPPORTED_MODEL_NAMES = frozenset(VULKAN_MODEL_FILES)

class ModelManager(QObject):
    progress = Signal(int, str)  # percentage (0-100), status message
    download_finished = Signal(str, str, bool, str)  # backend, model_name, success, error_msg

    def __init__(self):
        super().__init__()
        self._is_downloading = False

    def get_model_path(self, model_name: str, backend: str):
        if model_name not in SUPPORTED_MODEL_NAMES:
            raise ValueError(f"Desteklenmeyen model: {model_name}")
        if backend == "vulkan":
            filename = VULKAN_MODEL_FILES.get(model_name)
            return os.path.join(VULKAN_MODEL_DIR, filename)
        return os.path.join(FASTER_WHISPER_MODEL_DIR, model_name)

    def is_model_downloaded(self, model_name: str, backend: str = "cpu") -> bool:
        if backend == "vulkan":
            try:
                return os.path.isfile(self.get_model_path(model_name, backend))
            except ValueError:
                return False
        try:
            model_path = self.get_model_path(model_name, backend)
            required_files = ("config.json", "model.bin", "tokenizer.json")
            return all(os.path.isfile(os.path.join(model_path, filename)) for filename in required_files)
        except (OSError, ValueError):
            return False

    def download_model_async(self, model_name: str, backend: str = "cpu"):
        if self._is_downloading:
            return
        self._is_downloading = True
        threading.Thread(target=self._download_worker, args=(model_name, backend), daemon=True).start()

    def _download_worker(self, model_name: str, backend: str):
        logger.info("Starting download for model '%s' (%s).", model_name, backend)
        self.progress.emit(-1, f"{t('Model dosyası indiriliyor')}: {model_name}...")

        try:
            if backend == "vulkan":
                self._download_vulkan_model(model_name)
            else:
                from faster_whisper.utils import download_model
                self.progress.emit(-1, f"{t('HuggingFace sunucusuna bağlanılıyor')} ({model_name})...")
                model_path = self.get_model_path(model_name, backend)
                os.makedirs(model_path, exist_ok=True)
                download_model(model_name, output_dir=model_path)
            
            self.progress.emit(100, t("Model '{model}' başarıyla yüklendi ve hazır.").format(model=model_name))
            self.download_finished.emit(backend, model_name, True, "")
        except Exception as e:
            logger.error(f"Failed to download model '{model_name}': {e}")
            self.progress.emit(0, f"{t('İndirme hatası')}: {e}")
            self.download_finished.emit(backend, model_name, False, str(e))
        finally:
            self._is_downloading = False

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
                            self.progress.emit(percent, f"{t('Vulkan modeli indiriliyor')}: %{percent}")
            os.replace(partial_path, target_path)
        except Exception:
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                except OSError:
                    pass
            raise

model_manager = ModelManager()
