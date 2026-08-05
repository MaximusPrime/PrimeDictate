import keyboard
import logging
import threading
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.HotkeyListener")

class HotkeyListener:
    def __init__(self, on_start_callback=None, on_stop_callback=None):
        self.on_start_callback = on_start_callback
        self.on_stop_callback = on_stop_callback
        self.current_hotkey = None
        self.is_recording = False
        self.hook_handle = None

    def start_listening(self):
        hotkey = config_manager.get("hotkey", "ctrl+alt+d")
        mode = config_manager.get("hotkey_mode", "toggle")
        self.update_hotkey(hotkey, mode)

    def update_hotkey(self, new_hotkey: str, mode: str = "toggle"):
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        self.current_hotkey = new_hotkey.strip().lower()
        logger.info(f"Registering global hotkey '{self.current_hotkey}' in '{mode}' mode.")

        try:
            if mode == "hold":
                keyboard.on_press_key(self.current_hotkey, self._handle_press)
                keyboard.on_release_key(self.current_hotkey, self._handle_release)
            else:  # toggle
                keyboard.add_hotkey(self.current_hotkey, self._toggle_recording, suppress=False)
        except Exception as e:
            logger.error(f"Failed to register hotkey '{self.current_hotkey}': {e}")

    def _toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            if self.on_start_callback:
                self.on_start_callback()
        else:
            self.is_recording = False
            if self.on_stop_callback:
                self.on_stop_callback()

    def _handle_press(self, event):
        if not self.is_recording:
            self.is_recording = True
            if self.on_start_callback:
                self.on_start_callback()

    def _handle_release(self, event):
        if self.is_recording:
            self.is_recording = False
            if self.on_stop_callback:
                self.on_stop_callback()

    def stop_listening(self):
        try:
            keyboard.unhook_all()
        except Exception as e:
            logger.error(f"Error stopping hotkey listener: {e}")
