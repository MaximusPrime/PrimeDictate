import logging
import numpy as np
from src.config import STT_LANGUAGES, config_manager
from src.engine.stt_cuda import CUDASTTEngine
from src.engine.stt_cpu import CPUSTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.ai_cleanup import ai_cleanup_engine
from src.engine.stt_base import TranscriptionCancelled

logger = logging.getLogger("PrimeDictate.EngineManager")


def _validated_language(value) -> str:
    if isinstance(value, str) and (value == "auto" or value in STT_LANGUAGES):
        return value
    logger.warning("Invalid STT language configuration %r; falling back to auto detection.", value)
    return "auto"

class EngineManager:
    def __init__(self):
        self.engines = {}
        self.current_backend = None
        self.last_transcription_info = {}
        self.last_error = None

    def get_engine(self, backend: str):
        if backend not in self.engines:
            if backend == "cuda":
                self.engines[backend] = CUDASTTEngine()
            elif backend == "vulkan":
                self.engines[backend] = VulkanSTTEngine()
            elif backend == "cloud":
                self.engines[backend] = CloudSTTEngine()
            else:  # cpu
                self.engines[backend] = CPUSTTEngine()
        return self.engines[backend]

    def process_audio(self, audio: np.ndarray, sample_rate: int = 16000, language_override: str = None, cancel_check=None) -> str:
        if len(audio) == 0:
            return ""
        if cancel_check and cancel_check():
            raise TranscriptionCancelled()
        self.last_error = None

        backend = config_manager.get("stt_backend", "cpu")
        model_size = config_manager.get("model_size", "base")
        configured_language = language_override if language_override is not None else config_manager.get("language", "tr")
        language = _validated_language(configured_language)

        logger.info(f"Processing audio with backend '{backend}', model '{model_size}', lang '{language}'")

        try:
            engine = self.get_engine(backend)
            if backend != "cloud":
                engine.load_model(model_size, language)

            transcribe_args = {"sample_rate": sample_rate, "language": language}
            if cancel_check:
                transcribe_args["cancel_check"] = cancel_check
            raw_text = engine.transcribe(audio, **transcribe_args)
            self._capture_transcription_info(engine, backend, language)

            if not raw_text or not raw_text.strip():
                self.last_error = getattr(engine, "last_error", None)
                return ""

            # Perform AI Cleanup (stutter removal, punctuation, formatting)
            if cancel_check and cancel_check():
                raise TranscriptionCancelled()
            final_text = ai_cleanup_engine.clean_text(raw_text)
            if cancel_check and cancel_check():
                raise TranscriptionCancelled()
            return final_text
        except TranscriptionCancelled:
            raise
        except Exception as e:
            logger.error(f"Error in EngineManager processing: {e}")
            self.last_error = str(e)
            if backend != "cloud" and config_manager.get("allow_cloud_fallback", False):
                try:
                    logger.info("Attempting user-approved cloud fallback...")
                    cloud_engine = self.get_engine("cloud")
                    cloud_args = {"sample_rate": sample_rate, "language": language}
                    if cancel_check:
                        cloud_args["cancel_check"] = cancel_check
                    raw_text = cloud_engine.transcribe(audio, **cloud_args)
                    self._capture_transcription_info(cloud_engine, "cloud", language)
                    if not raw_text:
                        self.last_error = getattr(cloud_engine, "last_error", self.last_error)
                    return ai_cleanup_engine.clean_text(raw_text)
                except TranscriptionCancelled:
                    raise
                except Exception as ex:
                    logger.error(f"Cloud fallback also failed: {ex}")
            return ""

    def _capture_transcription_info(self, engine, backend: str, requested_language: str):
        self.last_transcription_info = {
            "backend": backend,
            "requested_language": requested_language,
            "detected_language": getattr(engine, "last_detected_language", None),
            "language_probability": getattr(engine, "last_language_probability", None),
        }

engine_manager = EngineManager()
