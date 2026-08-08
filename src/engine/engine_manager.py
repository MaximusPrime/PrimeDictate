import logging
import threading
import time
import numpy as np
from src.config import STT_LANGUAGES, config_manager
from src.engine.stt_cuda import CUDASTTEngine
from src.engine.stt_cpu import CPUSTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.ai_cleanup import TextProcessingError, ai_cleanup_engine
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
        self._warmup_thread = None
        self._warmup_ready = threading.Event()
        self._warmup_ready.set()

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

    def shutdown(self):
        for engine in tuple(self.engines.values()):
            close = getattr(engine, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.exception("Could not close transcription engine cleanly.")
        self.engines.clear()

    def is_model_resident(self, backend: str = None) -> bool:
        backend = backend or config_manager.get("stt_backend", "cpu")
        engine = self.engines.get(backend)
        check = getattr(engine, "is_model_resident", None)
        return bool(check()) if callable(check) else False

    def is_warmup_active(self) -> bool:
        return bool(self._warmup_thread and self._warmup_thread.is_alive())

    def unload_model(self, backend: str = None):
        backend = backend or config_manager.get("stt_backend", "cpu")
        engine = self.engines.get(backend)
        unload = getattr(engine, "unload_model", None)
        if callable(unload):
            unload()

    def load_selected_model(self, backend: str = None):
        backend = backend or config_manager.get("stt_backend", "cpu")
        if backend not in {"cuda", "vulkan"}:
            return
        engine = self.get_engine(backend)
        engine.load_model(
            config_manager.get("model_size", "base"),
            _validated_language(config_manager.get("language", "tr")),
        )
        warmup = getattr(engine, "warmup", None)
        if callable(warmup):
            warmup()

    def start_warmup(self):
        backend = config_manager.get("stt_backend", "cpu")
        if backend == "cloud":
            self._warmup_ready.set()
            return
        if self._warmup_thread and self._warmup_thread.is_alive():
            return
        model_size = config_manager.get("model_size", "base")
        language = _validated_language(config_manager.get("language", "tr"))
        self._warmup_ready.clear()

        def worker():
            started = time.perf_counter()
            try:
                engine = self.get_engine(backend)
                engine.load_model(model_size, language)
                warmup = getattr(engine, "warmup", None)
                if callable(warmup):
                    warmup()
                logger.info(
                    "Transcription engine warmup completed backend=%s seconds=%.3f.",
                    backend,
                    time.perf_counter() - started,
                )
            except Exception:
                logger.exception("Transcription engine warmup failed; first dictation will retry normally.")
            finally:
                self._warmup_ready.set()

        self._warmup_thread = threading.Thread(
            target=worker,
            daemon=True,
            name="EngineWarmup",
        )
        self._warmup_thread.start()

    def process_audio(self, audio: np.ndarray, sample_rate: int = 16000, language_override: str = None, cancel_check=None, apply_text_processing: bool = True) -> str:
        if len(audio) == 0:
            return ""
        if cancel_check and cancel_check():
            raise TranscriptionCancelled()
        self.last_error = None
        self._warmup_ready.wait(timeout=30)

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
            transcription_started = time.perf_counter()
            raw_text = engine.transcribe(audio, **transcribe_args)
            transcription_seconds = time.perf_counter() - transcription_started
            self._capture_transcription_info(
                engine, backend, language, transcription_seconds, len(audio) / sample_rate
            )

            if not raw_text or not raw_text.strip():
                self.last_error = getattr(engine, "last_error", None)
                return ""

            # Perform AI Cleanup (stutter removal, punctuation, formatting)
            if cancel_check and cancel_check():
                raise TranscriptionCancelled()
            final_text = self._clean_text(raw_text, cancel_check) if apply_text_processing else raw_text.strip()
            if cancel_check and cancel_check():
                raise TranscriptionCancelled()
            return final_text
        except TranscriptionCancelled:
            raise
        except TextProcessingError:
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
                    transcription_started = time.perf_counter()
                    raw_text = cloud_engine.transcribe(audio, **cloud_args)
                    transcription_seconds = time.perf_counter() - transcription_started
                    self._capture_transcription_info(
                        cloud_engine, "cloud", language, transcription_seconds, len(audio) / sample_rate
                    )
                    if not raw_text:
                        self.last_error = getattr(cloud_engine, "last_error", self.last_error)
                    return self._clean_text(raw_text, cancel_check) if apply_text_processing else raw_text.strip()
                except TranscriptionCancelled:
                    raise
                except Exception as ex:
                    logger.error(f"Cloud fallback also failed: {ex}")
            return ""

    def _capture_transcription_info(self, engine, backend: str, requested_language: str, transcription_seconds=None, audio_seconds=None):
        real_time_factor = None
        if isinstance(transcription_seconds, (float, int)) and isinstance(audio_seconds, (float, int)) and audio_seconds > 0:
            real_time_factor = transcription_seconds / audio_seconds
        self.last_transcription_info = {
            "backend": backend,
            "requested_language": requested_language,
            "detected_language": getattr(engine, "last_detected_language", None),
            "language_probability": getattr(engine, "last_language_probability", None),
            "inference_device": getattr(engine, "last_inference_device", None),
            "audio_seconds": audio_seconds,
            "transcription_seconds": transcription_seconds,
            "real_time_factor": real_time_factor,
        }
        if real_time_factor is not None:
            logger.info(
                "STT performance backend=%s device=%s audio_seconds=%.3f transcription_seconds=%.3f real_time_factor=%.3f",
                backend,
                self.last_transcription_info["inference_device"] or "unknown",
                audio_seconds,
                transcription_seconds,
                real_time_factor,
            )

    def _clean_text(self, raw_text: str, cancel_check=None) -> str:
        try:
            return ai_cleanup_engine.clean_text(raw_text, cancel_check=cancel_check)
        finally:
            self.last_transcription_info["text_processing"] = dict(
                getattr(ai_cleanup_engine, "last_processing_info", {})
            )

    def process_text(self, raw_text: str, cancel_check=None) -> str:
        return self._clean_text(raw_text, cancel_check)

engine_manager = EngineManager()
