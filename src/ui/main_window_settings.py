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

class MainWindowSettingsMixin:
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
        try:
            saved_recording_limit = min(600, int(config_manager.get("max_recording_seconds", 300)))
        except (TypeError, ValueError):
            saved_recording_limit = 300
        self._safe_combo_set_data(
            getattr(self, "max_recording_combo", None),
            saved_recording_limit,
            1,
        )
        self.overlay_always_on_cb.setChecked(config_manager.get("overlay_always_on", False))
        self.start_windows_cb.setChecked(config_manager.get("start_with_windows", False))
        self.admin_mode_cb.setChecked(config_manager.get("run_as_administrator", False))
        self._update_admin_mode_status()
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
        previous_backend = config_manager.get("stt_backend", "cpu")
        previous_model = config_manager.get("model_size", "base")
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
            "run_as_administrator": self.admin_mode_cb.isChecked(),
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
        previous_admin_mode = config_manager.get("run_as_administrator", False)
        try:
            configure_start_with_windows(
                self.start_windows_cb.isChecked(),
                elevated=self.admin_mode_cb.isChecked(),
            )
            config_manager.update(settings)
        except (RuntimeError, OSError) as exc:
            try:
                configure_start_with_windows(previous_startup, elevated=previous_admin_mode)
            except OSError:
                pass
            QMessageBox.critical(self, translate("settings.dialog.save_failed"), str(exc))
            return

        set_language(settings["ui_language"])
        self._apply_ui_font_size(settings["ui_font_size"])
        if self.app_controller:
            self.app_controller.reload_settings()
        self.engine_manager.apply_stt_configuration(previous_backend, previous_model)
        if self.app_controller and hasattr(self.app_controller, "track_model_warmup"):
            self.app_controller.track_model_warmup()

        self._apply_ui_language()
        self._refresh_dashboard()
        if completing_setup_flow:
            self._setup_flow_active = False
            self.setup_engine_step.setVisible(False)
            self.setup_audio_step.setVisible(False)
            self._set_page(0)
        self._update_admin_mode_status()
        QMessageBox.information(self, translate("dialog.success"), translate("settings.dialog.saved"))

    def _update_admin_mode_status(self):
        if not hasattr(self, "admin_mode_status"):
            return
        if is_running_as_administrator():
            key = "settings.admin_status.elevated"
        elif self.admin_mode_cb.isChecked():
            key = "settings.admin_status.restart_required"
        else:
            key = "settings.admin_status.standard"
        detail = translate(key)
        self.admin_mode_status.setText(detail)
