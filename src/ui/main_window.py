import os
import datetime
import logging
import threading
import weakref
import shiboken6
from PySide6.QtCore import Qt, Signal, QUrl, QTimer
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QComboBox as QtQComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QButtonGroup, QStackedWidget, QScrollArea,
    QFrame, QGridLayout, QSystemTrayIcon
)

class QComboBox(QtQComboBox):
    def wheelEvent(self, event):
        event.ignore()

from src import __version__
from src.config import APP_DIR, STT_LANGUAGES, STT_LANGUAGE_NAMES_TR, config_manager, get_resource_path
from src.i18n import get_language, legacy_translation_key, set_language, translate
from src.metadata import EMAIL, REPOSITORY, STUDIO, WEBSITE
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import model_manager, supported_models
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.hardware_capabilities import detect_local_backends, recommended_local_backend
from src.engine.file_transcriber import FileTranscribeWorker, segments_to_json, segments_to_srt, segments_to_vtt
from src.engine.engine_manager import engine_manager
from src.engine.provider_catalog import provider_catalog
from src.startup import configure_start_with_windows
from src.ui.styles import PREMIUM_STYLE, get_styled_app
from src.ui.brand import app_mark_pixmap
from src.ui.log_handler import QtLogHandler
from src.ui.page_registry import PAGE_DEFINITIONS
from src.logging_config import SensitiveDataFilter
from src.diagnostics import create_diagnostics_bundle
from src.hotkey.listener import canonicalize_hotkey

logger = logging.getLogger("PrimeDictate.MainWindow")
LOGO_PATH = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))

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

