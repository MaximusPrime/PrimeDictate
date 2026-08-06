import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine

logger = logging.getLogger("PrimeDictate.STT_CUDA")

class CUDASTTEngine(BaseSTTEngine):
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        logger.info(f"Loading Whisper model '{model_name}' on NVIDIA GPU (CUDA)...")
        from faster_whisper import WhisperModel
        try:
            self.model = WhisperModel(model_name, device="cuda", compute_type="float16")
            self.model_name = model_name
            logger.info(f"Successfully loaded '{model_name}' on NVIDIA CUDA float16.")
        except Exception as e1:
            logger.warning(f"CUDA float16 failed ({e1}), attempting CUDA int8...")
            try:
                self.model = WhisperModel(model_name, device="cuda", compute_type="int8")
                self.model_name = model_name
                logger.info(f"Successfully loaded '{model_name}' on NVIDIA CUDA int8.")
            except Exception as e2:
                self.model = None
                self.model_name = None
                raise RuntimeError(
                    "CUDA modeli yüklenemedi. NVIDIA sürücülerini kontrol edin veya Yerel CPU motorunu seçin."
                ) from e2

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if len(audio) == 0:
            return ""

        if self.model is None:
            self.load_model("base", language)

        if self.model is None:
            return ""

        try:
            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                audio,
                beam_size=3,
                language=lang,
                vad_filter=True
            )
            text_segments = [segment.text.strip() for segment in segments]
            full_text = " ".join(text_segments).strip()
            return full_text
        except Exception as e:
            logger.error(f"Transcription error in CUDA engine: {e}")
            return ""
