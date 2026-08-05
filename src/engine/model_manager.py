import os
import threading
import logging
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("PrimeDictate.ModelManager")

# HuggingFace repository IDs for faster-whisper models
MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "turbo": "deepdml/faster-whisper-large-v3-turbo"
}

class ModelManager(QObject):
    progress = Signal(int, str)  # percentage (0-100), status message
    download_finished = Signal(str, bool, str)  # model_name, success, error_msg

    def __init__(self):
        super().__init__()
        self._is_downloading = False

    def is_model_downloaded(self, model_name: str) -> bool:
        try:
            from huggingface_hub import try_to_load_from_cache
            repo_id = MODEL_REPOS.get(model_name, f"Systran/faster-whisper-{model_name}")
            filepath = try_to_load_from_cache(repo_id, "model.bin")
            return isinstance(filepath, str) and os.path.exists(filepath)
        except Exception:
            return False

    def download_model_async(self, model_name: str):
        if self._is_downloading:
            return
        self._is_downloading = True
        threading.Thread(target=self._download_worker, args=(model_name,), daemon=True).start()

    def _download_worker(self, model_name: str):
        repo_id = MODEL_REPOS.get(model_name, f"Systran/faster-whisper-{model_name}")
        logger.info(f"Starting download for model '{model_name}' ({repo_id})...")
        self.progress.emit(10, f"Model dosyası indiriliyor: {model_name}...")

        try:
            from huggingface_hub import snapshot_download
            self.progress.emit(30, f"HuggingFace sunucularına bağlanılıyor ({model_name})...")
            
            snapshot_download(repo_id=repo_id)
            
            self.progress.emit(100, f"Model '{model_name}' başarıyla yüklendi ve hazır.")
            self.download_finished.emit(model_name, True, "")
        except Exception as e:
            logger.error(f"Failed to download model '{model_name}': {e}")
            self.progress.emit(0, f"İndirme hatası: {e}")
            self.download_finished.emit(model_name, False, str(e))
        finally:
            self._is_downloading = False

model_manager = ModelManager()
