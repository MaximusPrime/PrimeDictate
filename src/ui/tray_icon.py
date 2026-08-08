import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap
from src.config import get_resource_path
from src.i18n import translate
from src.ui.brand import app_mark_pixmap

class SystemTrayManager:
    def __init__(self, main_window, toggle_callback=None):
        self.main_window = main_window
        self.toggle_callback = toggle_callback
        self._dictation_state = "idle"
        self._dictation_enabled = True

        logo_path = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))
        if os.path.exists(logo_path):
            self.icon = QIcon(app_mark_pixmap(64))
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

    def set_dictation_state(self, state: str, enabled: bool = True):
        self._dictation_state = state
        self._dictation_enabled = enabled
        self._refresh_toggle_action()

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
