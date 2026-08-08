import keyboard
import logging
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.HotkeyListener")

KEY_MAPPING = {
    "left ctrl": "ctrl", "right ctrl": "ctrl", "control": "ctrl",
    "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "left shift": "shift", "right shift": "shift",
    "left windows": "win", "right windows": "win", "windows": "win", "cmd": "win"
}
MODIFIER_KEYS = ("ctrl", "alt", "shift", "win")
VALID_MODES = {"hold", "toggle"}

def normalize_key_name(name: str) -> str:
    if not name:
        return ""
    cleaned = str(name).lower().strip()
    return KEY_MAPPING.get(cleaned, cleaned)


def canonicalize_hotkey(value: str) -> str:
    """Validate and normalize a global shortcut into deterministic key order."""
    raw_parts = [normalize_key_name(part) for part in str(value or "").split("+") if part.strip()]
    unique_parts = list(dict.fromkeys(part for part in raw_parts if part))
    modifiers = [modifier for modifier in MODIFIER_KEYS if modifier in unique_parts]
    primary_keys = [part for part in unique_parts if part not in MODIFIER_KEYS]
    if len(primary_keys) != 1:
        return ""
    primary = primary_keys[0]
    is_function_key = primary.startswith("f") and primary[1:].isdigit() and 1 <= int(primary[1:]) <= 24
    if not modifiers and not is_function_key:
        return ""
    return "+".join([*modifiers, primary])

class HotkeyListener:
    def __init__(self, on_start_callback=None, on_stop_callback=None):
        self.on_start_callback = on_start_callback
        self.on_stop_callback = on_stop_callback
        self.current_hotkey = None
        self.current_mode = "toggle"
        self.target_keys = set()
        self.pressed_keys = set()
        self.is_recording = False
        self._combo_active = False
        self._hook_ref = None

    def start_listening(self):
        hotkey = config_manager.get("hotkey", "ctrl+alt+d")
        mode = config_manager.get("hotkey_mode", "toggle")
        if not canonicalize_hotkey(hotkey):
            logger.warning("Invalid saved global hotkey; using the safe default.")
            hotkey = "ctrl+alt+d"
        return self.update_hotkey(hotkey, mode)

    def update_hotkey(self, new_hotkey: str, mode: str = "toggle"):
        self.stop_listening()

        self.current_hotkey = canonicalize_hotkey(new_hotkey)
        self.current_mode = mode if mode in VALID_MODES else "toggle"
        if not self.current_hotkey:
            logger.error("Global hotkey is empty or unsafe.")
            return False

        parts = [normalize_key_name(p) for p in self.current_hotkey.split("+") if p.strip()]
        self.target_keys = set(parts)
        if not self.target_keys:
            logger.error("Parsed hotkey target set is empty.")
            return False

        self.pressed_keys.clear()
        self._combo_active = False
        logger.info("Registering global hotkey '%s' in '%s' mode.", self.current_hotkey, self.current_mode)

        try:
            self._hook_ref = keyboard.hook(self._on_keyboard_event)
            return True
        except Exception as e:
            logger.error(f"Failed to register keyboard hook for hotkey '{self.current_hotkey}': {e}")
            self.stop_listening()
            return False

    def _on_keyboard_event(self, event):
        key_name = normalize_key_name(event.name)
        if not key_name:
            return

        if event.event_type == "down":
            self.pressed_keys.add(key_name)
        elif event.event_type == "up":
            self.pressed_keys.discard(key_name)

        is_satisfied = self.target_keys.issubset(self.pressed_keys)

        if self.current_mode == "hold":
            # Push-to-Talk (Hold)
            if is_satisfied and not self.is_recording:
                self.is_recording = True
                if self.on_start_callback:
                    self.on_start_callback()
            elif not is_satisfied and self.is_recording:
                self.is_recording = False
                if self.on_stop_callback:
                    self.on_stop_callback()
        else:
            # Toggle Mode
            if is_satisfied:
                if not self._combo_active:
                    self._combo_active = True
                    self._toggle_recording()
            else:
                self._combo_active = False

    def _toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            if self.on_start_callback:
                self.on_start_callback()
        else:
            self.is_recording = False
            if self.on_stop_callback:
                self.on_stop_callback()

    def stop_listening(self):
        if self._hook_ref is not None:
            try:
                keyboard.unhook(self._hook_ref)
            except Exception as e:
                logger.error(f"Error unhooking keyboard listener: {e}")
            self._hook_ref = None
        self.pressed_keys.clear()
        self._combo_active = False

    def sync_recording_state(self, is_recording: bool):
        self.is_recording = is_recording
