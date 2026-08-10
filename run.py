import sys
import os
import winsound
import threading
import logging
import time
from enum import Enum
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QLockFile, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon, QGuiApplication

from src.config import APP_DIR, config_manager, get_resource_path
from src.i18n import set_language, translate
from src.audio.recorder import AudioRecorder
from src.audio.session_silencer import AudioSessionSilencer
from src.audio.vad import trim_silence, is_audio_meaningful
from src.engine.engine_manager import engine_manager
from src.hotkey.listener import HotkeyListener
from src.injector.paste_injector import paste_injector
from src.operation_coordinator import OperationCoordinator
from src.ui.main_window import MainWindow
from src.ui.floating_overlay import FloatingOverlay
from src.ui.tray_icon import SystemTrayManager
from src.logging_config import configure_logging
from src.startup import (
    configure_start_with_windows,
    consume_show_window_request,
    launch_elevated_task,
)
from src.elevation import relaunch_as_administrator, should_attempt_configured_elevation

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
    model_memory_finished = Signal(bool, bool, str)  # loading, success, detail

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
        self.audio_silencer = AudioSessionSilencer()
        self.engine_manager = engine_manager
        self.operation_coordinator = OperationCoordinator()
        self.state = AppState.IDLE
        self.target_window = None
        self._shutdown_requested = threading.Event()
        self._processing_thread = None
        self._dictation_stopped_at = None
        self._quitting = False
        
        # UI Elements
        self.main_window = MainWindow(app_controller=self)
        self.overlay = FloatingOverlay(start_callback=self.start_dictation, stop_callback=self.stop_dictation)
        self._model_memory_busy = False
        self.tray = SystemTrayManager(
            main_window=self.main_window,
            toggle_callback=self.toggle_dictation,
            model_memory_callback=self.toggle_model_memory,
        )

        # Refresh older Run entries so existing users also receive the
        # --start-hidden startup behavior after upgrading.
        if config_manager.get("start_with_windows", False) or config_manager.get("run_as_administrator", False):
            try:
                configure_start_with_windows(
                    True,
                    elevated=config_manager.get("run_as_administrator", False),
                )
            except OSError:
                logger.warning("Could not refresh the Windows startup entry.", exc_info=True)

        # Hotkey Listener
        self.hotkey_listener = HotkeyListener(
            on_start_callback=self.start_dictation_from_hotkey,
            on_stop_callback=self.stop_dictation_from_hotkey
        )

        self._connect_signals()
        self.reload_settings()
        self.engine_manager.start_warmup()
        self._warmup_was_active = self.engine_manager.is_warmup_active()
        self._show_model_warmup_status()
        QTimer.singleShot(250, self._poll_model_warmup)

    def _connect_signals(self):
        self.signals.recording_started.connect(self._on_recording_started)
        self.signals.recording_stopped.connect(self._on_recording_stopped)
        self.signals.transcription_complete.connect(self._on_transcription_complete)
        self.signals.audio_level.connect(self._on_audio_level)
        self.signals.status_changed.connect(self._on_status_changed)
        self.signals.recording_limit_reached.connect(self._on_recording_limit_reached)
        self.signals.model_memory_finished.connect(self._on_model_memory_finished)

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

    def _sync_tray_model_memory(self):
        backend = config_manager.get("stt_backend", "cpu")
        self.tray.set_model_memory_state(
            backend,
            self.engine_manager.is_model_resident(backend),
            self._model_memory_busy or self.engine_manager.is_warmup_active(),
        )

    def _poll_model_warmup(self):
        active = self.engine_manager.is_warmup_active()
        self._sync_tray_model_memory()
        if active:
            self._warmup_was_active = True
        elif getattr(self, "_warmup_was_active", False):
            self._warmup_was_active = False
            if self.state == AppState.IDLE:
                self.main_window.set_app_state(AppState.IDLE.value, translate("status.ready"))
                if config_manager.get("overlay_enabled", True) and config_manager.get("overlay_always_on", False):
                    self.overlay.set_status(translate("overlay.status.ready"), "#edf0f3")
        if active and not self._shutdown_requested.is_set():
            QTimer.singleShot(500, self._poll_model_warmup)

    def track_model_warmup(self):
        """Expose newly-started settings warmup immediately and track completion."""
        self._warmup_was_active = self.engine_manager.is_warmup_active()
        self._show_model_warmup_status()
        QTimer.singleShot(100, self._poll_model_warmup)

    def _show_model_warmup_status(self):
        if not self.engine_manager.is_warmup_active() or self.state != AppState.IDLE:
            return
        self.main_window.set_app_state(AppState.IDLE.value, translate("status.preparing_model"))
        if config_manager.get("overlay_enabled", True) and config_manager.get("overlay_always_on", False):
            self.overlay.set_status(translate("overlay.status.preparing_model"), "#f59e0b")
            self.overlay.show()

    def toggle_model_memory(self):
        backend = config_manager.get("stt_backend", "cpu")
        if (
            backend not in {"cpu", "cuda", "vulkan"}
            or self.state != AppState.IDLE
            or self._model_memory_busy
            or self.engine_manager.is_warmup_active()
        ):
            return
        loading = not self.engine_manager.is_model_resident(backend)
        self._model_memory_busy = True
        self._sync_tray_model_memory()

        def worker():
            try:
                if loading:
                    self.engine_manager.load_selected_model(backend)
                else:
                    self.engine_manager.unload_model(backend)
                self.signals.model_memory_finished.emit(loading, True, "")
            except Exception as exc:
                logger.exception("Model memory operation failed.")
                self.signals.model_memory_finished.emit(loading, False, str(exc))

        threading.Thread(target=worker, daemon=True, name="ModelMemoryOperation").start()

    @Slot(bool, bool, str)
    def _on_model_memory_finished(self, loading: bool, success: bool, detail: str):
        self._model_memory_busy = False
        self._sync_tray_model_memory()
        if success:
            backend = config_manager.get("stt_backend", "cpu")
            if loading:
                key = "tray.notice.model_loaded_ram" if backend == "cpu" else "tray.notice.model_loaded"
            else:
                key = "tray.notice.ram_released" if backend == "cpu" else "tray.notice.vram_released"
            self.tray.show_message("PrimeDictate", translate(key))
        else:
            self.tray.show_message("PrimeDictate", translate("tray.notice.model_memory_error", detail=detail))

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
        if self._model_memory_busy:
            self._set_state(AppState.IDLE, translate("status.processing"))
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

        if config_manager.get("mute_other_audio", False):
            # Silence playback before opening the microphone so the beginning
            # of the recording cannot capture a browser/video tail.
            self.audio_silencer.mute()

        try:
            self.recorder.start_recording(
                level_callback=lambda lvl: self.signals.audio_level.emit(lvl),
                max_duration_seconds=config_manager.get("max_recording_seconds", 300),
                limit_callback=lambda: self.signals.recording_limit_reached.emit(),
            )
        except Exception as exc:
            self.audio_silencer.restore()
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

        # Recording has logically ended. Restore output sessions on the same
        # Qt thread that muted them before finalization moves to a worker.
        self.audio_silencer.restore()

        if config_manager.get("play_sound", True):
            threading.Thread(target=lambda: winsound.Beep(800, 150), daemon=True).start()

        self._dictation_stopped_at = time.perf_counter()
        warmup_active = self.engine_manager.is_warmup_active()
        status_text = translate("status.preparing_model") if warmup_active else translate("status.transcribing")
        overlay_text = translate("overlay.status.preparing_model") if warmup_active else translate("overlay.status.transcribing")
        self._set_state(AppState.TRANSCRIBING, status_text)
        if config_manager.get("overlay_enabled", True):
            self.overlay.set_processing_active(True)
            self.overlay.set_status(overlay_text, "#f59e0b")

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
        # Release the operation before optional dashboard/history rendering.
        # A UI refresh failure must never strand dictation in TRANSCRIBING.
        self._finish_dictation_operation()
        result_message = translate("result.pasted" if pasted else "result.copied")
        processing_info = self.engine_manager.last_transcription_info.get("text_processing", {})
        if processing_info.get("fallback_used"):
            result_message = f"{result_message} • {translate('status.cleanup_fallback_used')}"
        # The result is already available; do not impose an artificial success
        # cooldown before accepting the next dictation.
        self._set_state(AppState.IDLE, result_message)

        try:
            self.main_window.add_history_entry(text)
        except Exception:
            logger.exception("Could not refresh transcription history after a successful dictation.")
        try:
            self.main_window.update_transcription_metadata(self.engine_manager.last_transcription_info)
        except Exception:
            logger.exception("Could not refresh transcription metadata after a successful dictation.")

        if config_manager.get("overlay_enabled", True):
            self.overlay.set_processing_active(False)
            overlay_result = translate("overlay.status.pasted" if pasted else "overlay.status.copied")
            self.overlay.set_status(overlay_result, "#10b981", tooltip_text=result_message)
            if config_manager.get("overlay_always_on", False):
                QTimer.singleShot(1800, self._settle_overlay_if_idle)
            else:
                QTimer.singleShot(1500, self._hide_overlay_if_idle)

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
            self.overlay.set_status(translate("overlay.status.error"), color_hex, tooltip_text=msg)
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
            self._sync_tray_model_memory()
        if state == AppState.SUCCESS:
            QTimer.singleShot(1500, lambda: self._set_state(AppState.IDLE, translate("status.ready")))

    def _settle_overlay_if_idle(self):
        if self.state == AppState.IDLE:
            self.overlay.set_processing_active(False)
            self.overlay.set_recording_active(False)
            self.overlay.set_status(translate("overlay.status.ready"), "#edf0f3")

    def _hide_overlay_if_idle(self):
        if self.state == AppState.IDLE:
            self.overlay.hide()

    def _finish_dictation_operation(self):
        if self._dictation_stopped_at is not None:
            logger.info(
                "Dictation stop-to-result latency=%.3f seconds.",
                time.perf_counter() - self._dictation_stopped_at,
            )
            self._dictation_stopped_at = None
        self.operation_coordinator.finish("dictation")
        self._processing_thread = None
        self.hotkey_listener.sync_recording_state(False)

    def run(self):
        show_requested = consume_show_window_request()
        start_hidden = (
            "--start-hidden" in sys.argv
            and not show_requested
            and config_manager.get("setup_completed", False)
        )
        if not start_hidden:
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
        silencer = getattr(self, "audio_silencer", None)
        if silencer is not None:
            silencer.restore()
        if not self.main_window.prepare_shutdown():
            logger.error("File transcription worker did not stop during application exit.")
        processing_thread = self._processing_thread
        if processing_thread and processing_thread.is_alive():
            processing_thread.join(timeout=10)
            if processing_thread.is_alive():
                logger.error("Dictation worker did not stop during application exit; abandoning daemon worker.")
        self.main_window.hide()
        self.engine_manager.shutdown()
        self.operation_coordinator.finish("dictation")
        self.instance_lock.unlock()
        self.app.quit()

if __name__ == "__main__":
    if should_attempt_configured_elevation(config_manager):
        try:
            if launch_elevated_task(show_window="--start-hidden" not in sys.argv):
                raise SystemExit(0)
            if relaunch_as_administrator():
                raise SystemExit(0)
        except OSError:
            logger.exception("The configured administrator relaunch was declined or failed.")
    app = PrimeDictateApp()
    app.run()
