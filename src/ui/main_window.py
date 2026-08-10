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
    QGroupBox, QComboBox as QtQComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QButtonGroup, QStackedWidget, QScrollArea,
    QFrame, QGridLayout, QSystemTrayIcon, QBoxLayout
)

from src import __version__
from src.config import APP_DIR, STT_LANGUAGES, STT_LANGUAGE_NAMES_TR, config_manager, get_resource_path
from src.history import HistoryStore
from src.i18n import get_language, legacy_translation_key, set_language, translate
from src.metadata import EMAIL, REPOSITORY, STUDIO, WEBSITE
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import model_manager, supported_models
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.hardware_capabilities import detect_local_backends, recommended_local_backend
from src.engine.file_transcriber import segments_to_json, segments_to_srt, segments_to_vtt
from src.engine.engine_manager import engine_manager
from src.engine.provider_catalog import provider_catalog
from src.startup import configure_start_with_windows
from src.elevation import is_running_as_administrator
from src.ui.styles import PREMIUM_STYLE, get_styled_app
from src.ui.brand import app_mark_pixmap
from src.ui.log_handler import QtLogHandler
from src.ui.page_registry import PAGE_DEFINITIONS
from src.ui.main_window_pages import MainWindowPagesMixin
from src.ui.main_window_settings import MainWindowSettingsMixin
from src.ui.main_window_models import MainWindowModelsMixin
from src.ui.main_window_widgets import QComboBox, HotkeyRecorderWidget, StatusPillLabel
from src.ui.provider_test_controller import ProviderTestController
from src.ui.file_transcription_controller import FileTranscriptionController
from src.logging_config import SensitiveDataFilter
from src.diagnostics import create_diagnostics_bundle
from src.hotkey.listener import canonicalize_hotkey

logger = logging.getLogger("PrimeDictate.MainWindow")
LOGO_PATH = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))

