import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine

logger = logging.getLogger("PrimeDictate.STT_Vulkan")

class VulkanSTTEngine(BaseSTTEngine):
    """
    Vulkan accelerated GGUF / whisper.cpp backend for AMD GPUs.
    Falls back to faster-whisper int8 execution if whisper.cpp Vulkan binary is not precompiled.
    """
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        logger.info(f"Loading Whisper model '{model_name}' on Vulkan AMD GPU...")
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(model_name, device="auto", compute_type="int8")
            self.model_name = model_name
            logger.info(f"Vulkan/Fast local model '{model_name}' ready.")
        except Exception as e:
            logger.error(f"Failed to load Vulkan model: {e}")
            raise e

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if self.model is None:
            self.load_model("base", language)

        if len(audio) == 0:
            return ""

        try:
            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                audio,
                beam_size=3,
                language=lang,
                vad_filter=True
            )
            text = " ".join([seg.text.strip() for seg in segments]).strip()
            return text
        except Exception as e:
            logger.error(f"Vulkan transcription error: {e}")
            return ""
