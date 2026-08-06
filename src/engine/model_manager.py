import os
import threading
import logging
import requests
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

class ModelManager(QObject):
    progress = Signal(int, str)  # percentage (0-100), status message
    download_finished = Signal(str, str, bool, str)  # backend, model_name, success, error_msg

    def __init__(self):
        super().__init__()
        self._is_downloading = False

    def get_model_path(self, model_name: str, backend: str):
        if backend == "vulkan":
            filename = VULKAN_MODEL_FILES.get(model_name)
            if not filename:
                raise ValueError(f"Vulkan için desteklenmeyen model: {model_name}")
            return os.path.join(VULKAN_MODEL_DIR, filename)
        return ""

    def is_model_downloaded(self, model_name: str, backend: str = "cpu") -> bool:
        if backend == "vulkan":
            try:
                return os.path.isfile(self.get_model_path(model_name, backend))
            except ValueError:
                return False
        try:
            from faster_whisper.utils import download_model
            model_path = download_model(model_name, local_files_only=True)
            return os.path.isdir(model_path)
        except Exception:
            return False

    def download_model_async(self, model_name: str, backend: str = "cpu"):
        if self._is_downloading:
            return
        self._is_downloading = True
        threading.Thread(target=self._download_worker, args=(model_name, backend), daemon=True).start()

    def _download_worker(self, model_name: str, backend: str):
        logger.info("Starting download for model '%s' (%s).", model_name, backend)
        self.progress.emit(-1, f"Model dosyası indiriliyor: {model_name}...")

        try:
            if backend == "vulkan":
                self._download_vulkan_model(model_name)
            else:
                from faster_whisper.utils import download_model
                self.progress.emit(-1, f"HuggingFace sunucusuna bağlanılıyor ({model_name})...")
                download_model(model_name)
            
            self.progress.emit(100, f"Model '{model_name}' başarıyla yüklendi ve hazır.")
            self.download_finished.emit(backend, model_name, True, "")
        except Exception as e:
            logger.error(f"Failed to download model '{model_name}': {e}")
            self.progress.emit(0, f"İndirme hatası: {e}")
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
                            self.progress.emit(percent, f"Vulkan modeli indiriliyor: %{percent}")
            os.replace(partial_path, target_path)
        except Exception:
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                except OSError:
                    pass
            raise

model_manager = ModelManager()
