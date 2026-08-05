from abc import ABC, abstractmethod
import numpy as np

class BaseSTTEngine(ABC):
    @abstractmethod
    def load_model(self, model_name: str, language: str = "tr"):
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000, language: str = "tr") -> str:
        pass