class MainWindow(QMainWindow):
    request_toggle_dictation = Signal()
    api_test_signal = Signal(object, object, object, str)
    hardware_detection_signal = Signal(object)
    PAGE_DEFINITIONS = PAGE_DEFINITIONS

    def __init__(self, app_controller=None, models=None, providers=None):
        super().__init__()
        self.app_controller = app_controller
        self.engine_manager = getattr(app_controller, "engine_manager", engine_manager)
        self.model_manager = models or model_manager
        self.provider_catalog = providers or provider_catalog
        self.provider_model_cache = {}
        self.local_backend_capabilities = {}
        self.api_test_signal.connect(self._on_api_key_test_result)
        self.hardware_detection_signal.connect(self._apply_hardware_capabilities)
        set_language(config_manager.get("ui_language", "en"))
        self.setWindowTitle(translate("app.window_title"))
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(PREMIUM_STYLE)

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self.transcribe_worker = None
        self._setup_flow_active = False
        self._preferred_sidebar_width = 255
        self._setup_ui()
        self._setup_accessibility()
        self.load_settings_to_ui()
        self._apply_ui_language()
        self._setup_log_stream()
        self._connect_model_manager_signals()
        self._start_hardware_detection()

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_layout()

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
        if os.path.exists(LOGO_PATH):
            logo_img.setPixmap(app_mark_pixmap(46))
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

        self.status_label = QLabel("●  Hazır")
        self.status_label.setObjectName("statusPill")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedHeight(40)
        self.status_label.setMinimumWidth(112)
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
        self.footer_widget.setVisible(index != len(self.PAGE_DEFINITIONS) - 1)
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

    def _create_metric_card(self, label: str, value: str, translation_key: str = None) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        caption = QLabel(label.upper())
        caption.setObjectName("metricLabel")
        if translation_key:
            self._bind_translation(caption, "text", translation_key, caption.setText)
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        layout.addWidget(caption)
        layout.addWidget(value_label)
        return card, value_label

    @staticmethod
    def _language_name(code: str) -> str:
        names = STT_LANGUAGE_NAMES_TR if get_language() == "tr" else STT_LANGUAGES
        return names.get(code, STT_LANGUAGES.get(code, code))

    def _create_dashboard_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 24, 26, 24)
        hero_text = QVBoxLayout()
        self.hero_title = QLabel("Konuşun. Gerisini Prime Dictate halletsin.")
        self.hero_title.setObjectName("heroTitle")
        self.hero_caption = QLabel("Global kısayolunuzla herhangi bir uygulamada dikteye başlayın.")
        self.hero_caption.setObjectName("heroCaption")
        self.hero_caption.setWordWrap(True)
        self.hero_state = QLabel("Sistem hazır")
        self.hero_state.setObjectName("mutedLabel")
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(self.hero_caption)
        hero_text.addSpacing(10)
        hero_text.addWidget(self.hero_state)
        hero_layout.addLayout(hero_text, 1)

        hero_focus = QFrame()
        hero_focus.setObjectName("heroFocus")
        focus_layout = QVBoxLayout(hero_focus)
        focus_layout.setContentsMargins(20, 16, 20, 16)
        focus_layout.setSpacing(5)
        focus_eyebrow = QLabel(translate("dashboard.ready_eyebrow"))
        focus_eyebrow.setObjectName("heroFocusEyebrow")
        self._bind_translation(focus_eyebrow, "text", "dashboard.ready_eyebrow", focus_eyebrow.setText)
        self.dashboard_hotkey = QLabel("CTRL + ALT + D")
        self.dashboard_hotkey.setObjectName("heroHotkey")
        focus_hint = QLabel(translate("dashboard.hotkey_hint"))
        focus_hint.setObjectName("mutedLabel")
        focus_hint.setWordWrap(True)
        self._bind_translation(focus_hint, "text", "dashboard.hotkey_hint", focus_hint.setText)
        self.hero_dictate_btn = QPushButton(translate("action.dictate"))
        self.hero_dictate_btn.setObjectName("primaryAction")
        self.hero_dictate_btn.setFixedHeight(42)
        self.hero_dictate_btn.clicked.connect(self.on_dictate_btn_clicked)
        self.hero_dictate_btn.setAccessibleName(translate("a11y.toggle_dictation"))
        self._bind_translation(self.hero_dictate_btn, "text", "action.dictate", self.hero_dictate_btn.setText)
        focus_layout.addWidget(focus_eyebrow)
        focus_layout.addWidget(self.dashboard_hotkey)
        focus_layout.addWidget(focus_hint)
        focus_layout.addSpacing(7)
        focus_layout.addWidget(self.hero_dictate_btn)
        hero_layout.addWidget(hero_focus)
        layout.addWidget(hero)

        self.dashboard_metrics_widget = QWidget()
        metrics = QGridLayout(self.dashboard_metrics_widget)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(12)
        engine_card, self.dashboard_engine = self._create_metric_card("Aktif Motor", "Yerel CPU", "dashboard.metric.engine")
        model_card, self.dashboard_model = self._create_metric_card("Model", "base", "dashboard.metric.model")
        privacy_card, self.dashboard_privacy = self._create_metric_card("Gizlilik", "Yerel", "dashboard.metric.privacy")
        language_card, self.dashboard_language = self._create_metric_card("Konuşma Dili", "Turkish (tr)", "dashboard.metric.language")
        metrics.addWidget(engine_card, 0, 0)
        metrics.addWidget(model_card, 0, 1)
        metrics.addWidget(language_card, 1, 0)
        metrics.addWidget(privacy_card, 1, 1)
        layout.addWidget(self.dashboard_metrics_widget)

        self.dashboard_onboarding = QFrame()
        self.dashboard_onboarding.setObjectName("onboardingCard")
        onboarding_layout = QVBoxLayout(self.dashboard_onboarding)
        onboarding_layout.setContentsMargins(22, 20, 22, 20)
        onboarding_layout.setSpacing(10)
        onboarding_eyebrow = QLabel("BAŞLANGIÇ")
        onboarding_eyebrow.setObjectName("sectionEyebrow")
        onboarding_title = QLabel("Prime Dictate'i kullanıma hazırlayın")
        onboarding_title.setObjectName("onboardingTitle")
        onboarding_text = QLabel(
            "Henüz etkin bir dikte yapılandırması yok. STT motorunu, konuşma dilini ve mikrofonu "
            "seçtikten sonra gerçek çalışma özeti burada gösterilecek."
        )
        onboarding_text.setObjectName("sectionDescription")
        onboarding_text.setWordWrap(True)
        onboarding_steps = QLabel("1  STT motorunu seçin     2  Modeli ve dili belirleyin     3  Ayarları kaydedin")
        onboarding_steps.setObjectName("onboardingSteps")
        onboarding_steps.setWordWrap(True)
        onboarding_action = QPushButton("Kurulumu Başlat")
        onboarding_action.setObjectName("primaryAction")
        onboarding_action.setFixedHeight(40)
        onboarding_action.clicked.connect(self._start_setup_flow)
        onboarding_layout.addWidget(onboarding_eyebrow)
        onboarding_layout.addWidget(onboarding_title)
        onboarding_layout.addWidget(onboarding_text)
        onboarding_layout.addWidget(onboarding_steps)
        action_row = QHBoxLayout()
        action_row.addWidget(onboarding_action)
        action_row.addStretch()
        onboarding_layout.addLayout(action_row)
        layout.addWidget(self.dashboard_onboarding)
        layout.addStretch()
        return widget

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.setup_engine_step = QFrame()
        self.setup_engine_step.setObjectName("onboardingCard")
        setup_layout = QHBoxLayout(self.setup_engine_step)
        setup_layout.setContentsMargins(18, 14, 18, 14)
        setup_text = QLabel("Kurulum 1/2 • Motoru, modeli ve konuşma dilini belirleyin.")
        setup_text.setObjectName("sectionDescription")
        setup_text.setWordWrap(True)
        setup_next = QPushButton("Mikrofon ve kısayola devam et")
        setup_next.setObjectName("primaryAction")
        setup_next.clicked.connect(lambda: self._set_page(4))
        setup_layout.addWidget(setup_text, 1)
        setup_layout.addWidget(setup_next)
        self.setup_engine_step.setVisible(False)
        layout.addWidget(self.setup_engine_step)

        pipeline = QFrame()
        pipeline.setObjectName("pipelineCard")
        pipeline_layout = QHBoxLayout(pipeline)
        pipeline_layout.setContentsMargins(16, 16, 16, 16)
        pipeline_layout.setSpacing(10)
        stt_stage = QLabel("1  SES → METİN\nZorunlu • Yerel veya bulut STT")
        stt_stage.setObjectName("pipelineStage")
        arrow = QLabel("→")
        arrow.setObjectName("pipelineArrow")
        cleanup_stage = QLabel("2  METİN DÜZENLEME\nİsteğe bağlı • Ayrı yöntem ve model")
        cleanup_stage.setObjectName("pipelineStage")
        pipeline_layout.addWidget(stt_stage, 1)
        pipeline_layout.addWidget(arrow)
        pipeline_layout.addWidget(cleanup_stage, 1)
        layout.addWidget(pipeline)

        engine_group = QGroupBox("1. Ses → Metin (STT)")
        engine_layout = QVBoxLayout(engine_group)
        engine_layout.setSpacing(14)

        engine_intro = QLabel(
            "Bu aşama yalnızca konuşmayı yazıya çevirir. Yerel seçenekler sesi cihazda işler; "
            "bulut seçeneği ses kaydını seçtiğiniz servise gönderir."
        )
        engine_intro.setObjectName("sectionDescription")
        engine_intro.setWordWrap(True)
        engine_layout.addWidget(engine_intro)

        # 1. Spoken Language (Konuşma Dili - En Üstte)
        h_lang = QHBoxLayout()
        language_label = QLabel("Konuşma dili")
        language_label.setObjectName("fieldLabel")
        h_lang.addWidget(language_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Otomatik algıla", "auto")
        featured_languages = ["tr", "en", "de", "fr", "es", "it", "pt", "ar", "ru", "zh", "ja", "ko"]
        for code in featured_languages:
            self.lang_combo.addItem(f"{self._language_name(code)} ({code})", code)
        for code, name in sorted(STT_LANGUAGES.items(), key=lambda item: item[1]):
            if code not in featured_languages:
                self.lang_combo.addItem(f"{self._language_name(code)} ({code})", code)
        h_lang.addWidget(self.lang_combo, 1)
        engine_layout.addLayout(h_lang)

        # 2. STT Backend Location
        h_backend = QHBoxLayout()
        backend_label = QLabel("STT çalışma konumu")
        backend_label.setObjectName("fieldLabel")
        h_backend.addWidget(backend_label)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Yerel GPU • Vulkan (AMD / Intel / NVIDIA)", "vulkan")
        self.backend_combo.addItem("Yerel GPU • CUDA (NVIDIA)", "cuda")
        self.backend_combo.addItem("Yerel CPU • Özel ve uyumlu", "cpu")
        self.backend_combo.addItem("Bulut STT • Groq / OpenAI / Gemini", "cloud")
        self.backend_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.backend_combo.setMinimumContentsLength(24)
        self.backend_combo.setToolTip("Vulkan için uyumlu ekran kartı sürücüsü ve Vulkan ile derlenmiş whisper.cpp gerekir.")
        h_backend.addWidget(self.backend_combo, 1)
        engine_layout.addLayout(h_backend)

        self.backend_description = QLabel()
        self.backend_description.setObjectName("infoNote")
        self.backend_description.setWordWrap(True)
        engine_layout.addWidget(self.backend_description)

        # 3. Local STT Configuration & Unified Model Sub-card
        self.local_stt_widget = QFrame()
        self.local_stt_widget.setObjectName("subCard")
        local_layout = QVBoxLayout(self.local_stt_widget)
        local_layout.setContentsMargins(14, 13, 14, 13)
        local_layout.setSpacing(12)
        local_title = QLabel("YEREL WHISPER YAPILANDIRMASI VE MODEL YÖNETİMİ")
        local_title.setObjectName("sectionEyebrow")
        local_layout.addWidget(local_title)

        h2 = QHBoxLayout()
        model_label = QLabel("Yerel model boyutu")
        model_label.setObjectName("fieldLabel")
        h2.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItem("tiny • ~75 MB (En hızlı, çok hafif)", "tiny")
        self.model_combo.addItem("base • ~145 MB (Hızlı, temel doğruluk)", "base")
        self.model_combo.addItem("small • ~490 MB (Dengeli performans)", "small")
        self.model_combo.addItem("medium • ~1.5 GB (Yüksek doğruluk)", "medium")
        self.model_combo.addItem("large-v3-turbo • ~1.6 GB (Hızlı & yüksek doğruluk)", "large-v3-turbo")
        self.model_combo.addItem("large-v3 • ~3.1 GB (Maksimum doğruluk)", "large-v3")
        self.model_combo.currentIndexChanged.connect(lambda: self.check_selected_model_status())
        h2.addWidget(self.model_combo, 1)
        local_layout.addLayout(h2)

        model_hint = QLabel(
            "Küçük modeller daha hızlı ve hafiftir; büyük modeller daha fazla bellek kullanır, "
            "genellikle daha yüksek doğruluk sağlar. Bu seçim yalnızca yerel motorları etkiler."
        )
        model_hint.setObjectName("mutedLabel")
        model_hint.setWordWrap(True)
        local_layout.addWidget(model_hint)

        # Unified Model Download / Progress Status Frame
        self.model_group = QFrame()
        self.model_group.setObjectName("subCard")
        m_layout = QVBoxLayout(self.model_group)
        m_layout.setContentsMargins(12, 10, 12, 10)
        m_layout.setSpacing(8)

        self.model_status_label = QLabel("Model Durumu Kontrol Ediliyor...")
        self.model_status_label.setWordWrap(True)
        self.model_status_label.setStyleSheet("color: #cbd5e1; font-weight: 500;")
        m_layout.addWidget(self.model_status_label)

        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.model_progress.setTextVisible(True)
        m_layout.addWidget(self.model_progress)

        h_dl = QHBoxLayout()
        self.download_model_btn = QPushButton("Seçilen Modeli İndir")
        self.download_model_btn.clicked.connect(self.download_selected_model)
        h_dl.addWidget(self.download_model_btn)
        h_dl.addStretch()
        m_layout.addLayout(h_dl)
        local_layout.addWidget(self.model_group)

        # Vulkan Runtime Widget
        self.vulkan_runtime_widget = QWidget()
        vulkan_layout = QVBoxLayout(self.vulkan_runtime_widget)
        vulkan_layout.setContentsMargins(0, 4, 0, 0)
        runtime_row = QHBoxLayout()
        runtime_label = QLabel("Vulkan runtime")
        runtime_label.setObjectName("fieldLabel")
        runtime_row.addWidget(runtime_label)
        self.vulkan_executable_input = QLineEdit()
        self.vulkan_executable_input.setPlaceholderText("Dahili runtime otomatik kullanılır; özel whisper-cli.exe isteğe bağlıdır")
        runtime_row.addWidget(self.vulkan_executable_input, 1)
        runtime_browse_btn = QPushButton("Özel Runtime Seç")
        runtime_browse_btn.setObjectName("secondary_btn")
        runtime_browse_btn.clicked.connect(self.browse_vulkan_runtime)
        runtime_row.addWidget(runtime_browse_btn)
        vulkan_layout.addLayout(runtime_row)
        self.vulkan_status_label = QLabel("Vulkan runtime kontrol edilmedi")
        self.vulkan_status_label.setObjectName("mutedLabel")
        vulkan_layout.addWidget(self.vulkan_status_label)
        local_layout.addWidget(self.vulkan_runtime_widget)

        engine_layout.addWidget(self.local_stt_widget)

        # 4. Cloud STT Configuration Card
        self.cloud_stt_widget = QFrame()
        self.cloud_stt_widget.setObjectName("subCard")
        cloud_layout = QVBoxLayout(self.cloud_stt_widget)
        cloud_layout.setContentsMargins(14, 13, 14, 13)
        cloud_layout.setSpacing(10)
        self.cloud_stt_title = QLabel("BULUT STT YAPILANDIRMASI")
        self.cloud_stt_title.setObjectName("sectionEyebrow")
        cloud_layout.addWidget(self.cloud_stt_title)
        cloud_provider_row = QHBoxLayout()
        cloud_provider_label = QLabel("Transkripsiyon servisi")
        cloud_provider_label.setObjectName("fieldLabel")
        cloud_provider_row.addWidget(cloud_provider_label)
        self.cloud_stt_combo = QComboBox()
        self.cloud_stt_combo.addItem("Groq Whisper", "groq")
        self.cloud_stt_combo.addItem("OpenAI Transcribe", "openai")
        self.cloud_stt_combo.addItem("Google Gemini Audio", "gemini")
        cloud_provider_row.addWidget(self.cloud_stt_combo, 1)
        cloud_layout.addLayout(cloud_provider_row)
        cloud_model_row = QHBoxLayout()
        cloud_model_label = QLabel("Bulut STT modeli")
        cloud_model_label.setObjectName("fieldLabel")
        cloud_model_row.addWidget(cloud_model_label)
        self.cloud_stt_model_combo = QComboBox()
        cloud_model_row.addWidget(self.cloud_stt_model_combo, 1)
        cloud_layout.addLayout(cloud_model_row)
        self.cloud_provider_note = QLabel()
        self.cloud_provider_note.setObjectName("infoNote")
        self.cloud_provider_note.setWordWrap(True)
        cloud_layout.addWidget(self.cloud_provider_note)
        self.cloud_stt_note = QLabel()
        self.cloud_stt_note.setObjectName("warningNote")
        self.cloud_stt_note.setWordWrap(True)
        cloud_layout.addWidget(self.cloud_stt_note)
        engine_layout.addWidget(self.cloud_stt_widget)
        self.cloud_stt_combo.currentIndexChanged.connect(self._update_cloud_stt_models)

        # 5. Engine Failover Sub-card (Fallback)
        fallback_card = QFrame()
        fallback_card.setObjectName("subCard")
        fallback_layout = QVBoxLayout(fallback_card)
        fallback_layout.setContentsMargins(14, 11, 14, 11)
        self.cloud_fallback_cb = QCheckBox("Yerel motor başarısızsa buluta geçmeme izin ver")
        self.cloud_fallback_cb.setToolTip("Açıldığında ses kaydı, yalnızca yerel işlem başarısız olursa seçili bulut STT servisine gönderilebilir.")
        self.cloud_fallback_cb.toggled.connect(self._update_backend_fields)
        fallback_layout.addWidget(self.cloud_fallback_cb)
        engine_layout.addWidget(fallback_card)

        self.backend_combo.currentIndexChanged.connect(self._update_backend_fields)
        layout.addWidget(engine_group)
        layout.addStretch()
        return widget

    def _update_backend_fields(self, *_):
        backend = self.backend_combo.currentData()
        is_cloud = backend == "cloud"
        uses_fallback = not is_cloud and self.cloud_fallback_cb.isChecked()
        self.backend_description.setText(translate(f"engine.description.{backend}"))
        capability = getattr(self, "local_backend_capabilities", {}).get(backend)
        if capability and capability.available:
            self.backend_description.setText(
                f"{self.backend_description.text()}\n{translate('label.detected_device', device=capability.device_name)}"
            )
        self.local_stt_widget.setVisible(not is_cloud)
        self.cloud_stt_widget.setVisible(is_cloud or uses_fallback)
        self.model_group.setVisible(not is_cloud)
        self.vulkan_runtime_widget.setVisible(backend == "vulkan")
        self.cloud_fallback_cb.setEnabled(not is_cloud)
        if is_cloud:
            self.cloud_stt_title.setText(translate("cloud.title.active_engine"))
            self.cloud_stt_note.setText(translate("cloud.note.active"))
        else:
            self.cloud_stt_title.setText(translate("cloud.title.fallback_engine"))
            self.cloud_stt_note.setText(translate("cloud.note.fallback"))
        if backend == "vulkan":
            capability = getattr(self, "local_backend_capabilities", {}).get("vulkan")
            if capability:
                self.vulkan_status_label.setText(capability.detail)
                self.vulkan_status_label.setStyleSheet("color: #69ddb0;" if capability.available else "color: #ff8794;")
            else:
                self.vulkan_status_label.setText(translate("hardware.detecting"))
        if not is_cloud and hasattr(self, "model_combo"):
            available_models = supported_models(backend)
            for index in range(self.model_combo.count()):
                model_item = self.model_combo.model().item(index)
                if model_item is not None:
                    model_item.setEnabled(self.model_combo.itemData(index) in available_models)
            if self.model_combo.currentData() not in available_models:
                preferred = "large-v3-turbo" if "large-v3-turbo" in available_models else "base"
                self._safe_combo_set_data(self.model_combo, preferred, 1)
        if not is_cloud and hasattr(self, "model_combo"):
            self.check_selected_model_status()

    def _update_cloud_stt_models(self, *_):
        provider = self.cloud_stt_combo.currentData()
        models = {
            "groq": ["whisper-large-v3-turbo", "whisper-large-v3"],
            "openai": ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"],
            "gemini": ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro"],
        }
        saved_model = config_manager.get(f"stt_model_{provider}", "")
        self.cloud_stt_model_combo.clear()
        self.cloud_stt_model_combo.addItems(models.get(provider, []))
        if saved_model:
            self.cloud_stt_model_combo.setCurrentText(saved_model)
        self.cloud_provider_note.setText(translate(f"cloud.note.{provider}"))

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

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        cleanup_group = QGroupBox("2. Metin Düzenleme (İsteğe Bağlı)")
        c_layout = QVBoxLayout(cleanup_group)
        c_layout.setSpacing(12)

        cleanup_intro = QLabel(
            "Bu aşama ses tanımadan sonra çalışır. Kapalıysa STT çıktısı hiçbir düzenleme yapılmadan kullanılır; "
            "açıksa seçtiğiniz yerel veya bulut yöntemi metni temizler ve biçimlendirir."
        )
        cleanup_intro.setObjectName("sectionDescription")
        cleanup_intro.setWordWrap(True)
        c_layout.addWidget(cleanup_intro)

        self.ai_cleanup_cb = QCheckBox("STT çıktısını otomatik düzenle")
        c_layout.addWidget(self.ai_cleanup_cb)

        self.ai_processing_settings = QFrame()
        self.ai_processing_settings.setObjectName("subCard")
        processing_layout = QVBoxLayout(self.ai_processing_settings)
        processing_layout.setContentsMargins(14, 13, 14, 13)
        processing_layout.setSpacing(10)

        h1 = QHBoxLayout()
        method_label = QLabel("Düzenleme yöntemi")
        method_label.setObjectName("fieldLabel")
        h1.addWidget(method_label)
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("Kural tabanlı • Yerel, hızlı, LLM kullanmaz", "rule_based")
        self.ai_provider_combo.addItem("Ollama / LM Studio • Yerel LLM", "custom_ollama")
        self.ai_provider_combo.addItem("Google Gemini • Bulut LLM", "gemini")
        self.ai_provider_combo.addItem("OpenAI • Bulut LLM", "openai")
        self.ai_provider_combo.addItem("Groq • Bulut LLM", "groq")
        self.ai_provider_combo.addItem("xAI Grok • Bulut LLM", "grok")
        h1.addWidget(self.ai_provider_combo, 1)
        processing_layout.addLayout(h1)

        self.ai_provider_description = QLabel()
        self.ai_provider_description.setObjectName("infoNote")
        self.ai_provider_description.setWordWrap(True)
        processing_layout.addWidget(self.ai_provider_description)

        self.ai_model_widget = QWidget()
        ai_model_layout = QHBoxLayout(self.ai_model_widget)
        ai_model_layout.setContentsMargins(0, 0, 0, 0)
        ai_model_label = QLabel("Bulut düzenleme modeli")
        ai_model_label.setObjectName("fieldLabel")
        ai_model_layout.addWidget(ai_model_label)
        self.ai_model_combo = QComboBox()
        ai_model_layout.addWidget(self.ai_model_combo, 1)
        processing_layout.addWidget(self.ai_model_widget)

        self.custom_provider_widget = QWidget()
        h_ollama = QHBoxLayout(self.custom_provider_widget)
        h_ollama.setContentsMargins(0, 0, 0, 0)
        endpoint_label = QLabel("Yerel API adresi")
        endpoint_label.setObjectName("fieldLabel")
        h_ollama.addWidget(endpoint_label)
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("http://localhost:11434/v1")
        h_ollama.addWidget(self.custom_url_input, 1)
        local_model_label = QLabel("Model")
        local_model_label.setObjectName("fieldLabel")
        h_ollama.addWidget(local_model_label)
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setPlaceholderText("llama3.2")
        h_ollama.addWidget(self.custom_model_input, 1)
        processing_layout.addWidget(self.custom_provider_widget)

        self.ai_prompt_widget = QWidget()
        prompt_layout = QVBoxLayout(self.ai_prompt_widget)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(10)
        h_preset = QHBoxLayout()
        preset_label = QLabel("Düzenleme profili")
        preset_label.setObjectName("fieldLabel")
        h_preset.addWidget(preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Standart imla ve temizleme", "standard")
        self.preset_combo.addItem("Resmi iş ve e-posta dili", "formal")
        self.preset_combo.addItem("Kodlama ve teknik terimler", "coding")
        self.preset_combo.addItem("İngilizceye çevir", "translate_en")
        self.preset_combo.addItem("Maddeler halinde özetle", "summarize")
        h_preset.addWidget(self.preset_combo, 1)
        prompt_layout.addLayout(h_preset)

        fallback_row = QHBoxLayout()
        fallback_label = QLabel("Düzenleme başarısız olursa")
        fallback_label.setObjectName("fieldLabel")
        fallback_row.addWidget(fallback_label)
        self.cleanup_failure_combo = QComboBox()
        self.cleanup_failure_combo.addItem("Temel yerel temizleme uygula", "rule_based")
        self.cleanup_failure_combo.addItem("Ham transkripti kullan", "raw")
        self.cleanup_failure_combo.addItem("İşlemi hata ile durdur", "fail")
        fallback_row.addWidget(self.cleanup_failure_combo, 1)
        prompt_layout.addLayout(fallback_row)

        rules_label = QLabel("Ek düzenleme kuralları")
        rules_label.setObjectName("fieldLabel")
        prompt_layout.addWidget(rules_label)
        self.custom_rules_edit = QTextEdit()
        self.custom_rules_edit.setPlaceholderText("Örn: Özel isimleri koru, kısa cümleler kullan, üslubu resmi tut...")
        self.custom_rules_edit.setMaximumHeight(88)
        prompt_layout.addWidget(self.custom_rules_edit)
        processing_layout.addWidget(self.ai_prompt_widget)
        c_layout.addWidget(self.ai_processing_settings)
        self.ai_provider_combo.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.ai_cleanup_cb.toggled.connect(self._update_ai_provider_fields)

        layout.addWidget(cleanup_group)

        self.cloud_keys_widget = QGroupBox("Bulut Servis Erişimleri")
        key_layout = QVBoxLayout(self.cloud_keys_widget)
        key_layout.setSpacing(10)
        key_intro = QLabel(
            "Yalnızca etkin STT veya metin düzenleme sağlayıcısının anahtarı gösterilir. "
            "Anahtarlar düz metin ayar dosyasına değil Windows Kimlik Bilgisi Yöneticisi'ne kaydedilir."
        )
        key_intro.setObjectName("sectionDescription")
        key_intro.setWordWrap(True)
        key_layout.addWidget(key_intro)
        keys_grid = QGridLayout()
        keys_grid.setHorizontalSpacing(12)
        keys_grid.setVerticalSpacing(10)

        # Gemini Row
        self.gemini_key_label = QLabel("Gemini API anahtarı")
        self.gemini_key_label.setObjectName("fieldLabel")
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_key_input.setPlaceholderText("Google AI Studio API anahtarı")
        self.gemini_test_btn = QPushButton("Test Et")
        self.gemini_test_btn.setObjectName("testKeyBtn")
        self.gemini_status_label = QLabel("")
        self.gemini_status_label.setObjectName("apiTestStatus")
        self.gemini_test_btn.clicked.connect(lambda: self._test_api_key("gemini", self.gemini_key_input, self.gemini_status_label, self.gemini_test_btn))
        keys_grid.addWidget(self.gemini_key_label, 0, 0)
        keys_grid.addWidget(self.gemini_key_input, 0, 1)
        keys_grid.addWidget(self.gemini_test_btn, 0, 2)
        keys_grid.addWidget(self.gemini_status_label, 0, 3)

        # Grok Row
        self.grok_key_label = QLabel("Grok API anahtarı")
        self.grok_key_label.setObjectName("fieldLabel")
        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.Password)
        self.grok_key_input.setPlaceholderText("xAI API anahtarı")
        self.grok_test_btn = QPushButton("Test Et")
        self.grok_test_btn.setObjectName("testKeyBtn")
        self.grok_status_label = QLabel("")
        self.grok_status_label.setObjectName("apiTestStatus")
        self.grok_test_btn.clicked.connect(lambda: self._test_api_key("grok", self.grok_key_input, self.grok_status_label, self.grok_test_btn))
        keys_grid.addWidget(self.grok_key_label, 1, 0)
        keys_grid.addWidget(self.grok_key_input, 1, 1)
        keys_grid.addWidget(self.grok_test_btn, 1, 2)
        keys_grid.addWidget(self.grok_status_label, 1, 3)

        # Groq Row
        self.groq_key_label = QLabel("Groq API anahtarı")
        self.groq_key_label.setObjectName("fieldLabel")
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        self.groq_key_input.setPlaceholderText("Groq Cloud API anahtarı")
        self.groq_test_btn = QPushButton("Test Et")
        self.groq_test_btn.setObjectName("testKeyBtn")
        self.groq_status_label = QLabel("")
        self.groq_status_label.setObjectName("apiTestStatus")
        self.groq_test_btn.clicked.connect(lambda: self._test_api_key("groq", self.groq_key_input, self.groq_status_label, self.groq_test_btn))
        keys_grid.addWidget(self.groq_key_label, 2, 0)
        keys_grid.addWidget(self.groq_key_input, 2, 1)
        keys_grid.addWidget(self.groq_test_btn, 2, 2)
        keys_grid.addWidget(self.groq_status_label, 2, 3)

        # OpenAI Row
        self.openai_key_label = QLabel("OpenAI API anahtarı")
        self.openai_key_label.setObjectName("fieldLabel")
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        self.openai_key_input.setPlaceholderText("OpenAI Platform API anahtarı")
        self.openai_test_btn = QPushButton("Test Et")
        self.openai_test_btn.setObjectName("testKeyBtn")
        self.openai_status_label = QLabel("")
        self.openai_status_label.setObjectName("apiTestStatus")
        self.openai_test_btn.clicked.connect(lambda: self._test_api_key("openai", self.openai_key_input, self.openai_status_label, self.openai_test_btn))
        keys_grid.addWidget(self.openai_key_label, 3, 0)
        keys_grid.addWidget(self.openai_key_input, 3, 1)
        keys_grid.addWidget(self.openai_test_btn, 3, 2)
        keys_grid.addWidget(self.openai_status_label, 3, 3)

        keys_grid.setColumnStretch(1, 1)
        key_layout.addLayout(keys_grid)
        layout.addWidget(self.cloud_keys_widget)
        layout.addStretch()
        return widget

    def _test_api_key(self, provider: str, input_field: QLineEdit, status_label: QLabel, test_btn: QPushButton):
        key = input_field.text().strip()
        if not key:
            status_label.setText(translate("api.status.empty_key"))
            status_label.setStyleSheet("color: #ef4444; font-weight: 600;")
            return

        status_label.setText(translate("api.status.testing"))
        status_label.setStyleSheet("color: #38bdf8; font-weight: 600;")
        test_btn.setEnabled(False)

        def worker():
            result = self.provider_catalog.discover(provider, key)
            self.api_test_signal.emit(result, status_label, test_btn, provider)

        threading.Thread(target=worker, daemon=True).start()

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

    def _update_ai_provider_fields(self, *_):
        provider = self.ai_provider_combo.currentData()
        enabled = self.ai_cleanup_cb.isChecked()
        is_cloud_ai = provider in {"gemini", "grok", "groq", "openai"}
        self.ai_processing_settings.setVisible(enabled)
        self.ai_provider_description.setText(translate(f"cleanup.description.{provider}"))
        self.custom_provider_widget.setVisible(enabled and provider == "custom_ollama")
        self.ai_model_widget.setVisible(enabled and is_cloud_ai)
        self.ai_prompt_widget.setVisible(enabled and provider != "rule_based")
        required_key_providers = set()
        if enabled and is_cloud_ai:
            required_key_providers.add(provider)
        if self.backend_combo.currentData() == "cloud" or self.cloud_fallback_cb.isChecked():
            required_key_providers.add(self.cloud_stt_combo.currentData())
        self.cloud_keys_widget.setVisible(bool(required_key_providers))
        for key_provider, label, field, btn, status in (
            ("gemini", self.gemini_key_label, self.gemini_key_input, self.gemini_test_btn, self.gemini_status_label),
            ("grok", self.grok_key_label, self.grok_key_input, self.grok_test_btn, self.grok_status_label),
            ("groq", self.groq_key_label, self.groq_key_input, self.groq_test_btn, self.groq_status_label),
            ("openai", self.openai_key_label, self.openai_key_input, self.openai_test_btn, self.openai_status_label),
        ):
            visible = key_provider in required_key_providers
            label.setVisible(visible)
            field.setVisible(visible)
            btn.setVisible(visible)
            status.setVisible(visible)
        self._update_ai_models(provider)

    def _update_ai_models(self, provider: str):
        models = {
            "gemini": ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro"],
            "openai": ["gpt-5.4", "gpt-4o-mini", "gpt-4o", "o3-mini", "o4-mini"],
            "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            "grok": ["grok-4.5", "grok-4.3", "grok-4.1-fast"],
            "custom_ollama": ["llama3.2", "llama3.1", "qwen2.5", "gemma2", "mistral"],
        }
        discovered = self.provider_model_cache.get(provider, {}).get("text", [])
        if discovered:
            models[provider] = discovered
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(models.get(provider, []))
        saved_model = config_manager.get(f"ai_model_{provider}", "")
        if saved_model:
            self.ai_model_combo.setCurrentText(saved_model)

    def _create_file_transcribe_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Ses veya Video Dosyasını Metne Çevir (.mp3, .wav, .mp4, .m4a, .mkv, .flac, .ogg)")
        g_layout = QVBoxLayout(group)

        h_file = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Bir ses veya video dosyası seçin...")
        h_file.addWidget(self.file_path_input)

        browse_btn = QPushButton("Gözat...")
        browse_btn.clicked.connect(self.browse_audio_file)
        h_file.addWidget(browse_btn)

        self.transcribe_file_btn = QPushButton("Transkripsiyonu Başlat")
        self.transcribe_file_btn.clicked.connect(self.start_file_transcription)
        h_file.addWidget(self.transcribe_file_btn)

        self.cancel_transcribe_btn = QPushButton("İptal")
        self.cancel_transcribe_btn.setObjectName("secondary_btn")
        self.cancel_transcribe_btn.setEnabled(False)
        self.cancel_transcribe_btn.clicked.connect(self.cancel_file_transcription)
        h_file.addWidget(self.cancel_transcribe_btn)
        g_layout.addLayout(h_file)

        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        g_layout.addWidget(self.file_progress)

        g_layout.addWidget(QLabel("Çevrilen Metin:"))
        self.file_result_edit = QTextEdit()
        g_layout.addWidget(self.file_result_edit)

        h_actions = QHBoxLayout()
        copy_file_text_btn = QPushButton("Metni Kopyala")
        copy_file_text_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.file_result_edit.toPlainText()))
        h_actions.addWidget(copy_file_text_btn)

        save_file_text_btn = QPushButton("Metni Dosyaya Kaydet")
        save_file_text_btn.clicked.connect(self.save_file_text)
        h_actions.addWidget(save_file_text_btn)

        clear_file_text_btn = QPushButton("Metni Temizle")
        clear_file_text_btn.setObjectName("secondary_btn")
        clear_file_text_btn.clicked.connect(self.clear_file_transcription)
        h_actions.addWidget(clear_file_text_btn)
        h_actions.addStretch()

        g_layout.addLayout(h_actions)
        layout.addWidget(group)
        return widget

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
            worker = FileTranscribeWorker(file_path, engine=self.engine_manager)
            self.transcribe_worker = worker
            worker.progress.connect(self._on_file_progress)
            worker.completed.connect(self._on_file_finished)
            worker.error.connect(self._on_file_error)
            worker.cancelled.connect(self._on_file_cancelled)
            worker.finished.connect(lambda worker=worker: self._release_file_worker(worker))
            worker.start()
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

    def _release_file_worker(self, worker):
        """Release only the worker that actually stopped; ignore stale callbacks."""
        if self.transcribe_worker is not worker:
            return
        self.transcribe_worker = None
        worker.deleteLater()

    def cancel_file_transcription(self):
        if self.transcribe_worker and self.transcribe_worker.isRunning():
            self.transcribe_worker.requestInterruption()
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
        self.file_segments = list(getattr(self.transcribe_worker, "segments", []))
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

    def _create_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.setup_audio_step = QFrame()
        self.setup_audio_step.setObjectName("onboardingCard")
        setup_layout = QHBoxLayout(self.setup_audio_step)
        setup_layout.setContentsMargins(18, 14, 18, 14)
        setup_text = QLabel("Kurulum 2/2 • Mikrofonu ve global kısayolu doğrulayın, ardından kurulumu tamamlayın.")
        setup_text.setObjectName("sectionDescription")
        setup_text.setWordWrap(True)
        setup_back = QPushButton("Motor seçimine dön")
        setup_back.setObjectName("secondary_btn")
        setup_back.clicked.connect(lambda: self._set_page(1))
        setup_finish = QPushButton("Kurulumu Tamamla")
        setup_finish.setObjectName("primaryAction")
        setup_finish.clicked.connect(self.save_ui_settings)
        setup_layout.addWidget(setup_text, 1)
        setup_layout.addWidget(setup_back)
        setup_layout.addWidget(setup_finish)
        self.setup_audio_step.setVisible(False)
        layout.addWidget(self.setup_audio_step)

        language_group = QGroupBox("Uygulama Dili & Arayüz")
        language_layout = QVBoxLayout(language_group)

        language_row = QHBoxLayout()
        language_label = QLabel("Arayüz dili")
        language_label.setObjectName("fieldLabel")
        language_row.addWidget(language_label)
        self.ui_language_combo = QComboBox(language_group)
        self.ui_language_combo.addItem("Türkçe", "tr")
        self.ui_language_combo.addItem("English", "en")
        language_row.addWidget(self.ui_language_combo, 1)
        language_layout.addLayout(language_row)

        font_row = QHBoxLayout()
        font_label = QLabel("Arayüz metin boyutu")
        font_label.setObjectName("fieldLabel")
        font_row.addWidget(font_label)
        self.ui_font_size_combo = QComboBox(language_group)
        self.ui_font_size_combo.addItem("Normal (%100)", "normal")
        self.ui_font_size_combo.addItem("Büyük (%115)", "large")
        font_row.addWidget(self.ui_font_size_combo, 1)
        language_layout.addLayout(font_row)

        language_note = QLabel("Dil ve görünüm değişiklikleri ayarlar kaydedildiğinde uygulanır.")
        language_note.setObjectName("mutedLabel")
        language_layout.addWidget(language_note)
        layout.addWidget(language_group)

        hotkey_group = QGroupBox("Küresel Kısayol Tuşu")
        hk_layout = QVBoxLayout(hotkey_group)

        h1 = QHBoxLayout()
        hk_lbl = QLabel("Kısayol Tuşu:")
        hk_lbl.setObjectName("fieldLabel")
        h1.addWidget(hk_lbl)
        self.hotkey_recorder = HotkeyRecorderWidget()
        self.hotkey_recorder.hotkey_changed.connect(self._sync_hotkey_settings_live)
        h1.addWidget(self.hotkey_recorder, 1)
        hk_layout.addLayout(h1)

        h2 = QHBoxLayout()
        hk_mode_lbl = QLabel("Kısayol Çalışma Modu:")
        hk_mode_lbl.setObjectName("fieldLabel")
        h2.addWidget(hk_mode_lbl)
        self.hotkey_mode_combo = QComboBox(hotkey_group)
        self.hotkey_mode_combo.addItem("Bas-Konuş (Push-to-Talk): Tuşa basılı tutulduğu sürece dikte aktif olur.", "hold")
        self.hotkey_mode_combo.addItem("Aç / Kapat (Toggle): Tuşa bir kez basıldığında başlar, tekrar basıldığında durur.", "toggle")
        self.hotkey_mode_combo.currentIndexChanged.connect(self._sync_hotkey_settings_live)
        h2.addWidget(self.hotkey_mode_combo, 1)
        hk_layout.addLayout(h2)

        self.hotkey_status_label = QLabel()
        self.hotkey_status_label.setObjectName("mutedLabel")
        self.hotkey_status_label.setWordWrap(True)
        hk_layout.addWidget(self.hotkey_status_label)

        layout.addWidget(hotkey_group)

        audio_group = QGroupBox("Mikrofon Girişi")
        a_layout = QVBoxLayout(audio_group)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Mikrofon Aygıtı:"))
        self.mic_combo = QComboBox(audio_group)
        self.refresh_mic_list()
        h3.addWidget(self.mic_combo)
        a_layout.addLayout(h3)

        a_layout.addWidget(QLabel("Canlı Mikrofon Test Metresi:"))
        self.mic_progress = QProgressBar()
        self.mic_progress.setRange(0, 100)
        a_layout.addWidget(self.mic_progress)

        duration_row = QHBoxLayout()
        duration_label = QLabel("Maksimum dikte süresi:")
        duration_label.setObjectName("fieldLabel")
        duration_row.addWidget(duration_label)
        self.max_recording_combo = QComboBox(audio_group)
        self.max_recording_combo.addItem("1 dakika", 60)
        self.max_recording_combo.addItem("5 dakika", 300)
        self.max_recording_combo.addItem("10 dakika", 600)
        self.max_recording_combo.addItem("30 dakika", 1800)
        duration_row.addWidget(self.max_recording_combo, 1)
        a_layout.addLayout(duration_row)

        layout.addWidget(audio_group)

        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)
        b_layout.setSpacing(10)

        self.auto_paste_cb = QCheckBox("Metni aktif pencereye otomatik yapıştır")
        self.restore_clip_cb = QCheckBox("Yapıştırmadan sonra önceki pano metnini geri yükle")
        self.restore_clip_cb.setToolTip("Yalnızca düz metin korunur; resim, dosya ve biçimlendirilmiş pano içerikleri geri yüklenmez.")
        self.history_enabled_cb = QCheckBox("Dikte geçmişini bu cihazda sakla")
        self.play_sound_cb = QCheckBox("Kayıt başlangıç ve bitiş seslerini çal")
        self.overlay_cb = QCheckBox("Yüzen ses dalgası göstergesini kullan")
        self.overlay_always_on_cb = QCheckBox("Yüzen dikte kutusunu her zaman göster (Sürekli görünür)")
        self.start_windows_cb = QCheckBox("Windows ile otomatik başlat")

        b_layout.addWidget(self.auto_paste_cb)
        b_layout.addWidget(self.restore_clip_cb)
        b_layout.addWidget(self.history_enabled_cb)
        b_layout.addWidget(self.play_sound_cb)
        b_layout.addWidget(self.overlay_cb)
        b_layout.addWidget(self.overlay_always_on_cb)
        b_layout.addWidget(self.start_windows_cb)

        layout.addWidget(behavior_group)
        layout.addStretch()
        return widget

    def _sync_hotkey_settings_live(self, *_):
        hk = self.hotkey_recorder.get_hotkey()
        mode = self.hotkey_mode_combo.currentData() or "toggle"
        if self.app_controller and hasattr(self.app_controller, "hotkey_listener"):
            registered = self.app_controller.hotkey_listener.update_hotkey(hk, mode)
            if registered:
                self.hotkey_status_label.setText(
                    translate("hotkey.status.active", hotkey=hk.upper().replace("+", " + "))
                )
                self.hotkey_status_label.setStyleSheet("color: #69ddb0;")
            else:
                self.hotkey_status_label.setText(translate("hotkey.status.failed"))
                self.hotkey_status_label.setStyleSheet("color: #ff8794;")

    def _create_about_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("aboutCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 30, 34, 30)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignHCenter)

        studio_logo = QLabel()
        studio_logo.setObjectName("studioLogo")
        studio_logo.setAlignment(Qt.AlignCenter)
        logo_path = get_resource_path(os.path.join("assets", "maximus-prime-software.png"))
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            studio_logo.setPixmap(pixmap)
        card_layout.addWidget(studio_logo)

        studio_name = QLabel(STUDIO)
        studio_name.setObjectName("aboutStudio")
        studio_name.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(studio_name)

        credit = QLabel("Maximus Prime Software tarafından tasarlandı ve geliştirildi.")
        credit.setObjectName("aboutCredit")
        credit.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(credit)

        manifesto = QLabel("Gizlilik odaklı tasarım. Üretken Windows iş akışları için geliştirildi.")
        manifesto.setObjectName("mutedLabel")
        manifesto.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(manifesto)

        self.about_version_label = QLabel(f"Sürüm {__version__}  •  GPL-3.0")
        self.about_version_label.setObjectName("aboutVersion")
        self.about_version_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.about_version_label)

        links = QHBoxLayout()
        links.setSpacing(10)
        for label, url in (
            ("Web Sitesi", WEBSITE),
            ("GitHub", REPOSITORY),
            ("E-posta", f"mailto:{EMAIL}"),
        ):
            button = QPushButton(label)
            button.setObjectName("secondary_btn")
            button.clicked.connect(lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            links.addWidget(button)
        card_layout.addLayout(links)

        layout.addWidget(card)
        layout.addStretch()
        return widget

    def _create_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Geçmişte ara...")
        self.history_search.textChanged.connect(self.refresh_history_list)
        layout.addWidget(self.history_search)
        self.history_summary = QLabel()
        self.history_summary.setObjectName("mutedLabel")
        layout.addWidget(self.history_summary)
        self.history_list = QListWidget()
        self.history_list.itemSelectionChanged.connect(self._update_history_actions)
        self.history_list.itemDoubleClicked.connect(lambda _item: self.copy_selected_history())
        layout.addWidget(self.history_list)

        self.history_empty_label = QLabel("Henüz kayıtlı bir dikte yok.")
        self.history_empty_label.setObjectName("infoNote")
        self.history_empty_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.history_empty_label)

        h = QHBoxLayout()
        self.history_copy_btn = QPushButton("Seçilen Metni Kopyala")
        self.history_copy_btn.clicked.connect(self.copy_selected_history)
        h.addWidget(self.history_copy_btn)

        self.history_delete_btn = QPushButton("Seçileni Sil")
        self.history_delete_btn.setObjectName("secondary_btn")
        self.history_delete_btn.clicked.connect(self.delete_selected_history)
        h.addWidget(self.history_delete_btn)

        clear_btn = QPushButton("Geçmişi Temizle")
        clear_btn.setObjectName("secondary_btn")
        clear_btn.clicked.connect(self.clear_history)
        h.addWidget(clear_btn)

        layout.addLayout(h)
        self._update_history_actions()
        return widget

    def _create_dev_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        dev_group = QGroupBox("Geliştirici Tanı Ekranı ve Canlı Log Konsolu")
        d_layout = QVBoxLayout(dev_group)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #080c11; color: #76a8b4; font-family: 'Consolas', monospace; font-size: 11px;")
        d_layout.addWidget(self.log_console)

        h_btn = QHBoxLayout()
        clear_log_btn = QPushButton("Konsolu Temizle")
        clear_log_btn.clicked.connect(lambda: self.log_console.clear())
        h_btn.addWidget(clear_log_btn)

        test_sound_btn = QPushButton("Mikrofon Tanı Bilgisi")
        test_sound_btn.clicked.connect(self.test_audio_input)
        h_btn.addWidget(test_sound_btn)

        export_diagnostics_btn = QPushButton(translate("diagnostics.action.export"))
        export_diagnostics_btn.setObjectName("secondary_btn")
        self._bind_translation(
            export_diagnostics_btn,
            "text",
            "diagnostics.action.export",
            export_diagnostics_btn.setText,
        )
        export_diagnostics_btn.clicked.connect(self.export_diagnostics_bundle)
        h_btn.addWidget(export_diagnostics_btn)

        h_btn.addStretch()
        d_layout.addLayout(h_btn)

        layout.addWidget(dev_group)
        return widget

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

    def refresh_mic_list(self):
        self.mic_combo.clear()
        self.mic_combo.addItem("Varsayılan Sistem Mikrofonu", None)
        devices = AudioRecorder.get_input_devices()
        for dev in devices:
            self.mic_combo.addItem(f"{dev['name']}", dev['index'])

    def _apply_ui_font_size(self, font_size_mode: str):
        if font_size_mode == "small":
            font_size_mode = "normal"
        sidebar_widths = {"normal": 255, "large": 285}
        self._preferred_sidebar_width = sidebar_widths.get(font_size_mode, 255)
        self._update_responsive_layout()
        self.setStyleSheet(get_styled_app(font_size_mode))

    @staticmethod
    def _safe_combo_set_data(combo, data_val, default_idx=0):
        if not combo:
            return
        try:
            combo.blockSignals(True)
            idx = combo.findData(data_val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(max(0, default_idx))
            combo.blockSignals(False)
        except (RuntimeError, AttributeError):
            pass

    def load_settings_to_ui(self):
        ui_language = config_manager.get("ui_language", "en")
        self._safe_combo_set_data(getattr(self, "ui_language_combo", None), ui_language, 0)
        self._safe_combo_set_data(getattr(self, "quick_lang_combo", None), ui_language, 0)

        font_size = config_manager.get("ui_font_size", "normal")
        if font_size == "small":
            font_size = "normal"
        self._safe_combo_set_data(getattr(self, "ui_font_size_combo", None), font_size, 0)
        self._apply_ui_font_size(font_size)

        backend = config_manager.get("stt_backend", "cpu")
        capability = getattr(self, "local_backend_capabilities", {}).get(backend)
        if capability and not capability.available:
            backend = recommended_local_backend(self.local_backend_capabilities)
        self._safe_combo_set_data(getattr(self, "backend_combo", None), backend, 2)
        self.vulkan_executable_input.setText(config_manager.get("vulkan_executable", ""))
        cloud_provider = config_manager.get("cloud_stt_provider", "groq")
        self._safe_combo_set_data(getattr(self, "cloud_stt_combo", None), cloud_provider, 0)
        self._update_cloud_stt_models()
        self._update_backend_fields()

        model = config_manager.get("model_size", "base")
        if model == "turbo":
            model = "large-v3-turbo"
        active_backend = self.backend_combo.currentData()
        if active_backend != "cloud" and model not in supported_models(active_backend):
            model = "large-v3-turbo" if "large-v3-turbo" in supported_models(active_backend) else "base"
        self._safe_combo_set_data(getattr(self, "model_combo", None), model, 1)

        lang = config_manager.get("language", "en")
        self._safe_combo_set_data(getattr(self, "lang_combo", None), lang, 0)

        self.auto_paste_cb.setChecked(config_manager.get("auto_paste", True))
        self.restore_clip_cb.setChecked(config_manager.get("restore_clipboard", True))
        self.history_enabled_cb.setChecked(config_manager.get("history_enabled", True))
        self.play_sound_cb.setChecked(config_manager.get("play_sound", True))
        self.overlay_cb.setChecked(config_manager.get("overlay_enabled", True))
        self._safe_combo_set_data(
            getattr(self, "max_recording_combo", None),
            config_manager.get("max_recording_seconds", 300),
            1,
        )
        self.overlay_always_on_cb.setChecked(config_manager.get("overlay_always_on", False))
        self.start_windows_cb.setChecked(config_manager.get("start_with_windows", False))
        self.cloud_fallback_cb.setChecked(config_manager.get("allow_cloud_fallback", False))

        self.hotkey_recorder.set_hotkey(config_manager.get("hotkey", "ctrl+alt+d"))
        hk_mode = config_manager.get("hotkey_mode", "toggle")
        self._safe_combo_set_data(getattr(self, "hotkey_mode_combo", None), hk_mode, 1)

        self.ai_cleanup_cb.setChecked(config_manager.get("ai_cleanup_enabled", True))
        provider = config_manager.get("ai_cleanup_provider", "rule_based")
        self._safe_combo_set_data(getattr(self, "ai_provider_combo", None), provider, 0)
        self._update_ai_provider_fields()

        preset_key = config_manager.get("preset_prompt_key", "standard")
        self._safe_combo_set_data(getattr(self, "preset_combo", None), preset_key, 0)
        self._safe_combo_set_data(
            getattr(self, "cleanup_failure_combo", None),
            config_manager.get("cleanup_failure_policy", "rule_based"),
            0,
        )

        self.custom_url_input.setText(config_manager.get("custom_api_base_url", "http://localhost:11434/v1"))
        self.custom_model_input.setText(config_manager.get("custom_model_name", "llama3.2"))

        self.gemini_key_input.setText(config_manager.get("api_key_gemini", ""))
        self.grok_key_input.setText(config_manager.get("api_key_grok", ""))
        self.groq_key_input.setText(config_manager.get("api_key_groq", ""))
        self.openai_key_input.setText(config_manager.get("api_key_openai", ""))
        self.custom_rules_edit.setText(config_manager.get("custom_user_rules", ""))

        self.check_selected_model_status(model)
        self.refresh_history_list()
        self._refresh_dashboard()

    def save_ui_settings(self):
        completing_setup_flow = self._setup_flow_active
        provider = self.ai_provider_combo.currentData()
        backend = self.backend_combo.currentData()
        cloud_provider = self.cloud_stt_combo.currentData()
        credentials = {
            "gemini": self.gemini_key_input.text().strip(),
            "grok": self.grok_key_input.text().strip(),
            "groq": self.groq_key_input.text().strip(),
            "openai": self.openai_key_input.text().strip(),
        }
        local_model = self.model_combo.currentData() or self.model_combo.currentText()
        if backend != "cloud" and not self.model_manager.is_model_downloaded(local_model, backend):
            QMessageBox.warning(self, translate("setup.dialog.incomplete"), translate("setup.error.download_local_model"))
            self._set_page(1)
            return
        if backend == "cloud" and (not self.cloud_stt_model_combo.currentText().strip() or not credentials.get(cloud_provider)):
            QMessageBox.warning(self, translate("setup.dialog.incomplete"), translate("setup.error.cloud_stt_credentials"))
            return
        if backend != "cloud" and self.cloud_fallback_cb.isChecked() and (
            not credentials.get(cloud_provider) or not self.cloud_stt_model_combo.currentText().strip()
        ):
            QMessageBox.warning(self, translate("setup.dialog.incomplete"), translate("setup.error.cloud_fallback_credentials"))
            return
        if self.ai_cleanup_cb.isChecked() and provider in credentials:
            if not credentials[provider] or not self.ai_model_combo.currentText().strip():
                QMessageBox.warning(self, translate("setup.dialog.incomplete"), translate("setup.error.cleanup_credentials"))
                return
        if self.ai_cleanup_cb.isChecked() and provider == "custom_ollama":
            if not self.custom_url_input.text().strip() or not self.custom_model_input.text().strip():
                QMessageBox.warning(self, translate("setup.dialog.incomplete"), translate("setup.error.local_llm"))
                return
        vulkan_executable = self.vulkan_executable_input.text().strip()
        if backend == "vulkan" and vulkan_executable and not os.path.isfile(vulkan_executable):
            QMessageBox.warning(self, translate("vulkan.dialog.invalid_runtime"), translate("vulkan.error.executable_missing"))
            return
        if backend == "vulkan":
            runtime_ok, runtime_message = VulkanSTTEngine.runtime_status(vulkan_executable or None)
            if not runtime_ok:
                QMessageBox.warning(self, translate("vulkan.dialog.runtime_unavailable"), runtime_message)
                return

        settings = {
            "ui_language": self.ui_language_combo.currentData(),
            "ui_font_size": self.ui_font_size_combo.currentData(),
            "setup_completed": True,
            "stt_backend": backend,
            "model_size": self.model_combo.currentData() or self.model_combo.currentText(),
            "language": self.lang_combo.currentData() or "auto",
            "cloud_stt_provider": cloud_provider,
            f"stt_model_{cloud_provider}": self.cloud_stt_model_combo.currentText().strip(),
            "vulkan_executable": vulkan_executable,
            "auto_paste": self.auto_paste_cb.isChecked(),
            "restore_clipboard": self.restore_clip_cb.isChecked(),
            "history_enabled": self.history_enabled_cb.isChecked(),
            "play_sound": self.play_sound_cb.isChecked(),
            "overlay_enabled": self.overlay_cb.isChecked(),
            "overlay_always_on": self.overlay_always_on_cb.isChecked(),
            "start_with_windows": self.start_windows_cb.isChecked(),
            "allow_cloud_fallback": self.cloud_fallback_cb.isChecked(),
            "hotkey": self.hotkey_recorder.get_hotkey(),
            "hotkey_mode": self.hotkey_mode_combo.currentData(),
            "audio_device_index": self.mic_combo.currentData(),
            "max_recording_seconds": self.max_recording_combo.currentData() or 300,
            "ai_cleanup_enabled": self.ai_cleanup_cb.isChecked(),
            "ai_cleanup_provider": provider,
            "cleanup_failure_policy": self.cleanup_failure_combo.currentData() or "rule_based",
            f"ai_model_{provider}": self.ai_model_combo.currentText().strip(),
            "preset_prompt_key": self.preset_combo.currentData(),
            "custom_api_base_url": self.custom_url_input.text().strip(),
            "custom_model_name": self.custom_model_input.text().strip(),
            "api_key_gemini": self.gemini_key_input.text().strip(),
            "api_key_grok": self.grok_key_input.text().strip(),
            "api_key_groq": self.groq_key_input.text().strip(),
            "api_key_openai": self.openai_key_input.text().strip(),
            "custom_user_rules": self.custom_rules_edit.toPlainText().strip(),
        }
        previous_startup = config_manager.get("start_with_windows", False)
        try:
            configure_start_with_windows(self.start_windows_cb.isChecked())
            config_manager.update(settings)
        except (RuntimeError, OSError) as exc:
            try:
                configure_start_with_windows(previous_startup)
            except OSError:
                pass
            QMessageBox.critical(self, translate("settings.dialog.save_failed"), str(exc))
            return

        set_language(settings["ui_language"])
        self._apply_ui_font_size(settings["ui_font_size"])
        if self.app_controller:
            self.app_controller.reload_settings()

        self._apply_ui_language()
        self._refresh_dashboard()
        if completing_setup_flow:
            self._setup_flow_active = False
            self.setup_engine_step.setVisible(False)
            self.setup_audio_step.setVisible(False)
            self._set_page(0)
        QMessageBox.information(self, translate("dialog.success"), translate("settings.dialog.saved"))

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
        history = config_manager.load_history()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history.insert(0, {"time": now_str, "text": text})
        config_manager.save_history(history[:500])
        self.refresh_history_list()

    def refresh_history_list(self):
        self.history_list.clear()
        history = config_manager.load_history()
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
        history = config_manager.load_history()
        for index, item in enumerate(history):
            if item.get("text", "") == target_text and item.get("time", "") == target_time:
                del history[index]
                break
        config_manager.save_history(history)
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
        config_manager.save_history([])
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
        worker = self.transcribe_worker
        if worker is None or not worker.isRunning():
            return True
        worker.requestInterruption()
        if not worker.wait(timeout_ms):
            logger.error("File transcription worker did not stop before shutdown timeout.")
            return False
        if self.transcribe_worker is worker:
            self.transcribe_worker = None
        worker.deleteLater()
        return True

    def closeEvent(self, event):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            self.quit_app()
            return
        event.ignore()
        self.hide()
