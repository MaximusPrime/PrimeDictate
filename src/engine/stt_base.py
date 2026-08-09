from abc import ABC, abstractmethod
import numpy as np


class TranscriptionCancelled(Exception):
    pass


class BaseSTTEngine(ABC):
    last_detected_language = None
    last_language_probability = None
    last_inference_device = None

    @staticmethod
    def prepare_audio(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        prepared = audio.astype(np.float32, copy=False)
        if sample_rate == 16000:
            return prepared
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        from scipy.signal import resample_poly
        divisor = int(np.gcd(sample_rate, 16000))
        return resample_poly(prepared, 16000 // divisor, sample_rate // divisor).astype(np.float32)

    @abstractmethod
    def load_model(self, model_name: str, language: str = "tr"):
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr", cancel_check=None) -> str:
        pass
