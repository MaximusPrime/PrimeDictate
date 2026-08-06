import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap
from src.config import get_resource_path

class SystemTrayManager:
    def __init__(self, main_window, toggle_callback=None):
        self.main_window = main_window
        self.toggle_callback = toggle_callback

        logo_path = get_resource_path("PrimeDictate-Logo.png")
        if os.path.exists(logo_path):
            self.icon = QIcon(logo_path)
        else:
            self.icon = QIcon.fromTheme("microphone")

        self.tray = QSystemTrayIcon(self.icon, main_window)
        self.tray.setToolTip("PrimeDictate - Sistem Geneli Sesli Yazma Asistanı")

        self._setup_menu()
        self.tray.show()

    def _setup_menu(self):
        menu = QMenu()

        show_action = menu.addAction("Kontrol Paneli")
        show_action.triggered.connect(self.main_window.show_and_raise)

        toggle_action = menu.addAction("Dikteyi Başlat / Durdur")
        if self.toggle_callback:
            toggle_action.triggered.connect(self.toggle_callback)

        menu.addSeparator()

        exit_action = menu.addAction("Çıkış")
        exit_action.triggered.connect(self.main_window.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.main_window.show_and_raise()

    def show_message(self, title: str, message: str):
        self.tray.showMessage(title, message, self.icon, 2000)
