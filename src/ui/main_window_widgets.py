"""Reusable widgets used by the PrimeDictate main window pages."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QComboBox as QtQComboBox, QPushButton

from src.hotkey.listener import canonicalize_hotkey
from src.i18n import translate

class QComboBox(QtQComboBox):
    def wheelEvent(self, event):
        event.ignore()

class HotkeyRecorderWidget(QPushButton):
    hotkey_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hotkeyRecorderBtn")
        self.setCursor(Qt.PointingHandCursor)
        self._hotkey_str = "ctrl+alt+d"
        self._recording = False
        self._changed_during_recording = False
        self.clicked.connect(self._toggle_recording)
        self._update_display()

    def set_hotkey(self, hotkey_str: str):
        self._hotkey_str = canonicalize_hotkey(hotkey_str) or "ctrl+alt+d"
        self._update_display()

    def get_hotkey(self) -> str:
        return self._hotkey_str

    def _toggle_recording(self):
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        main_win = self.window()
        controller = getattr(main_win, "app_controller", None) if main_win else None
        if controller and getattr(getattr(controller, "state", None), "value", "idle") != "idle":
            self.setText(translate("hotkey.error.operation_active"))
            return
        self._recording = True
        self._changed_during_recording = False
        self.setProperty("recording", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(translate("hotkey.press_combination"))
        self.setFocus()
        if main_win and hasattr(main_win, "app_controller") and main_win.app_controller:
            if hasattr(main_win.app_controller, "hotkey_listener"):
                main_win.app_controller.hotkey_listener.stop_listening()

    def _stop_recording(self):
        if self._recording:
            self._recording = False
            self.setProperty("recording", "false")
            self.style().unpolish(self)
            self.style().polish(self)
            self._update_display()
            main_win = self.window()
            if main_win and hasattr(main_win, "app_controller") and main_win.app_controller:
                if hasattr(main_win.app_controller, "hotkey_listener") and not self._changed_during_recording:
                    main_win.app_controller.hotkey_listener.start_listening()

    def keyPressEvent(self, event):
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key_Escape:
            self._stop_recording()
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.AltModifier:
            parts.append("alt")
        if modifiers & Qt.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.MetaModifier:
            parts.append("win")

        key_name = self._key_to_string(key, event)
        if key_name in ("ctrl", "alt", "shift", "win"):
            if key_name not in parts:
                parts.append(key_name)
            display_parts = [p.upper() if len(p) <= 3 else p.capitalize() for p in parts]
            self.setText(" + ".join(display_parts) + " + ...")
            return

        if key_name:
            if key_name not in parts:
                parts.append(key_name)
            new_hotkey = canonicalize_hotkey("+".join(parts))
            if not new_hotkey:
                self.setText(translate("hotkey.error.unsafe"))
                return
            self._hotkey_str = new_hotkey
            self._changed_during_recording = True
            self.hotkey_changed.emit(new_hotkey)
            self._stop_recording()

    def focusOutEvent(self, event):
        if self._recording:
            self._stop_recording()
        super().focusOutEvent(event)

    def _key_to_string(self, key: int, event) -> str:
        key_map = {
            Qt.Key_Control: "ctrl", Qt.Key_Alt: "alt", Qt.Key_Shift: "shift", Qt.Key_Meta: "win",
            Qt.Key_Space: "space", Qt.Key_Return: "enter", Qt.Key_Enter: "enter",
            Qt.Key_Tab: "tab", Qt.Key_Backspace: "backspace", Qt.Key_Delete: "delete",
            Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right",
            Qt.Key_CapsLock: "capslock", Qt.Key_ScrollLock: "scrolllock", Qt.Key_NumLock: "numlock",
            Qt.Key_Pause: "pause", Qt.Key_Print: "printscreen", Qt.Key_Insert: "insert",
            Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "pageup", Qt.Key_PageDown: "pagedown",
            Qt.Key_Escape: "escape",
        }
        if key in key_map:
            return key_map[key]
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return f"f{key - Qt.Key_F1 + 1}"
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(ord('a') + (key - Qt.Key_A))
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(ord('0') + (key - Qt.Key_0))
        if Qt.Key_Keypad0 <= key <= Qt.Key_Keypad9:
            return str(key - Qt.Key_Keypad0)

        seq = QKeySequence(key).toString().lower()
        cleaned = "".join([c for c in seq if ord(c) >= 32])
        if cleaned:
            return cleaned

        return ""

    def _update_display(self):
        if not self._hotkey_str:
            self.setText(translate("hotkey.choose"))
            return
        parts = [p.upper() if len(p) <= 3 else p.capitalize() for p in self._hotkey_str.split("+")]
        self.setText(" + ".join(parts))
