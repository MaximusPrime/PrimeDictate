import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine, TranscriptionCancelled
from src.engine.model_manager import model_manager
from src.i18n import t

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
        model_path = model_manager.get_model_path(model_name, "cuda")
        if not model_manager.is_model_downloaded(model_name, "cuda"):
            raise RuntimeError(t("Seçilen yerel Whisper modeli indirilmemiş."))
        try:
            self.model = WhisperModel(model_path, device="cuda", compute_type="float16")
            self.model_name = model_name
            logger.info(f"Successfully loaded '{model_name}' on NVIDIA CUDA float16.")
        except Exception as e1:
            logger.warning(f"CUDA float16 failed ({e1}), attempting CUDA int8...")
            try:
                self.model = WhisperModel(model_path, device="cuda", compute_type="int8")
                self.model_name = model_name
                logger.info(f"Successfully loaded '{model_name}' on NVIDIA CUDA int8.")
            except Exception as e2:
                self.model = None
                self.model_name = None
                raise RuntimeError(
                    t("CUDA modeli yüklenemedi. NVIDIA sürücülerini kontrol edin veya Yerel CPU motorunu seçin.")
                ) from e2

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr", cancel_check=None) -> str:
        if len(audio) == 0:
            return ""

        if self.model is None:
            self.load_model("base", language)

        if self.model is None:
            return ""

        try:
            lang = None if language == "auto" else language
            segments, info = self.model.transcribe(
                self.prepare_audio(audio, sample_rate),
                beam_size=3,
                language=lang,
                vad_filter=True
            )
            text_segments = []
            for segment in segments:
                if cancel_check and cancel_check():
                    raise TranscriptionCancelled()
                text_segments.append(segment.text.strip())
            full_text = " ".join(text_segments).strip()
            self.last_detected_language = getattr(info, "language", None) or (None if language == "auto" else language)
            self.last_language_probability = getattr(info, "language_probability", None)
            return full_text
        except TranscriptionCancelled:
            raise
        except Exception as e:
            logger.error(f"Transcription error in CUDA engine: {e}")
            raise RuntimeError(t("CUDA transkripsiyonu başarısız oldu.")) from e
