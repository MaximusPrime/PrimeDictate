import numpy as np
import logging

logger = logging.getLogger("PrimeDictate.VAD")

def trim_silence(audio: np.ndarray, threshold: float = 0.01, min_speech_duration_samples: int = 1600) -> np.ndarray:
    """
    Trims leading and trailing silence from float32 audio array.
    """
    if len(audio) == 0:
        return audio

    abs_audio = np.abs(audio)
    mask = abs_audio > threshold

    if not np.any(mask):
        return np.array([], dtype=np.float32)

    indices = np.where(mask)[0]
    start_idx = max(0, indices[0] - 800)  # include 50ms padding
    end_idx = min(len(audio), indices[-1] + 800)

    trimmed = audio[start_idx:end_idx]
    if len(trimmed) < min_speech_duration_samples:
        return np.array([], dtype=np.float32)

    return trimmed

def is_audio_meaningful(audio: np.ndarray, threshold: float = 0.015, min_active_ratio: float = 0.05) -> bool:
    """
    Returns True if audio has significant sound activity beyond background noise.
    """
    if len(audio) < 1600:  # < 100ms
        return False
    active_samples = np.sum(np.abs(audio) > threshold)
    ratio = active_samples / len(audio)
    return ratio >= min_active_ratio
