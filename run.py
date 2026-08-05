import sys
import os
import winsound
import threading
import logging
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from src.config import config_manager, get_resource_path
from src.audio.recorder import AudioRecorder
from src.audio.vad import trim_silence, is_audio_meaningful
from src.engine.engine_manager import engine_manager
from src.hotkey.listener import HotkeyListener
from src.injector.paste_injector import paste_injector
from src.ui.main_window import MainWindow
from src.ui.floating_overlay import FloatingOverlay
from src.ui.tray_icon import SystemTrayManager

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("PrimeDictate.AppController")

LOGO_PATH = get_resource_path("PrimeDictate-Logo.png")

class AppSignals(QObject):
    recording_started = Signal()
    recording_stopped = Signal()
    transcription_complete = Signal(str)
    audio_level = Signal(float)
    status_changed = Signal(str, str)

class PrimeDictateApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        if os.path.exists(LOGO_PATH):
            self.app.setWindowIcon(QIcon(LOGO_PATH))

        self.signals = AppSignals()
        self.recorder = AudioRecorder()
        
        # UI Elements
        self.main_window = MainWindow(app_controller=self)
        self.overlay = FloatingOverlay()
        self.tray = SystemTrayManager(main_window=self.main_window, toggle_callback=self.toggle_dictation)

        # Hotkey Listener
        self.hotkey_listener = HotkeyListener(
            on_start_callback=self.start_dictation_from_hotkey,
            on_stop_callback=self.stop_dictation_from_hotkey
        )

        self._connect_signals()
        self.reload_settings()

    def _connect_signals(self):
        self.signals.recording_started.connect(self._on_recording_started)
        self.signals.recording_stopped.connect(self._on_recording_stopped)
        self.signals.transcription_complete.connect(self._on_transcription_complete)
        self.signals.audio_level.connect(self._on_audio_level)
        self.signals.status_changed.connect(self._on_status_changed)

        self.main_window.request_toggle_dictation.connect(self.toggle_dictation)

    def reload_settings(self):
        device_idx = config_manager.get("audio_device_index", None)
        self.recorder.set_device(device_idx)

        # Update hotkey
        self.hotkey_listener.start_listening()

    def toggle_dictation(self):
        if not self.recorder.is_recording:
            self.start_dictation()
        else:
            self.stop_dictation()

    def start_dictation_from_hotkey(self):
        self.signals.recording_started.emit()

    def stop_dictation_from_hotkey(self):
        self.signals.recording_stopped.emit()

    def start_dictation(self):
        self.signals.recording_started.emit()

    def stop_dictation(self):
        self.signals.recording_stopped.emit()

    def _on_recording_started(self):
        if self.recorder.is_recording:
            return

        if config_manager.get("play_sound", True):
            threading.Thread(target=lambda: winsound.Beep(1000, 150), daemon=True).start()

        self.recorder.start_recording(level_callback=lambda lvl: self.signals.audio_level.emit(lvl))
        self.main_window.set_recording_state(True)

        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status("Dinleniyor...", "#38bdf8")
            self.overlay.show()

    def _on_recording_stopped(self):
        if not self.recorder.is_recording:
            return

        if config_manager.get("play_sound", True):
            threading.Thread(target=lambda: winsound.Beep(800, 150), daemon=True).start()

        self.main_window.set_recording_state(False)
        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status("Metne Çevriliyor...", "#f59e0b")

        # Process recorded audio in background thread
        audio = self.recorder.stop_recording()
        threading.Thread(target=self._process_audio_thread, args=(audio,), daemon=True).start()

    def _process_audio_thread(self, audio):
        try:
            trimmed_audio = trim_silence(audio)
            if len(trimmed_audio) == 0 or not is_audio_meaningful(trimmed_audio):
                logger.info("Recorded audio was silent or too short.")
                self.signals.status_changed.emit("Ses algılanmadı", "#ef4444")
                return

            text = engine_manager.process_audio(trimmed_audio)
            if text:
                self.signals.transcription_complete.emit(text)
            else:
                self.signals.status_changed.emit("Anlaşılamadı veya Model Yüklenemedi", "#ef4444")
        except Exception as e:
            logger.error(f"Error processing dictation: {e}")
            self.signals.status_changed.emit(f"Hata: {e}", "#ef4444")

    def _on_transcription_complete(self, text: str):
        logger.info(f"Final transcription: '{text}'")

        # Inject into active focused window via clipboard Ctrl+V
        paste_injector.paste_text(text)

        # Add to history
        self.main_window.add_history_entry(text)

        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status("Aktarıldı! ✓", "#10b981")
            QTimer.singleShot(1500, self.overlay.hide)

    def _on_audio_level(self, level: float):
        if config_manager.get("overlay_enabled", True):
            self.overlay.update_audio_level(level)
        self.main_window.mic_progress.setValue(int(level * 100))

    def _on_status_changed(self, msg: str, color_hex: str):
        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status(msg, color_hex)
            QTimer.singleShot(1800, self.overlay.hide)

    def run(self):
        self.main_window.show()
        sys.exit(self.app.exec())

    def quit(self):
        self.hotkey_listener.stop_listening()
        self.app.quit()

if __name__ == "__main__":
    app = PrimeDictateApp()
    app.run()
