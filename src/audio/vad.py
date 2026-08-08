import numpy as np


SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # 20 ms
MIN_SPEECH_SAMPLES = 3200  # 200 ms of active speech
MIN_RECORDING_SAMPLES = 3840  # 240 ms total
PADDING_SAMPLES = 3200  # 200 ms pre/post-roll
MIN_RMS_THRESHOLD = 0.003


def _frame_rms(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(audio) == 0:
        return np.array([], dtype=np.float32)
    frame_count = int(np.ceil(len(audio) / FRAME_SAMPLES))
    padded = np.pad(audio, (0, frame_count * FRAME_SAMPLES - len(audio)))
    frames = padded.reshape(frame_count, FRAME_SAMPLES)
    return np.sqrt(np.mean(np.square(frames), axis=1))


def _activity_mask(audio: np.ndarray) -> np.ndarray:
    rms = _frame_rms(audio)
    if len(rms) == 0:
        return np.array([], dtype=bool)
    peak_rms = float(np.max(rms))
    if peak_rms < MIN_RMS_THRESHOLD:
        return np.zeros(len(rms), dtype=bool)

    # The quietest frames estimate the current room/microphone noise floor.
    noise_floor = float(np.percentile(rms, 20))
    adaptive_threshold = max(
        MIN_RMS_THRESHOLD,
        min(noise_floor * 3.0, peak_rms * 0.35),
    )
    return rms >= adaptive_threshold


def trim_silence(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(audio) < MIN_RECORDING_SAMPLES:
        return np.array([], dtype=np.float32)

    active = _activity_mask(audio)
    active_frames = np.flatnonzero(active)
    if len(active_frames) == 0:
        return np.array([], dtype=np.float32)

    start = max(0, int(active_frames[0] * FRAME_SAMPLES) - PADDING_SAMPLES)
    end = min(len(audio), int((active_frames[-1] + 1) * FRAME_SAMPLES) + PADDING_SAMPLES)
    return audio[start:end].astype(np.float32, copy=False)


def is_audio_meaningful(audio: np.ndarray) -> bool:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(audio) < MIN_RECORDING_SAMPLES:
        return False
    active = _activity_mask(audio)
    active_samples = int(np.count_nonzero(active) * FRAME_SAMPLES)
    return active_samples >= MIN_SPEECH_SAMPLES
