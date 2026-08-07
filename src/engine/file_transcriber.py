import os
import logging
import av
import numpy as np
from PySide6.QtCore import QThread, Signal
from src.engine.engine_manager import engine_manager
from src.config import config_manager
from src.i18n import t
from src.engine.stt_base import TranscriptionCancelled

logger = logging.getLogger("PrimeDictate.FileTranscriber")

class FileTranscribeWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str, str)  # (file_path, transcribed_text)
    error = Signal(str)
    cancelled = Signal()

    CHUNK_SECONDS = 30
    TARGET_SAMPLE_RATE = 16000
    MIN_LANGUAGE_CONFIDENCE = 0.60

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            if not os.path.exists(self.file_path):
                self.error.emit(f"{t('Dosya bulunamadı')}: {self.file_path}")
                return

            self.progress.emit(5, t("Medya akışı hazırlanıyor..."))
            text_parts = []
            configured_language = config_manager.get("language", "tr")
            detected_language = None
            for chunk, percent in self._iter_audio_chunks():
                if self.isInterruptionRequested():
                    self.cancelled.emit()
                    return
                self.progress.emit(percent, t("Ses parçası metne dönüştürülüyor..."))
                language_override = detected_language if configured_language == "auto" else None
                text = engine_manager.process_audio(
                    chunk,
                    sample_rate=self.TARGET_SAMPLE_RATE,
                    language_override=language_override,
                    cancel_check=self.isInterruptionRequested,
                )
                if configured_language == "auto" and detected_language is None:
                    info = engine_manager.last_transcription_info
                    candidate_language = info.get("detected_language")
                    confidence = info.get("language_probability")
                    if candidate_language and isinstance(confidence, (float, int)) and confidence >= self.MIN_LANGUAGE_CONFIDENCE:
                        detected_language = candidate_language
                        logger.info("File language locked to '%s' after the first chunk.", detected_language)
                if text:
                    text_parts.append(text)

            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            text = "\n\n".join(text_parts).strip()
            if not text:
                raise RuntimeError(t("Dosyada konuşma algılanamadı veya seçili motor yanıt vermedi."))

            self.progress.emit(100, t("Çeviri tamamlandı!"))
            self.finished.emit(self.file_path, text)
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as e:
            logger.error(f"Error transcribing file {self.file_path}: {e}")
            self.error.emit(str(e))

    def _iter_audio_chunks(self):
        chunk_size = self.CHUNK_SECONDS * self.TARGET_SAMPLE_RATE
        pending = np.array([], dtype=np.float32)

        with av.open(self.file_path) as container:
            stream = next((item for item in container.streams if item.type == "audio"), None)
            if stream is None:
                raise RuntimeError(t("Dosyada kullanılabilir bir ses akışı bulunamadı."))

            duration_seconds = None
            if stream.duration is not None and stream.time_base is not None:
                duration_seconds = float(stream.duration * stream.time_base)

            resampler = av.AudioResampler(
                format="fltp",
                layout="mono",
                rate=self.TARGET_SAMPLE_RATE,
            )
            processed_samples = 0

            for frame in container.decode(stream):
                if self.isInterruptionRequested():
                    return
                for resampled in resampler.resample(frame):
                    samples = resampled.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                    pending = np.concatenate((pending, samples))
                    while len(pending) >= chunk_size:
                        chunk = pending[:chunk_size]
                        pending = pending[chunk_size:]
                        processed_samples += len(chunk)
                        yield chunk, self._calculate_progress(processed_samples, duration_seconds)

            for resampled in resampler.resample(None):
                pending = np.concatenate((
                    pending,
                    resampled.to_ndarray().reshape(-1).astype(np.float32, copy=False),
                ))

            if len(pending):
                processed_samples += len(pending)
                yield pending, self._calculate_progress(processed_samples, duration_seconds)

    def _calculate_progress(self, processed_samples: int, duration_seconds) -> int:
        if not duration_seconds:
            return 55
        ratio = min(1.0, processed_samples / (duration_seconds * self.TARGET_SAMPLE_RATE))
        return min(92, 10 + int(ratio * 82))
