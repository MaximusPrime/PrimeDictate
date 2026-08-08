import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
import logging

logger = logging.getLogger("PrimeDictate.AudioRecorder")

TARGET_SAMPLE_RATE = 16000

class AudioRecorder:
    def __init__(self):
        self.is_recording = False
        self.stream = None
        self.frames = []
        self.level_callback = None
        self.device_index = None
        self.native_sample_rate = TARGET_SAMPLE_RATE
        self.max_samples = None
        self.recorded_samples = 0
        self.limit_callback = None
        self._limit_notified = False
        self.max_duration_seconds = None
        self.smoothed_level = None

    @staticmethod
    def get_input_devices():
        devices = []
        try:
            device_list = sd.query_devices()
            for i, dev in enumerate(device_list):
                if dev['max_input_channels'] > 0:
                    devices.append({
                        'index': i,
                        'name': dev['name'],
                        'channels': dev['max_input_channels'],
                        'default_samplerate': int(dev['default_samplerate'])
                    })
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
        return devices

    def set_device(self, device_index):
        self.device_index = device_index

    def _get_device_sample_rate(self) -> int:
        try:
            dev_info = sd.query_devices(self.device_index, 'input')
            return int(dev_info.get('default_samplerate', 16000))
        except Exception:
            return 16000

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio callback status: {status}")
        if self.is_recording:
            audio_data = indata.copy()
            if self.max_samples is not None:
                remaining = self.max_samples - self.recorded_samples
                if remaining <= 0:
                    self._notify_recording_limit()
                    return
                if len(audio_data) > remaining:
                    audio_data = audio_data[:remaining]
            self.frames.append(audio_data)
            self.recorded_samples += len(audio_data)

            # Calibrated dBFS meter: -60 dB is silence, -6 dB is near clipping.
            rms = float(np.sqrt(np.mean(np.square(audio_data))))
            dbfs = 20.0 * np.log10(max(rms, 1e-6))
            level = min(1.0, max(0.0, (dbfs + 60.0) / 54.0))
            self.smoothed_level = level if self.smoothed_level is None else (0.72 * self.smoothed_level + 0.28 * level)

            if self.level_callback:
                self.level_callback(self.smoothed_level)

            if self.max_samples is not None and self.recorded_samples >= self.max_samples:
                self._notify_recording_limit()

    def _notify_recording_limit(self):
        if self._limit_notified:
            return
        self._limit_notified = True
        if self.limit_callback:
            self.limit_callback()

    def start_recording(self, level_callback=None, max_duration_seconds=None, limit_callback=None):
        if self.is_recording:
            return

        self.frames = []
        self.level_callback = level_callback
        self.limit_callback = limit_callback
        self.native_sample_rate = self._get_device_sample_rate()
        self.recorded_samples = 0
        self._limit_notified = False
        self.smoothed_level = None
        try:
            duration = float(max_duration_seconds) if max_duration_seconds is not None else 0
        except (TypeError, ValueError):
            duration = 0
        self.max_duration_seconds = min(duration, 3600) if duration > 0 else None
        self.max_samples = (
            max(1, int(self.max_duration_seconds * self.native_sample_rate))
            if self.max_duration_seconds
            else None
        )
        self.is_recording = True

        try:
            kwargs = {
                'samplerate': self.native_sample_rate,
                'channels': 1,
                'dtype': 'float32',
                'callback': self._audio_callback
            }
            if self.device_index is not None:
                kwargs['device'] = self.device_index

            self.stream = sd.InputStream(**kwargs)
            self.stream.start()
            logger.info(f"Started audio stream on device {self.device_index} @ {self.native_sample_rate}Hz")
        except Exception as e:
            self.is_recording = False
            logger.error(f"Failed to start InputStream @ {self.native_sample_rate}Hz: {e}")
            # Retry with 16000Hz fallback if custom rate failed
            try:
                self.native_sample_rate = 16000
                if self.max_duration_seconds:
                    self.max_samples = max(1, int(self.max_duration_seconds * self.native_sample_rate))
                kwargs['samplerate'] = 16000
                self.stream = sd.InputStream(**kwargs)
                self.stream.start()
                self.is_recording = True
                logger.info("Fallback to 16000Hz InputStream succeeded.")
            except Exception as ex:
                self.is_recording = False
                logger.error(f"Fallback InputStream also failed: {ex}")
                raise ex

    def stop_recording(self) -> np.ndarray:
        if not self.is_recording:
            return np.array([], dtype=np.float32)

        self.is_recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing stream: {e}")
            self.stream = None

        if not self.frames:
            return np.array([], dtype=np.float32)

        recorded_audio = np.concatenate(self.frames, axis=0).flatten()
        self.frames = []

        # Resample to 16000Hz if microphone rate was different
        if self.native_sample_rate != TARGET_SAMPLE_RATE and len(recorded_audio) > 0:
            try:
                gcd = np.gcd(self.native_sample_rate, TARGET_SAMPLE_RATE)
                up = TARGET_SAMPLE_RATE // gcd
                down = self.native_sample_rate // gcd
                resampled = resample_poly(recorded_audio, up, down).astype(np.float32)
                logger.info(f"Resampled audio from {self.native_sample_rate}Hz to {TARGET_SAMPLE_RATE}Hz ({len(resampled)} samples)")
                return resampled
            except Exception as e:
                logger.error(f"Audio resampling failed: {e}")

        return recorded_audio.astype(np.float32)