class MainWindow(MainWindowPagesMixin, MainWindowSettingsMixin, MainWindowModelsMixin, QMainWindow):
    request_toggle_dictation = Signal()
    hardware_detection_signal = Signal(object)
    PAGE_DEFINITIONS = PAGE_DEFINITIONS

    def __init__(self, app_controller=None, models=None, providers=None, history=None):
        super().__init__()
        self.app_controller = app_controller
        self.engine_manager = getattr(app_controller, "engine_manager", engine_manager)
        self.model_manager = models or model_manager
        self.provider_catalog = providers or provider_catalog
        self.provider_test_controller = ProviderTestController(self.provider_catalog, self)
        self.file_transcription_controller = FileTranscriptionController(self.engine_manager, self)
        self.history_store = history or HistoryStore()
        self.provider_model_cache = {}
        self.local_backend_capabilities = {}
        self.provider_test_controller.completed.connect(self._on_provider_test_completed)
        self.file_transcription_controller.progress.connect(self._on_file_progress)
        self.file_transcription_controller.completed.connect(self._on_file_finished)
        self.file_transcription_controller.error.connect(self._on_file_error)
        self.file_transcription_controller.cancelled.connect(self._on_file_cancelled)
        self.hardware_detection_signal.connect(self._apply_hardware_capabilities)
        set_language(config_manager.get("ui_language", "en"))
        self.setWindowTitle(translate("app.window_title"))
        self._geometry_ready = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(400)
        self._geometry_save_timer.timeout.connect(self._save_window_geometry)
        # Match the compact geometry selected during the final UI tuning pass.
        # Individual pages must remain usable at this first-run size.
        self.resize(960, 677)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(PREMIUM_STYLE)

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self._setup_flow_active = False
        self._preferred_sidebar_width = 255
        self._setup_ui()
        self._setup_accessibility()
        self.load_settings_to_ui()
        self._apply_ui_language()
        self._setup_log_stream()
        self._connect_model_manager_signals()
        self._start_hardware_detection()
        self._restore_window_geometry()
        self._geometry_ready = True

    def _setup_accessibility(self):
        self._apply_accessible_translations()
        for index, button in enumerate(self.nav_buttons):
            title_key, tooltip_key, _, _ = self.PAGE_DEFINITIONS[index]
            button.setAccessibleName(translate(title_key))
            button.setAccessibleDescription(translate(tooltip_key))

        self._shortcuts = []
        for index in range(len(self.PAGE_DEFINITIONS)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda i=index: self._set_page(i))
            self._shortcuts.append(shortcut)
        for sequence, callback in (
            ("Ctrl+S", self.save_ui_settings),
            ("Ctrl+F", self._focus_history_search),
            ("Escape", self.cancel_file_transcription),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _apply_accessible_translations(self):
        self.status_label.setAccessibleName(translate("a11y.application_status"))
        self.dictate_btn.setAccessibleName(translate("a11y.toggle_dictation"))
        self.save_btn.setAccessibleName(translate("a11y.save_all_settings"))
        self.quick_lang_combo.setAccessibleName(translate("a11y.quick_language"))
        self.pages.setAccessibleName(translate("a11y.application_pages"))

    def _focus_history_search(self):
        self._set_page(5)
        self.history_search.setFocus(Qt.ShortcutFocusReason)

    def _update_responsive_layout(self):
        if not hasattr(self, "sidebar_widget"):
            return
        target_width = 210 if self.width() < 1080 else self._preferred_sidebar_width
        self.sidebar_widget.setFixedWidth(target_width)
        if hasattr(self, "dashboard_hero_layout"):
            # The dashboard action card belongs in the intentionally reserved
            # right column, including at the compact first-run width.
            self.dashboard_hero_layout.setDirection(QBoxLayout.LeftToRight)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_layout()
        self._schedule_geometry_save()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_save()

    def _schedule_geometry_save(self):
        if getattr(self, "_geometry_ready", False) and not self.isMaximized() and not self.isMinimized():
            self._geometry_save_timer.start()

    def _save_window_geometry(self):
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        config_manager.update({"main_window_geometry": geometry})

    def _restore_window_geometry(self):
        geometry = config_manager.get("main_window_geometry", None)
        if not isinstance(geometry, str) or not geometry:
            return
        try:
            if not self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii"))):
                logger.warning("Stored main-window geometry could not be restored.")
        except (TypeError, ValueError):
            logger.warning("Stored main-window geometry is invalid.")

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        shell_layout = QHBoxLayout(central_widget)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebar")
        self.sidebar_widget.setFixedWidth(255)
        side_layout = QVBoxLayout(self.sidebar_widget)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.setSpacing(8)

        brand_layout = QHBoxLayout()
        logo_img = QLabel()
        logo_img.setFixedSize(48, 48)
        logo_img.setAlignment(Qt.AlignCenter)
        logo = app_mark_pixmap(46)
        if not logo.isNull():
            logo_img.setPixmap(logo)
        else:
            logo_img.setText("PD")
        brand_text = QVBoxLayout()
        title_label = QLabel("PrimeDictate")
        title_label.setObjectName("brandTitle")
        subtitle_label = QLabel("PRIVATE DICTATION")
        subtitle_label.setObjectName("brandCaption")
        brand_text.addWidget(title_label)
        brand_text.addWidget(subtitle_label)
        brand_layout.addWidget(logo_img)
        brand_layout.addLayout(brand_text)
        side_layout.addLayout(brand_layout)
        side_layout.addSpacing(24)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, (label_key, tooltip_key, _, _) in enumerate(self.PAGE_DEFINITIONS):
            button = QPushButton(translate(label_key))
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(translate(tooltip_key))
            button.clicked.connect(lambda checked=False, i=index: self._set_page(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            side_layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        side_layout.addStretch()

        self.quick_lang_combo = QComboBox()
        self.quick_lang_combo.setToolTip(translate("label.interface_language"))
        self.quick_lang_combo.addItem("🌐 English", "en")
        self.quick_lang_combo.addItem("🌐 Türkçe", "tr")
        current_ui_lang = get_language()
        q_idx = self.quick_lang_combo.findData(current_ui_lang)
        self.quick_lang_combo.setCurrentIndex(max(0, q_idx))
        self.quick_lang_combo.currentIndexChanged.connect(self._on_quick_lang_changed)
        side_layout.addWidget(self.quick_lang_combo)

        shell_layout.addWidget(self.sidebar_widget)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 18)
        content_layout.setSpacing(18)

        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        self.page_title = QLabel("Ana Sayfa")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Dikte çalışma alanınızın genel görünümü")
        self.page_subtitle.setObjectName("pageSubtitle")
        header_text.addWidget(self.page_title)
        header_text.addWidget(self.page_subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch()

        header_actions = QFrame()
        header_actions.setObjectName("headerActions")
        actions_layout = QHBoxLayout(header_actions)
        actions_layout.setContentsMargins(5, 5, 5, 5)
        actions_layout.setSpacing(6)

        self.status_label = StatusPillLabel("●  Hazır")
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedHeight(40)
        actions_layout.addWidget(self.status_label)

        self.dictate_btn = QPushButton("Dikte Et")
        self.dictate_btn.setObjectName("primaryAction")
        self.dictate_btn.setFixedHeight(40)
        self.dictate_btn.setMinimumWidth(150)
        self.dictate_btn.clicked.connect(self.on_dictate_btn_clicked)
        self._bind_translation(self.dictate_btn, "text", "action.dictate", self.dictate_btn.setText)
        actions_layout.addWidget(self.dictate_btn)

        header_layout.addWidget(header_actions)
        content_layout.addLayout(header_layout)

        self.pages = QStackedWidget()
        for _, _, _, factory_name in self.PAGE_DEFINITIONS:
            self.pages.addWidget(self._wrap_page(getattr(self, factory_name)()))
        content_layout.addWidget(self.pages, 1)

        self.footer_widget = QWidget()
        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_note = QLabel("Ayarlar bu cihazda saklanır. API anahtarları Windows kimlik kasasında korunur.")
        footer_note.setObjectName("mutedLabel")
        footer_layout.addWidget(footer_note)
        footer_layout.addStretch()
        self.save_btn = QPushButton("Ayarları Kaydet")
        self.save_btn.setObjectName("secondary_btn")
        self.save_btn.clicked.connect(self.save_ui_settings)
        self._bind_translation(self.save_btn, "text", "action.save_settings", self.save_btn.setText)
        footer_layout.addWidget(self.save_btn)
        content_layout.addWidget(self.footer_widget)
        shell_layout.addWidget(content, 1)

    def _wrap_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background-color: #0a0d12;")
        scroll.setWidget(page)
        return scroll

    def _set_page(self, index: int):
        if not 0 <= index < len(self.PAGE_DEFINITIONS):
            return
        title_key, _, subtitle_key, _ = self.PAGE_DEFINITIONS[index]
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.page_title.setText(translate(title_key))
        self.page_subtitle.setText(translate(subtitle_key))
        self.footer_widget.setVisible(index not in (0, len(self.PAGE_DEFINITIONS) - 1))
        self.dictate_btn.setVisible(index != 0)
        current_page = self.pages.currentWidget()
        if isinstance(current_page, QScrollArea):
            current_page.verticalScrollBar().setValue(0)
        setup_visible = self._setup_flow_active and not config_manager.get("setup_completed", False)
        if hasattr(self, "setup_engine_step"):
            self.setup_engine_step.setVisible(setup_visible and index == 1)
        if hasattr(self, "setup_audio_step"):
            self.setup_audio_step.setVisible(setup_visible and index == 4)

    def _on_quick_lang_changed(self, index: int):
        lang = self.quick_lang_combo.itemData(index)
        if lang and lang != get_language():
            set_language(lang)
            config_manager.set("ui_language", lang)
            config_manager.save_config()
            if hasattr(self, "ui_language_combo"):
                idx = self.ui_language_combo.findData(lang)
                if idx >= 0:
                    self.ui_language_combo.blockSignals(True)
                    self.ui_language_combo.setCurrentIndex(idx)
                    self.ui_language_combo.blockSignals(False)
            self._apply_ui_language()

    def _apply_ui_language(self):
        self.setWindowTitle(translate("app.window_title"))
        if hasattr(self, "quick_lang_combo"):
            self.quick_lang_combo.setToolTip(translate("label.interface_language"))
        for index, (label_key, tooltip_key, _, _) in enumerate(self.PAGE_DEFINITIONS):
            if index < len(self.nav_buttons):
                self.nav_buttons[index].setText(translate(label_key))
                self.nav_buttons[index].setToolTip(translate(tooltip_key))
                self.nav_buttons[index].setAccessibleName(translate(label_key))
                self.nav_buttons[index].setAccessibleDescription(translate(tooltip_key))
        self._apply_accessible_translations()
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
                self._retranslate_widget_property(widget, "text", widget.text, widget.setText)
            elif isinstance(widget, QGroupBox):
                self._retranslate_widget_property(widget, "title", widget.title, widget.setTitle)
            if isinstance(widget, (QLineEdit, QTextEdit)):
                self._retranslate_widget_property(
                    widget,
                    "placeholder",
                    widget.placeholderText,
                    widget.setPlaceholderText,
                )
            if widget.toolTip():
                self._retranslate_widget_property(widget, "tooltip", widget.toolTip, widget.setToolTip)
            if isinstance(widget, QComboBox) and widget not in (getattr(self, "quick_lang_combo", None), getattr(self, "ui_language_combo", None)):
                for index in range(widget.count()):
                    current = widget.itemText(index)
                    key_role = Qt.UserRole + 20
                    rendered_role = Qt.UserRole + 21
                    translation_key = widget.itemData(index, key_role)
                    rendered = widget.itemData(index, rendered_role)
                    if translation_key is None or (rendered is not None and current != rendered):
                        translation_key = legacy_translation_key(current) or ""
                        widget.setItemData(index, translation_key, key_role)
                    translated = translate(translation_key) if translation_key else current
                    widget.setItemText(index, translated)
                    widget.setItemData(index, translated, rendered_role)
        if hasattr(self, "about_version_label"):
            self.about_version_label.setText(f"{translate('label.version')} {__version__}  •  GPL-3.0")
        if hasattr(self, "lang_combo"):
            for index in range(self.lang_combo.count()):
                code = self.lang_combo.itemData(index)
                if code == "auto":
                    self.lang_combo.setItemText(index, translate("language.auto_detect"))
                elif code in STT_LANGUAGES:
                    self.lang_combo.setItemText(index, f"{self._language_name(code)} ({code})")
        self._set_page(self.pages.currentIndex())
        self._update_backend_fields()
        self._update_ai_provider_fields()
        self._update_admin_mode_status()

    @staticmethod
    def _retranslate_widget_property(widget, property_name, getter, setter):
        current = getter()
        legacy_key_property = f"i18nLegacyKey_{property_name}"
        rendered_key = f"i18nRendered_{property_name}"
        stable_key = widget.property(f"i18nKey_{property_name}")
        if stable_key:
            translated = translate(stable_key)
            setter(translated)
            widget.setProperty(rendered_key, translated)
            return
        translation_key = widget.property(legacy_key_property)
        rendered = widget.property(rendered_key)
        if translation_key is None or (rendered is not None and current != rendered):
            translation_key = legacy_translation_key(current) or ""
            widget.setProperty(legacy_key_property, translation_key)
        translated = translate(translation_key) if translation_key else current
        setter(translated)
        widget.setProperty(rendered_key, translated)

    @staticmethod
    def _bind_translation(widget, property_name, key, setter):
        widget.setProperty(f"i18nKey_{property_name}", key)
        translated = translate(key)
        setter(translated)
        widget.setProperty(f"i18nRendered_{property_name}", translated)

    def _test_api_key(self, provider: str, input_field: QLineEdit, status_label: QLabel, test_btn: QPushButton):
        key = input_field.text().strip()
        if not key:
            status_label.setText(translate("api.status.empty_key"))
            status_label.setStyleSheet("color: #ef4444; font-weight: 600;")
            return

        status_label.setText(translate("api.status.testing"))
        status_label.setStyleSheet("color: #38bdf8; font-weight: 600;")
        test_btn.setEnabled(False)

        self.provider_test_controller.start(
            provider,
            key,
            (status_label, test_btn, provider),
        )

    def _on_provider_test_completed(self, result, context):
        status_label, test_btn, provider = context
        self._on_api_key_test_result(result, status_label, test_btn, provider)

    def _on_api_key_test_result(self, result, status_label: QLabel, test_btn: QPushButton, provider: str):
        test_btn.setEnabled(True)
        if result.ok:
            self.provider_model_cache[provider] = {
                "stt": list(result.stt_models),
                "text": list(result.text_models),
            }
            if self.cloud_stt_combo.currentData() == provider and result.stt_models:
                selected = self.cloud_stt_model_combo.currentText()
                self.cloud_stt_model_combo.clear()
                self.cloud_stt_model_combo.addItems(result.stt_models)
                if selected:
                    self.cloud_stt_model_combo.setCurrentText(selected)
            if self.ai_provider_combo.currentData() == provider:
                self._update_ai_models(provider)
            status_label.setText(translate("api.status.success"))
            status_label.setStyleSheet("color: #10b981; font-weight: 600;")
        else:
            status_label.setText(translate("api.status.invalid_key", code=result.error_code))
            status_label.setStyleSheet("color: #ef4444; font-weight: 600;")

    def clear_file_transcription(self):
        self.file_path_input.clear()
        self.file_result_edit.clear()
        self.file_progress.setValue(0)
        self.file_segments = []
        self.status_label.setText(f"●  {translate('status.ready')}")

    def browse_audio_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            translate("file.dialog.select_title"),
            "",
            translate("file.dialog.media_filter"),
        )
        if file_name:
            self.file_path_input.setText(file_name)

    def start_file_transcription(self):
        if self.app_controller and getattr(self.app_controller.state, "value", "idle") != "idle":
            QMessageBox.warning(self, translate("dialog.operation_in_progress"), translate("file.error.finish_dictation_first"))
            return
        file_path = self.file_path_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, translate("dialog.error"), translate("file.error.invalid_selection"))
            return
        coordinator = getattr(self.app_controller, "operation_coordinator", None)
        if coordinator and not coordinator.try_begin("file_transcription"):
            QMessageBox.warning(self, translate("dialog.operation_in_progress"), translate("file.error.finish_dictation_first"))
            return

        self.transcribe_file_btn.setEnabled(False)
        self.cancel_transcribe_btn.setEnabled(True)
        self.dictate_btn.setEnabled(False)
        self.file_progress.setValue(10)
        self.file_result_edit.setText(translate("file.status.starting"))

        try:
            self.file_transcription_controller.start(file_path)
        except Exception:
            if coordinator:
                coordinator.finish("file_transcription")
            self.transcribe_file_btn.setEnabled(True)
            self.cancel_transcribe_btn.setEnabled(False)
            self.dictate_btn.setEnabled(True)
            raise

    def _finish_file_operation(self):
        coordinator = getattr(self.app_controller, "operation_coordinator", None)
        if coordinator:
            coordinator.finish("file_transcription")

    def cancel_file_transcription(self):
        if self.file_transcription_controller.cancel():
            self.cancel_transcribe_btn.setEnabled(False)
            self.status_label.setText(translate("file.status.cancelling"))

    def _on_file_progress(self, percent: int, msg: str):
        self.file_progress.setValue(percent)
        self.status_label.setText(translate("file.status.transcribing", detail=msg))

    def _on_file_finished(self, file_path: str, text: str):
        self._finish_file_operation()
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(100)
        self.file_result_edit.setText(text)
        self.file_segments = list(self.file_transcription_controller.segments)
        self.update_transcription_metadata(self.engine_manager.last_transcription_info)
        processing_info = self.engine_manager.last_transcription_info.get("text_processing", {})
        if processing_info.get("fallback_used"):
            self.status_label.setText(translate("file.status.complete_with_fallback"))
        else:
            self.status_label.setText(translate("file.status.complete"))
        QMessageBox.information(self, translate("dialog.success"), translate("file.dialog.complete"))

    def _on_file_error(self, err: str):
        self._finish_file_operation()
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        QMessageBox.critical(self, translate("dialog.error"), translate("file.error.transcription", detail=err))

    def _on_file_cancelled(self):
        self._finish_file_operation()
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        self.status_label.setText(translate("file.status.cancelled"))

    def save_file_text(self):
        text = self.file_result_edit.toPlainText()
        if not text:
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            translate("file.dialog.save_title"),
            "transcription.txt",
            translate("file.dialog.export_filter"),
        )
        if file_name:
            extension = os.path.splitext(file_name)[1].casefold()
            if extension == ".srt":
                output = segments_to_srt(getattr(self, "file_segments", []))
            elif extension == ".vtt":
                output = segments_to_vtt(getattr(self, "file_segments", []))
            elif extension == ".json":
                output = segments_to_json(getattr(self, "file_segments", []))
            else:
                output = text
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(output)
            QMessageBox.information(self, translate("dialog.saved"), translate("file.dialog.saved_path", path=file_name))

    def _setup_log_stream(self):
        handler = QtLogHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        handler.addFilter(SensitiveDataFilter())
        handler.log_signal.connect(self._append_log)
        logging.getLogger().addHandler(handler)

    def _append_log(self, text: str):
        self.log_console.append(text)

    def test_audio_input(self):
        devices = AudioRecorder.get_input_devices()
        msg = f"{translate('microphone.found_count', count=len(devices))}\n\n"
        for d in devices:
            msg += f"• [{d['index']}] {d['name']} ({d['default_samplerate']}Hz, {d['channels']} ch)\n"
        QMessageBox.information(self, translate("microphone.diagnostics_title"), msg)

    def export_diagnostics_bundle(self):
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            translate("diagnostics.dialog.export_title"),
            "PrimeDictate-Diagnostics.zip",
            translate("diagnostics.dialog.zip_filter"),
        )
        if not file_name:
            return
        if not file_name.casefold().endswith(".zip"):
            file_name += ".zip"
        try:
            create_diagnostics_bundle(
                file_name,
                config_manager,
                capabilities=self.local_backend_capabilities,
                log_dir=os.path.join(APP_DIR, "logs"),
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                translate("dialog.error"),
                translate("diagnostics.dialog.error", detail=error),
            )
            return
        QMessageBox.information(
            self,
            translate("dialog.saved"),
            translate("diagnostics.dialog.saved", path=file_name),
        )

    def _refresh_dashboard(self):
        setup_completed = config_manager.get("setup_completed", False)
        self.dashboard_metrics_widget.setVisible(setup_completed)
        self.dashboard_onboarding.setVisible(not setup_completed)
        self.dictate_btn.setEnabled(setup_completed)
        self.hero_dictate_btn.setEnabled(setup_completed)
        if not setup_completed:
            self.hero_title.setText(translate("dashboard.setup.title"))
            self.hero_caption.setText(translate("dashboard.setup.caption"))
            self.hero_state.setText(translate("dashboard.setup.empty_state"))
            return

        self.hero_title.setText(translate("dashboard.hero.title"))
        self.hero_caption.setText(translate("dashboard.hero.caption"))
        backend = config_manager.get("stt_backend", "cpu")
        self.dashboard_engine.setText(translate(f"engine.label.{backend}"))
        if backend == "cloud":
            cloud_provider = config_manager.get("cloud_stt_provider", "groq")
            dashboard_model = config_manager.get(f"stt_model_{cloud_provider}", cloud_provider)
        else:
            dashboard_model = config_manager.get("model_size", "base")
        self.dashboard_model.setText(dashboard_model)
        self.dashboard_hotkey.setText(config_manager.get("hotkey", "ctrl+alt+d").upper())
        privacy_key = "privacy.cloud" if backend == "cloud" else "privacy.local"
        if config_manager.get("allow_cloud_fallback", False) and backend != "cloud":
            privacy_key = "privacy.local_fallback"
        self.dashboard_privacy.setText(translate(privacy_key))
        language = config_manager.get("language", "tr")
        language_text = translate("language.auto_detect") if language == "auto" else f"{self._language_name(language)} ({language})"
        self.dashboard_language.setText(language_text)

    def update_transcription_metadata(self, info: dict):
        if not isinstance(info, dict):
            return
        inference_device = info.get("inference_device")
        if inference_device:
            self.dashboard_engine.setText(str(inference_device))
        language = info.get("detected_language") if isinstance(info, dict) else None
        if not language:
            return
        label = f"{self._language_name(language)} ({language})"
        probability = info.get("language_probability")
        if isinstance(probability, (float, int)):
            label += f" • {probability:.0%}"
        self.dashboard_language.setText(label)

    def add_history_entry(self, text: str):
        if not config_manager.get("history_enabled", True):
            return
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.history_store.add({"time": now_str, "text": text})
        self.refresh_history_list()

    def refresh_history_list(self):
        self.history_list.clear()
        history = self.history_store.entries()
        query = self.history_search.text().strip().casefold() if hasattr(self, "history_search") else ""
        visible_count = 0
        for item in history:
            raw_text = item.get("text", "")
            if query and query not in raw_text.casefold():
                continue
            display_text = f"{item.get('time', '')}   {raw_text}"
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.UserRole, raw_text)
            list_item.setData(Qt.UserRole + 1, item.get("time", ""))
            self.history_list.addItem(list_item)
            visible_count += 1
        self.history_summary.setText(translate("history.summary", visible=visible_count, total=len(history)))
        self.history_empty_label.setText(
            translate("history.no_matches") if history and query else translate("history.empty")
        )
        self.history_empty_label.setVisible(visible_count == 0)
        self.history_list.setVisible(visible_count > 0)
        self._update_history_actions()

    def _update_history_actions(self):
        has_selection = bool(getattr(self, "history_list", None) and self.history_list.currentItem())
        if hasattr(self, "history_copy_btn"):
            self.history_copy_btn.setEnabled(has_selection)
        if hasattr(self, "history_delete_btn"):
            self.history_delete_btn.setEnabled(has_selection)

    def copy_selected_history(self):
        current_item = self.history_list.currentItem()
        if current_item:
            clean_text = current_item.data(Qt.UserRole) or current_item.text()
            QApplication.clipboard().setText(clean_text)
            QMessageBox.information(self, translate("dialog.copied"), translate("clipboard.text_copied"))

    def delete_selected_history(self):
        current_item = self.history_list.currentItem()
        if not current_item:
            return
        answer = QMessageBox.question(
            self,
            translate("history.delete_title"),
            translate("history.delete_confirm"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        target_text = current_item.data(Qt.UserRole) or ""
        target_time = current_item.data(Qt.UserRole + 1) or ""
        self.history_store.delete(target_text, target_time)
        self.refresh_history_list()

    def clear_history(self):
        answer = QMessageBox.question(
            self,
            translate("history.clear_title"),
            translate("history.clear_confirm"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.history_store.clear()
        self.refresh_history_list()

    def _start_setup_flow(self):
        self._setup_flow_active = True
        self.setup_engine_step.setVisible(True)
        self._set_page(1)

    def on_dictate_btn_clicked(self):
        self.request_toggle_dictation.emit()

    def set_recording_state(self, is_recording: bool):
        message = translate("status.listening" if is_recording else "status.ready")
        self.set_app_state("recording" if is_recording else "idle", message)

    def set_app_state(self, state: str, message: str):
        localized_message = message
        self.status_label.setText(f"●  {localized_message}")
        self.hero_state.setText(localized_message)
        setup_completed = config_manager.get("setup_completed", False)
        self.dictate_btn.setEnabled(setup_completed and state in {"idle", "recording"})
        self.hero_dictate_btn.setEnabled(setup_completed and state in {"idle", "recording"})
        self.dictate_btn.setObjectName("dangerAction" if state == "recording" else "primaryAction")
        dictate_key = "action.stop" if state == "recording" else "action.dictate"
        self._bind_translation(self.dictate_btn, "text", dictate_key, self.dictate_btn.setText)
        self.hero_dictate_btn.setObjectName("dangerAction" if state == "recording" else "primaryAction")
        self._bind_translation(self.hero_dictate_btn, "text", dictate_key, self.hero_dictate_btn.setText)
        self.hero_dictate_btn.style().unpolish(self.hero_dictate_btn)
        self.hero_dictate_btn.style().polish(self.hero_dictate_btn)
        self.dictate_btn.style().unpolish(self.dictate_btn)
        self.dictate_btn.style().polish(self.dictate_btn)

        colors = {
            "idle": ("#1a160e", "#3d321d", "#d2b879"),
            "recording": ("#221215", "#52232a", "#e5828d"),
            "transcribing": ("#1c1810", "#483c22", "#e0c586"),
            "success": ("#1a160e", "#3d321d", "#d2b879"),
            "error": ("#241215", "#58252c", "#e5828d"),
        }
        bg, border, color = colors.get(state, colors["idle"])
        self.status_label.setStyleSheet(
            f"background-color:{bg}; border:1px solid {border}; border-radius:9px;"
            f"color:{color}; font-weight:600; padding:0 14px;"
        )

    def show_and_raise(self):
        self.show()
        self.activateWindow()

    def show_page(self, index: int):
        self._set_page(index)
        self.show_and_raise()

    def quit_app(self):
        if self.app_controller:
            self.app_controller.quit()
        else:
            QApplication.quit()

    def prepare_shutdown(self, timeout_ms=10000):
        """Cooperatively stop owned QThreads before the application is destroyed."""
        if not self.file_transcription_controller.shutdown(timeout_ms):
            logger.error("File transcription worker did not stop before shutdown timeout.")
            return False
        return True

    @property
    def transcribe_worker(self):
        """Compatibility facade for integrations that inspect the active worker."""
        return self.file_transcription_controller.worker

    @transcribe_worker.setter
    def transcribe_worker(self, worker):
        self.file_transcription_controller.worker = worker

    def closeEvent(self, event):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            self.quit_app()
            return
        event.ignore()
        self.hide()
