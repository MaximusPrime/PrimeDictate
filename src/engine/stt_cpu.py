import logging
import os

import numpy as np

from src.engine.stt_base import BaseSTTEngine

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
        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, min(8, os.cpu_count() or 4)),
        )
        self.model_name = model_name

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        if len(audio) == 0:
            return ""
        if self.model is None:
            self.load_model("base", language)

        lang = None if language == "auto" else language
        segments, _ = self.model.transcribe(
            audio.astype(np.float32, copy=False),
            beam_size=3,
            language=lang,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
