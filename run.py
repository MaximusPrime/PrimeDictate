import sys
import os
import winsound
import threading
import logging
from enum import Enum
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QLockFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon, QGuiApplication

from src.config import APP_DIR, config_manager, get_resource_path
from src.i18n import set_language, translate
from src.audio.recorder import AudioRecorder
from src.audio.vad import trim_silence, is_audio_meaningful
from src.engine.engine_manager import engine_manager
from src.hotkey.listener import HotkeyListener
from src.injector.paste_injector import paste_injector
from src.operation_coordinator import OperationCoordinator
from src.ui.main_window import MainWindow
from src.ui.floating_overlay import FloatingOverlay
from src.ui.tray_icon import SystemTrayManager
from src.logging_config import configure_logging

# Configure bounded, redacted file and console logging before app startup.
LOG_PATH = configure_logging(APP_DIR)
logger = logging.getLogger("PrimeDictate.AppController")

LOGO_PATH = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))

class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    SUCCESS = "success"
    ERROR = "error"

class AppSignals(QObject):
    recording_started = Signal()
    recording_stopped = Signal()
    transcription_complete = Signal(str)
    audio_level = Signal(float)
    status_changed = Signal(str, str)
    recording_limit_reached = Signal()

class PrimeDictateApp(QObject):
    def __init__(self):
        set_language(config_manager.get("ui_language", "tr"))
        try:
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass
        self.app = QApplication(sys.argv)
        # Initialize the QObject only after QApplication exists. This gives
        # worker-originated signals a main-thread receiver context, so Qt
        # queues UI callbacks and timers onto the GUI event loop.
        super().__init__()
        self.app.setQuitOnLastWindowClosed(False)
        self.instance_lock = QLockFile(os.path.join(APP_DIR, "PrimeDictate.lock"))
        if not self.instance_lock.tryLock(100):
            QMessageBox.information(None, "PrimeDictate", translate("app.already_running"))
            raise SystemExit(0)

        if os.path.exists(LOGO_PATH):
            self.app.setWindowIcon(QIcon(LOGO_PATH))

        self.signals = AppSignals(self)
        self.recorder = AudioRecorder()
        self.engine_manager = engine_manager
        self.operation_coordinator = OperationCoordinator()
        self.state = AppState.IDLE
        self.target_window = None
        self._shutdown_requested = threading.Event()
        self._processing_thread = None
        self._quitting = False
        
        # UI Elements
        self.main_window = MainWindow(app_controller=self)
        self.overlay = FloatingOverlay(start_callback=self.start_dictation, stop_callback=self.stop_dictation)
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
        self.signals.recording_limit_reached.connect(self._on_recording_limit_reached)

        self.main_window.request_toggle_dictation.connect(self.toggle_dictation)

    def reload_settings(self):
        device_idx = config_manager.get("audio_device_index", None)
        self.recorder.set_device(device_idx)

        # Update hotkey
        self.hotkey_listener.start_listening()
        if hasattr(self, "tray"):
            self.tray.retranslate()
            self.tray.set_dictation_state(
                self.state.value,
                enabled=config_manager.get("setup_completed", False),
            )

        if config_manager.get("overlay_enabled", True) and config_manager.get("overlay_always_on", False):
            self.overlay.set_recording_active(False)
            self.overlay.set_status(translate("overlay.status.ready"), "#edf0f3")
            self.overlay.show()
        elif not config_manager.get("overlay_always_on", False) and self.state == AppState.IDLE:
            self.overlay.hide()

    def toggle_dictation(self):
        if self.state == AppState.IDLE:
            self.start_dictation()
        elif self.state == AppState.RECORDING:
            self.stop_dictation()

    def start_dictation_from_hotkey(self):
        self.signals.recording_started.emit()

    def stop_dictation_from_hotkey(self):
        self.signals.recording_stopped.emit()

    def start_dictation(self):
        self.signals.recording_started.emit()

    def stop_dictation(self):
        self.signals.recording_stopped.emit()

    @Slot()
    def _on_recording_started(self):
        if self.state != AppState.IDLE:
            return
        if not config_manager.get("setup_completed", False):
            self.main_window.show_and_raise()
            self.main_window._set_page(1)
            self._set_state(AppState.IDLE, translate("setup.status.required"))
            return
        if not self.operation_coordinator.try_begin("dictation"):
            self.main_window.set_app_state("transcribing", translate("status.processing"))
            return

        self.target_window = paste_injector.capture_target_window()

        if config_manager.get("play_sound", True):
            threading.Thread(target=lambda: winsound.Beep(1000, 150), daemon=True).start()

        try:
            self.recorder.start_recording(
                level_callback=lambda lvl: self.signals.audio_level.emit(lvl),
                max_duration_seconds=config_manager.get("max_recording_seconds", 300),
                limit_callback=lambda: self.signals.recording_limit_reached.emit(),
            )
        except Exception as exc:
            self.operation_coordinator.finish("dictation")
            logger.error("Could not start recording: %s", exc)
            self._set_state(AppState.ERROR, translate("microphone.error.start"))
            QTimer.singleShot(1800, lambda: self._set_state(AppState.IDLE, translate("status.ready")))
            return

        self._set_state(AppState.RECORDING, translate("status.listening"))

        if config_manager.get("overlay_enabled", True):
            self.overlay.set_recording_active(True)
            self.overlay.set_status(translate("overlay.status.listening"), "#38bdf8")
            self.overlay.show()

    @Slot()
    def _on_recording_stopped(self):
        if self.state != AppState.RECORDING or not self.recorder.is_recording:
            return

        if config_manager.get("play_sound", True):
            threading.Thread(target=lambda: winsound.Beep(800, 150), daemon=True).start()

        self._set_state(AppState.TRANSCRIBING, translate("status.transcribing"))
        if config_manager.get("overlay_enabled", True):
            self.overlay.set_recording_active(False)
            self.overlay.set_status(translate("overlay.status.transcribing"), "#f59e0b")

        # Stream finalization, concatenation and resampling can be expensive.
        self._processing_thread = threading.Thread(
            target=self._finalize_and_process_audio_thread,
            daemon=True,
            name="DictationProcessing",
        )
        self._processing_thread.start()

    @Slot()
    def _on_recording_limit_reached(self):
        if self.state == AppState.RECORDING:
            self._on_recording_stopped()

    def _finalize_and_process_audio_thread(self):
        try:
            audio = self.recorder.stop_recording()
        except Exception as exc:
            logger.error("Could not finalize recording: %s", exc)
            self.signals.status_changed.emit(translate("recording.error.finalize"), "#ef4444")
            return
        self._process_audio_thread(audio)

    def _process_audio_thread(self, audio):
        try:
            trimmed_audio = trim_silence(audio)
            if len(trimmed_audio) == 0 or not is_audio_meaningful(trimmed_audio):
                logger.info("Recorded audio was silent or too short.")
                self.signals.status_changed.emit(translate("recording.error.no_audio"), "#ef4444")
                return

            text = self.engine_manager.process_audio(
                trimmed_audio,
                cancel_check=self._shutdown_requested.is_set,
            )
            if text:
                self.signals.transcription_complete.emit(text)
            else:
                error_message = self.engine_manager.last_error or translate("stt.error.no_result")
                self.signals.status_changed.emit(error_message, "#ef4444")
        except Exception as e:
            logger.error(f"Error processing dictation: {e}")
            self.signals.status_changed.emit(translate("error.with_detail", detail=e), "#ef4444")

    @Slot(str)
    def _on_transcription_complete(self, text: str):
        if self._shutdown_requested.is_set():
            self._finish_dictation_operation()
            return
        logger.info("Final transcription ready (%d characters).", len(text))

        # Inject into active focused window via clipboard Ctrl+V
        pasted = paste_injector.paste_text(
            text,
            restore_clipboard=config_manager.get("restore_clipboard", True),
            target_hwnd=self.target_window,
        )

        # Add to history
        self.main_window.add_history_entry(text)
        self.main_window.update_transcription_metadata(self.engine_manager.last_transcription_info)
        self._finish_dictation_operation()
        result_message = translate("result.pasted" if pasted else "result.copied")
        processing_info = self.engine_manager.last_transcription_info.get("text_processing", {})
        if processing_info.get("fallback_used"):
            result_message = f"{result_message} • {translate('status.cleanup_fallback_used')}"
        self._set_state(AppState.SUCCESS, result_message)

        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status(result_message, "#10b981")
            if config_manager.get("overlay_always_on", False):
                QTimer.singleShot(1800, lambda: (self.overlay.set_status(translate("overlay.status.ready"), "#edf0f3"), self.overlay.set_recording_active(False)))
            else:
                QTimer.singleShot(1500, self.overlay.hide)

    @Slot(float)
    def _on_audio_level(self, level: float):
        if config_manager.get("overlay_enabled", True):
            self.overlay.update_audio_level(level)
        self.main_window.mic_progress.setValue(int(level * 100))

    @Slot(str, str)
    def _on_status_changed(self, msg: str, color_hex: str):
        self._finish_dictation_operation()
        if self._shutdown_requested.is_set():
            return
        self._set_state(AppState.ERROR, msg)
        if config_manager.get("overlay_enabled", True):
            self.overlay.set_status(msg, color_hex)
            if config_manager.get("overlay_always_on", False):
                QTimer.singleShot(1800, lambda: (self.overlay.set_status(translate("overlay.status.ready"), "#edf0f3"), self.overlay.set_recording_active(False)))
            else:
                QTimer.singleShot(1800, self.overlay.hide)
        QTimer.singleShot(1800, lambda: self._set_state(AppState.IDLE, translate("status.ready")))

    def _set_state(self, state: AppState, message: str):
        self.state = state
        self.hotkey_listener.sync_recording_state(state == AppState.RECORDING)
        self.main_window.set_app_state(state.value, message)
        if hasattr(self, "tray"):
            self.tray.set_dictation_state(
                state.value,
                enabled=config_manager.get("setup_completed", False),
            )
        if state == AppState.SUCCESS:
            QTimer.singleShot(1500, lambda: self._set_state(AppState.IDLE, translate("status.ready")))

    def _finish_dictation_operation(self):
        self.operation_coordinator.finish("dictation")
        self._processing_thread = None
        self.hotkey_listener.sync_recording_state(False)

    def run(self):
        self.main_window.show()
        sys.exit(self.app.exec())

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._shutdown_requested.set()
        # Exit is explicit: remove every top-level surface immediately so a
        # slow/cancelled worker can never leave an orphaned overlay behind.
        self.overlay.hide()
        self.tray.shutdown()
        self.hotkey_listener.stop_listening()
        if self.recorder.is_recording:
            self.recorder.stop_recording()
        if not self.main_window.prepare_shutdown():
            logger.error("File transcription worker did not stop during application exit.")
        processing_thread = self._processing_thread
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=10)
            if processing_thread.is_alive():
                logger.error("Dictation worker did not stop during application exit; abandoning daemon worker.")
        self.main_window.hide()
        self.operation_coordinator.finish("dictation")
        self.instance_lock.unlock()
        self.app.quit()

if __name__ == "__main__":
    app = PrimeDictateApp()
    app.run()
