import os
import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine

logger = logging.getLogger("PrimeDictate.STT_DirectML")

class DirectMLSTTEngine(BaseSTTEngine):
    def __init__(self):
        self.model = None
        self.model_name = None
        self.device = "directml"

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        logger.info(f"Loading Whisper model '{model_name}' on AMD GPU (DirectML)...")
        try:
            from faster_whisper import WhisperModel
            # Attempt CTranslate2 / DirectML or CPU float16/int8
            try:
                self.model = WhisperModel(model_name, device="auto", compute_type="int8")
                self.model_name = model_name
                logger.info(f"Successfully loaded '{model_name}' via CTranslate2/DirectML.")
            except Exception as e1:
                logger.warning(f"Fallback to CPU int8: {e1}")
                self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
                self.model_name = model_name
        except Exception as e:
            logger.error(f"Failed to load DirectML Whisper model: {e}")
            raise e

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if self.model is None:
            self.load_model("base", language)

        if len(audio) == 0:
            return ""

        try:
            # Normalize float32 audio
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                language=lang,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            text_segments = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_segments).strip()
            logger.info(f"Transcribed ({info.language}): {full_text}")
            return full_text
        except Exception as e:
            logger.error(f"Transcription error in DirectML engine: {e}")
            return ""
