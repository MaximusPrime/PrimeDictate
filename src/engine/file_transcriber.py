import os
import logging
import soundfile as sf
import scipy.signal
import numpy as np
from PySide6.QtCore import QThread, Signal
from src.engine.engine_manager import engine_manager

logger = logging.getLogger("PrimeDictate.FileTranscriber")

class FileTranscribeWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str, str)  # (file_path, transcribed_text)
    error = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            if not os.path.exists(self.file_path):
                self.error.emit(f"Dosya bulunamadı: {self.file_path}")
                return

            self.progress.emit(15, "Ses dosyası okunuyor...")
            data, samplerate = sf.read(self.file_path, dtype='float32')

            # Convert stereo to mono if needed
            if data.ndim > 1:
                data = np.mean(data, axis=1)

            # Resample to 16000Hz for Whisper
            if samplerate != 16000:
                self.progress.emit(35, f"Frekans 16000Hz seviyesine dönüştürülüyor ({samplerate}Hz -> 16000Hz)...")
                num_samples = int(len(data) * 16000 / samplerate)
                data = scipy.signal.resample(data, num_samples).astype(np.float32)

            self.progress.emit(60, "Donanım hızlandırmalı motor ile metne dönüştürülüyor...")
            text = engine_manager.process_audio(data, sample_rate=16000)

            self.progress.emit(100, "Çeviri tamamlandı!")
            self.finished.emit(self.file_path, text)
        except Exception as e:
            logger.error(f"Error transcribing file {self.file_path}: {e}")
            self.error.emit(str(e))
