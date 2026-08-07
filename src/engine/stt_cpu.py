import logging
import os

import numpy as np

from src.engine.stt_base import BaseSTTEngine, TranscriptionCancelled
from src.engine.model_manager import model_manager
from src.i18n import t

logger = logging.getLogger("PrimeDictate.STT_CPU")


class CPUSTTEngine(BaseSTTEngine):
    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name: str = "base", language: str = "tr"):
        if self.model is not None and self.model_name == model_name:
            return

        from faster_whisper import WhisperModel

        logger.info("Loading Whisper model '%s' on CPU.", model_name)
        model_path = model_manager.get_model_path(model_name, "cpu")
        if not model_manager.is_model_downloaded(model_name, "cpu"):
            raise RuntimeError(t("Seçilen yerel Whisper modeli indirilmemiş."))
        self.model = WhisperModel(
            model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, min(8, os.cpu_count() or 4)),
        )
        self.model_name = model_name

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr", cancel_check=None) -> str:
        if len(audio) == 0:
            return ""
        if self.model is None:
            self.load_model("base", language)

        lang = None if language == "auto" else language
        segments, info = self.model.transcribe(
            self.prepare_audio(audio, sample_rate),
            beam_size=3,
            language=lang,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
        text_parts = []
        for segment in segments:
            if cancel_check and cancel_check():
                raise TranscriptionCancelled()
            text_parts.append(segment.text.strip())
        text = " ".join(text_parts).strip()
        self.last_detected_language = getattr(info, "language", None) or (None if language == "auto" else language)
        self.last_language_probability = getattr(info, "language_probability", None)
        return text
