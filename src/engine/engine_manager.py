import logging
import numpy as np
from src.config import config_manager
from src.engine.stt_cuda import CUDASTTEngine
from src.engine.stt_cpu import CPUSTTEngine
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.stt_cloud import CloudSTTEngine
from src.engine.ai_cleanup import ai_cleanup_engine

logger = logging.getLogger("PrimeDictate.EngineManager")

class EngineManager:
    def __init__(self):
        self.engines = {}
        self.current_backend = None

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

    def process_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if len(audio) == 0:
            return ""

        backend = config_manager.get("stt_backend", "cpu")
        model_size = config_manager.get("model_size", "base")
        language = config_manager.get("language", "tr")

        logger.info(f"Processing audio with backend '{backend}', model '{model_size}', lang '{language}'")

        try:
            engine = self.get_engine(backend)
            if backend != "cloud":
                engine.load_model(model_size, language)

            raw_text = engine.transcribe(audio, sample_rate=sample_rate, language=language)

            if not raw_text or not raw_text.strip():
                return ""

            # Perform AI Cleanup (stutter removal, punctuation, formatting)
            final_text = ai_cleanup_engine.clean_text(raw_text)
            return final_text
        except Exception as e:
            logger.error(f"Error in EngineManager processing: {e}")
            if backend != "cloud" and config_manager.get("allow_cloud_fallback", False):
                try:
                    logger.info("Attempting user-approved cloud fallback...")
                    cloud_engine = self.get_engine("cloud")
                    raw_text = cloud_engine.transcribe(audio, sample_rate=sample_rate, language=language)
                    return ai_cleanup_engine.clean_text(raw_text)
                except Exception as ex:
                    logger.error(f"Cloud fallback also failed: {ex}")
            return ""

engine_manager = EngineManager()
