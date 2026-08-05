import os
import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine

logger = logging.getLogger("PrimeDictate.STT_DirectML")

class DirectMLSTTEngine(BaseSTTEngine):
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        logger.info(f"Loading Whisper model '{model_name}' (DirectML / Fast Execution)...")
        try:
            from faster_whisper import WhisperModel
            # Try loading with int8 computation for maximum speed and stability
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
            self.model_name = model_name
            logger.info(f"Successfully loaded '{model_name}' model.")
        except Exception as e:
            logger.error(f"Failed to load DirectML/Yerel model '{model_name}': {e}")
            self.model = None
            self.model_name = None
            raise RuntimeError(f"Model yükleme hatası ({model_name}): {e}")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if len(audio) == 0:
            return ""

        if self.model is None:
            self.load_model("base", language)

        if self.model is None:
            return ""

        try:
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                audio,
                beam_size=3,
                language=lang,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400)
            )

            text_segments = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_segments).strip()
            logger.info(f"Transcribed ({info.language}): {full_text}")
            return full_text
        except Exception as e:
            logger.error(f"Transcription error in DirectML engine: {e}")
            return ""
