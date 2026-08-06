import keyboard
import logging
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.HotkeyListener")

class HotkeyListener:
    def __init__(self, on_start_callback=None, on_stop_callback=None):
        self.on_start_callback = on_start_callback
        self.on_stop_callback = on_stop_callback
        self.current_hotkey = None
        self.is_recording = False
        self.hook_handles = []

    def start_listening(self):
        hotkey = config_manager.get("hotkey", "ctrl+alt+d")
        mode = config_manager.get("hotkey_mode", "toggle")
        self.update_hotkey(hotkey, mode)

    def update_hotkey(self, new_hotkey: str, mode: str = "toggle"):
        self.stop_listening()

        self.current_hotkey = new_hotkey.strip().lower()
        if not self.current_hotkey:
            logger.error("Global hotkey cannot be empty.")
            return False
        logger.info(f"Registering global hotkey '{self.current_hotkey}' in '{mode}' mode.")

        try:
            if mode == "hold":
                self.hook_handles.append(keyboard.add_hotkey(
                    self.current_hotkey, self._handle_press, suppress=False
                ))
                self.hook_handles.append(keyboard.add_hotkey(
                    self.current_hotkey, self._handle_release, suppress=False,
                    trigger_on_release=True
                ))
            else:  # toggle
                self.hook_handles.append(keyboard.add_hotkey(
                    self.current_hotkey, self._toggle_recording, suppress=False
                ))
            return True
        except Exception as e:
            logger.error(f"Failed to register hotkey '{self.current_hotkey}': {e}")
            self.stop_listening()
            return False

    def _toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            if self.on_start_callback:
                self.on_start_callback()
        else:
            self.is_recording = False
            if self.on_stop_callback:
                self.on_stop_callback()

    def _handle_press(self):
        if not self.is_recording:
            self.is_recording = True
            if self.on_start_callback:
                self.on_start_callback()

    def _handle_release(self):
        if self.is_recording:
            self.is_recording = False
            if self.on_stop_callback:
                self.on_stop_callback()

    def stop_listening(self):
        for handle in self.hook_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception as e:
                logger.error(f"Error stopping hotkey listener: {e}")
        self.hook_handles.clear()

    def sync_recording_state(self, is_recording: bool):
        self.is_recording = is_recording
