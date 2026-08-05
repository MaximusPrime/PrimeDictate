import numpy as np
import logging

logger = logging.getLogger("PrimeDictate.VAD")

MIN_SPEECH_DURATION_SAMPLES = 6400  # 400ms @ 16kHz

def trim_silence(audio: np.ndarray, threshold: float = 0.012) -> np.ndarray:
    """
    Trims leading and trailing silence from float32 16kHz audio array.
    """
    if len(audio) < MIN_SPEECH_DURATION_SAMPLES:
        return np.array([], dtype=np.float32)

    abs_audio = np.abs(audio)
    mask = abs_audio > threshold

    if not np.any(mask):
        return np.array([], dtype=np.float32)

    indices = np.where(mask)[0]
    start_idx = max(0, indices[0] - 1600)  # 100ms padding
    end_idx = min(len(audio), indices[-1] + 1600)

    trimmed = audio[start_idx:end_idx]
    if len(trimmed) < MIN_SPEECH_DURATION_SAMPLES:
        return np.array([], dtype=np.float32)

    return trimmed

def is_audio_meaningful(audio: np.ndarray, threshold: float = 0.015, min_active_ratio: float = 0.03) -> bool:
    """
    Returns True if audio has significant sound activity beyond room noise.
    """
    if len(audio) < MIN_SPEECH_DURATION_SAMPLES:
        return False

    active_samples = np.sum(np.abs(audio) > threshold)
    ratio = active_samples / len(audio)
    return ratio >= min_active_ratio
