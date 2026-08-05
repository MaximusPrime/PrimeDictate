import os
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap

LOGO_PATH = r"c:\Users\MAXIMUS\PROJECTS\PrimeDictate-Project\PrimeDictate-Logo.png"

class SystemTrayManager:
    def __init__(self, main_window, toggle_callback=None):
        self.main_window = main_window
        self.toggle_callback = toggle_callback

        if os.path.exists(LOGO_PATH):
            self.icon = QIcon(LOGO_PATH)
        else:
            self.icon = QIcon.fromTheme("microphone")

        self.tray = QSystemTrayIcon(self.icon, main_window)
        self.tray.setToolTip("PrimeDictate - AMD GPU Destekli Sesli Yazma")

        self._setup_menu()
        self.tray.show()

    def _setup_menu(self):
        menu = QMenu()

        show_action = menu.addAction("📌 Kontrol Paneli")
        show_action.triggered.connect(self.main_window.show_and_raise)

        toggle_action = menu.addAction("🎙️ Dikteyi Başlat / Durdur")
        if self.toggle_callback:
            toggle_action.triggered.connect(self.toggle_callback)

        menu.addSeparator()

        exit_action = menu.addAction("❌ Çıkış")
        exit_action.triggered.connect(self.main_window.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.main_window.show_and_raise()

    def show_message(self, title: str, message: str):
        self.tray.showMessage(title, message, self.icon, 2000)
