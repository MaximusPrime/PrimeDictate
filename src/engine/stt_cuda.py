import logging
import numpy as np
from src.engine.stt_base import BaseSTTEngine, TranscriptionCancelled
from src.engine.model_manager import model_manager
from src.i18n import translate
from src.engine.hardware_capabilities import detect_cuda_backend, preferred_cuda_compute_types

logger = logging.getLogger("PrimeDictate.STT_CUDA")

class CUDASTTEngine(BaseSTTEngine):
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        capability = detect_cuda_backend()
        if not capability.available:
            raise RuntimeError(translate("cuda.error.no_device"))
        compute_types = preferred_cuda_compute_types(capability.detail.split(", "))
        if not compute_types:
            raise RuntimeError(translate("cuda.error.no_compute_type"))

        logger.info("Loading Whisper model '%s' on NVIDIA GPU (CUDA).", model_name)
        from faster_whisper import WhisperModel
        model_path = model_manager.get_model_path(model_name, "cuda")
        if not model_manager.is_model_downloaded(model_name, "cuda"):
            raise RuntimeError(translate("stt.local_model_missing"))
        last_error = None
        for compute_type in compute_types:
            try:
                self.model = WhisperModel(model_path, device="cuda", compute_type=compute_type)
                self.model_name = model_name
                self.last_inference_device = f"NVIDIA CUDA GPU 0 • {compute_type}"
                logger.info("Successfully loaded '%s' on NVIDIA CUDA %s.", model_name, compute_type)
                return
            except Exception as error:
                last_error = error
                logger.warning("CUDA model load failed with compute_type=%s (%s).", compute_type, type(error).__name__)
        self.model = None
        self.model_name = None
        self.last_inference_device = None
        raise RuntimeError(
            translate("cuda.error.model_load")
        ) from last_error

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
            raise RuntimeError(translate("cuda.error.transcription")) from e
