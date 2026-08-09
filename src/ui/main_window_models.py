"""Extracted MainWindow responsibility component."""

import os
import datetime
import logging
import threading
import weakref
import shiboken6
from PySide6.QtCore import QByteArray, Qt, Signal, QUrl, QTimer
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QButtonGroup, QStackedWidget, QScrollArea,
    QFrame, QGridLayout, QSystemTrayIcon
)

from src import __version__
from src.config import APP_DIR, STT_LANGUAGES, STT_LANGUAGE_NAMES_TR, config_manager, get_resource_path
from src.i18n import get_language, legacy_translation_key, set_language, translate
from src.metadata import EMAIL, REPOSITORY, STUDIO, WEBSITE
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import supported_models
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.hardware_capabilities import detect_local_backends, recommended_local_backend
from src.engine.file_transcriber import segments_to_json, segments_to_srt, segments_to_vtt
from src.startup import configure_start_with_windows
from src.elevation import is_running_as_administrator
from src.ui.styles import PREMIUM_STYLE, get_styled_app
from src.ui.brand import app_mark_pixmap
from src.ui.main_window_widgets import QComboBox, HotkeyRecorderWidget
from src.logging_config import SensitiveDataFilter
from src.diagnostics import create_diagnostics_bundle

logger = logging.getLogger("PrimeDictate.MainWindow")
LOGO_PATH = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))

class MainWindowModelsMixin:
    def _start_hardware_detection(self):
        window_ref = weakref.ref(self)

        def worker():
            try:
                capabilities = detect_local_backends()
                window = window_ref()
                if window is None or not shiboken6.isValid(window):
                    return
                window.hardware_detection_signal.emit(capabilities)
            except RuntimeError:
                logger.debug("Hardware detection result discarded because the window was closed.")
            except Exception as error:
                logger.warning("Hardware detection failed (%s).", type(error).__name__)

        threading.Thread(target=worker, daemon=True, name="HardwareDetection").start()

    def _apply_hardware_capabilities(self, capabilities):
        if not isinstance(capabilities, dict):
            return
        self.local_backend_capabilities = capabilities
        unavailable_suffix = f" • {translate('status.unavailable')}"
        for index in range(self.backend_combo.count()):
            backend_id = self.backend_combo.itemData(index)
            capability = capabilities.get(backend_id)
            if not capability:
                continue
            label = self.backend_combo.itemText(index)
            if label.endswith(unavailable_suffix):
                label = label[:-len(unavailable_suffix)]
            if not capability.available:
                label += unavailable_suffix
            self.backend_combo.setItemText(index, label)
            model_item = self.backend_combo.model().item(index)
            if model_item is not None:
                model_item.setEnabled(capability.available)

        selected = self.backend_combo.currentData()
        selected_capability = capabilities.get(selected)
        if selected_capability and not selected_capability.available:
            self._safe_combo_set_data(
                self.backend_combo,
                recommended_local_backend(capabilities),
                2,
            )
        self._update_backend_fields()

    def browse_vulkan_runtime(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            translate("vulkan.dialog.select_runtime"),
            "",
            translate("vulkan.dialog.executable_filter"),
        )
        if file_name:
            self.vulkan_executable_input.setText(file_name)
            self._refresh_vulkan_status(file_name)

    def _refresh_vulkan_status(self, candidate_path: str = None):
        available, message = VulkanSTTEngine.runtime_status(candidate_path)
        self.vulkan_status_label.setText(message)
        self.vulkan_status_label.setStyleSheet("color: #69ddb0;" if available else "color: #ff8794;")

    def _connect_model_manager_signals(self):
        self.model_manager.progress.connect(self._on_model_progress)
        self.model_manager.download_finished.connect(self._on_model_download_finished)
        self.backend_combo.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.cloud_stt_combo.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.cloud_fallback_cb.toggled.connect(self._update_ai_provider_fields)

    def check_selected_model_status(self, model_name: str = None):
        backend = self.backend_combo.currentData()
        if backend == "cloud":
            return
        if not model_name:
            model_name = self.model_combo.currentData() or self.model_combo.currentText()

        is_downloaded = self.model_manager.is_model_downloaded(model_name, backend)
        if is_downloaded:
            self.model_status_label.setText(translate("model.status.installed", model=model_name))
            self.model_status_label.setStyleSheet("color: #78d6ad; font-weight: 600;")
            self.model_progress.setValue(100)
            self.download_model_btn.setEnabled(False)
            self.download_model_btn.setText(translate("model.status.ready"))
        else:
            self.model_status_label.setText(translate("model.status.not_installed", model=model_name))
            self.model_status_label.setStyleSheet("color: #e2c173; font-weight: 600;")
            self.model_progress.setValue(0)
            self.download_model_btn.setEnabled(True)
            self.download_model_btn.setText(translate("model.action.download_selected"))

    def download_selected_model(self):
        model_name = self.model_combo.currentData() or self.model_combo.currentText()
        backend = self.backend_combo.currentData()
        self.download_model_btn.setEnabled(False)
        self.download_model_btn.setText(translate("model.status.downloading"))
        if not self.model_manager.download_model_async(model_name, backend):
            self.download_model_btn.setEnabled(True)
            self.download_model_btn.setText(translate("model.action.download_selected"))
            self.status_label.setText(translate("model.status.download_already_running"))

    def _on_model_progress(self, percent: int, msg: str):
        if percent < 0:
            self.model_progress.setRange(0, 0)
        else:
            self.model_progress.setRange(0, 100)
            self.model_progress.setValue(percent)
        self.model_status_label.setText(msg)
        self.model_status_label.setStyleSheet("color: #76a8b4; font-weight: 600;")

    def _on_model_download_finished(self, backend: str, model_name: str, success: bool, error_msg: str):
        self.model_progress.setRange(0, 100)
        if success:
            QMessageBox.information(self, translate("model.dialog.download_complete"), translate("model.dialog.ready", model=model_name))
            if backend == self.backend_combo.currentData():
                self.check_selected_model_status(model_name)
        else:
            QMessageBox.critical(self, translate("model.dialog.download_error"), translate("model.dialog.error_detail", detail=error_msg))
            if backend == self.backend_combo.currentData():
                self.check_selected_model_status(model_name)
