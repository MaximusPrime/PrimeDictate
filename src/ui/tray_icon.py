from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon
from src.i18n import translate
from src.ui.brand import app_mark_pixmap

class SystemTrayManager:
    def __init__(self, main_window, toggle_callback=None, model_memory_callback=None):
        self.main_window = main_window
        self.toggle_callback = toggle_callback
        self.model_memory_callback = model_memory_callback
        self._dictation_state = "idle"
        self._dictation_enabled = True
        self._model_backend = "cpu"
        self._model_resident = False
        self._model_memory_busy = False

        logo = app_mark_pixmap(64)
        if not logo.isNull():
            self.icon = QIcon(logo)
        else:
            self.icon = QIcon.fromTheme("microphone")

        self.tray = QSystemTrayIcon(self.icon, main_window)
        self.tray.setToolTip(translate("tray.tooltip"))

        self._setup_menu()
        self.tray.show()

    def _setup_menu(self):
        menu = QMenu()

        self.show_action = menu.addAction(translate("tray.open_dashboard"))
        self.show_action.triggered.connect(self.main_window.show_and_raise)

        self.toggle_action = menu.addAction(translate("tray.start_dictation"))
        if self.toggle_callback:
            self.toggle_action.triggered.connect(self.toggle_callback)

        self.model_memory_action = menu.addAction(translate("tray.release_vram"))
        if self.model_memory_callback:
            self.model_memory_action.triggered.connect(self.model_memory_callback)
        self.model_memory_action.setVisible(False)

        menu.addSeparator()

        self.settings_action = menu.addAction(translate("tray.open_settings"))
        self.settings_action.triggered.connect(lambda: self.main_window.show_page(4))

        self.history_action = menu.addAction(translate("tray.open_history"))
        self.history_action.triggered.connect(lambda: self.main_window.show_page(5))

        menu.addSeparator()

        self.exit_action = menu.addAction(translate("tray.exit"))
        self.exit_action.triggered.connect(self.main_window.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

    def retranslate(self):
        self.tray.setToolTip(translate("tray.tooltip"))
        self.show_action.setText(translate("tray.open_dashboard"))
        self.settings_action.setText(translate("tray.open_settings"))
        self.history_action.setText(translate("tray.open_history"))
        self.exit_action.setText(translate("tray.exit"))
        self._refresh_toggle_action()
        self._refresh_model_memory_action()

    def set_dictation_state(self, state: str, enabled: bool = True):
        self._dictation_state = state
        self._dictation_enabled = enabled
        self._refresh_toggle_action()
        self._refresh_model_memory_action()

    def set_model_memory_state(self, backend: str, resident: bool, busy: bool = False):
        self._model_backend = backend
        self._model_resident = resident
        self._model_memory_busy = busy
        self._refresh_model_memory_action()

    def _refresh_model_memory_action(self):
        supported = self._model_backend in {"cuda", "vulkan"}
        self.model_memory_action.setVisible(supported)
        if not supported:
            return
        if self._model_memory_busy:
            key = "tray.model_memory_busy"
        elif self._model_resident:
            key = "tray.release_vram"
        else:
            key = "tray.load_model"
        self.model_memory_action.setText(translate(key))
        can_change = self._dictation_state == "idle" and not self._model_memory_busy
        self.model_memory_action.setEnabled(bool(self.model_memory_callback) and can_change)

    def _refresh_toggle_action(self):
        if self._dictation_state == "recording":
            key = "tray.stop_dictation"
            can_toggle = True
        elif self._dictation_state == "idle":
            key = "tray.start_dictation"
            can_toggle = self._dictation_enabled
        else:
            key = "tray.dictation_busy"
            can_toggle = False
        self.toggle_action.setText(translate(key))
        self.toggle_action.setEnabled(bool(self.toggle_callback) and can_toggle)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.main_window.show_and_raise()

    def show_message(self, title: str, message: str):
        self.tray.showMessage(title, message, self.icon, 2000)

    def shutdown(self):
        self.tray.hide()
        self.tray.setContextMenu(None)
