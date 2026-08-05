import numpy as np
import sounddevice as sd
import queue
import threading
import logging

logger = logging.getLogger("PrimeDictate.AudioRecorder")

class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.stream = None
        self.frames = []
        self.level_callback = None
        self.device_index = None

    @staticmethod
    def get_input_devices():
        devices = []
        try:
            device_list = sd.query_devices()
            for i, dev in enumerate(device_list):
                if dev['max_input_channels'] > 0:
                    devices.append({'index': i, 'name': dev['name'], 'channels': dev['max_input_channels']})
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
        return devices

    def set_device(self, device_index):
        self.device_index = device_index

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio callback status: {status}")
        if self.is_recording:
            audio_data = indata.copy()
            self.frames.append(audio_data)
            
            # Calculate RMS level for visualizer (0.0 to 1.0)
            rms = np.sqrt(np.mean(np.square(audio_data)))
            level = min(float(rms * 10.0), 1.0)
            
            if self.level_callback:
                self.level_callback(level)

    def start_recording(self, level_callback=None):
        if self.is_recording:
            return
        
        self.frames = []
        self.level_callback = level_callback
        self.is_recording = True

        try:
            kwargs = {
                'samplerate': self.sample_rate,
                'channels': self.channels,
                'dtype': 'float32',
                'callback': self._audio_callback
            }
            if self.device_index is not None:
                kwargs['device'] = self.device_index

            self.stream = sd.InputStream(**kwargs)
            self.stream.start()
            logger.info("Audio recording started.")
        except Exception as e:
            self.is_recording = False
            logger.error(f"Failed to start recording stream: {e}")
            raise e

    def stop_recording(self) -> np.ndarray:
        if not self.is_recording:
            return np.array([], dtype=np.float32)

        self.is_recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
            self.stream = None

        if self.frames:
            recorded_audio = np.concatenate(self.frames, axis=0).flatten()
            logger.info(f"Audio recording stopped. Captured {len(recorded_audio)} samples ({len(recorded_audio)/self.sample_rate:.2f}s)")
            return recorded_audio
        return np.array([], dtype=np.float32)
