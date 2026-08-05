import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine

logger = logging.getLogger("PrimeDictate.STT_CUDA")

class CUDASTTEngine(BaseSTTEngine):
    """
    NVIDIA GPU (CUDA / cuDNN) accelerated Whisper engine.
    Falls back to CPU if CUDA runtime is not available on device.
    """
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        logger.info(f"Loading Whisper model '{model_name}' on NVIDIA GPU (CUDA)...")
        try:
            from faster_whisper import WhisperModel
            try:
                self.model = WhisperModel(model_name, device="cuda", compute_type="float16")
                self.model_name = model_name
                logger.info(f"Successfully loaded '{model_name}' on NVIDIA CUDA float16.")
            except Exception as e1:
                logger.warning(f"CUDA float16 failed, trying int8: {e1}")
                self.model = WhisperModel(model_name, device="cuda", compute_type="int8")
                self.model_name = model_name
        except Exception as e:
            logger.warning(f"CUDA execution failed, falling back to CPU: {e}")
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_name, device="cpu", compute_type="int8")
            self.model_name = model_name

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if self.model is None:
            self.load_model("base", language)

        if len(audio) == 0:
            return ""

        try:
            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                audio,
                beam_size=5,
                language=lang,
                vad_filter=True
            )
            text_segments = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_segments).strip()
            logger.info(f"Transcribed (CUDA - {info.language}): {full_text}")
            return full_text
        except Exception as e:
            logger.error(f"Transcription error in CUDA engine: {e}")
            return ""
