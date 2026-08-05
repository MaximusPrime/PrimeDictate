import os
import sys
import datetime
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QGroupBox, QComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication
)
from src.config import config_manager
from src.audio.recorder import AudioRecorder
from src.ui.styles import DARK_GLASS_STYLE

LOGO_PATH = r"c:\Users\MAXIMUS\PROJECTS\PrimeDictate-Project\PrimeDictate-Logo.png"

class MainWindow(QMainWindow):
    request_toggle_dictation = Signal()

    def __init__(self, app_controller=None):
        super().__init__()
        self.app_controller = app_controller
        self.setWindowTitle("PrimeDictate - Windows Sesli Yazma Paneli")
        self.resize(750, 580)
        self.setStyleSheet(DARK_GLASS_STYLE)

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self._setup_ui()
        self.load_settings_to_ui()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # --- Header ---
        header_layout = QHBoxLayout()
        logo_img = QLabel()
        if os.path.exists(LOGO_PATH):
            pix = QPixmap(LOGO_PATH).scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_img.setPixmap(pix)
        header_layout.addWidget(logo_img)

        title_layout = QVBoxLayout()
        title_label = QLabel("PrimeDictate")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        subtitle_label = QLabel("AMD GPU Donanım Hızlandırmalı Akıllı Dikte ve Sesli Yazma")
        subtitle_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # Action Buttons
        self.dictate_btn = QPushButton("🎙️ Dikteyi Başlat")
        self.dictate_btn.setMinimumHeight(40)
        self.dictate_btn.clicked.connect(self.on_dictate_btn_clicked)
        header_layout.addWidget(self.dictate_btn)

        main_layout.addLayout(header_layout)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_general_tab(), "⚙️ Genel & Motor")
        self.tabs.addTab(self._create_audio_tab(), "🎤 Kısayol & Ses")
        self.tabs.addTab(self._create_ai_tab(), "🤖 Yapay Zeka Temizleyici")
        self.tabs.addTab(self._create_history_tab(), "📜 Dikte Geçmişi")
        main_layout.addWidget(self.tabs)

        # --- Footer ---
        footer_layout = QHBoxLayout()
        self.status_label = QLabel("Durum: Hazır | AMD GPU DirectML Aktif")
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()

        save_btn = QPushButton("💾 Ayarları Kaydet")
        save_btn.clicked.connect(self.save_ui_settings)
        footer_layout.addWidget(save_btn)

        main_layout.addLayout(footer_layout)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # STT Engine Selection
        engine_group = QGroupBox("Çıkarım Motoru ve Donanım Hızlandırma")
        engine_layout = QVBoxLayout(engine_group)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Çalışma Motoru:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems([
            "NVIDIA GPU (CUDA / cuDNN)",
            "AMD GPU DirectML (DirectX 12)",
            "Vulkan AMD/Intel GPU (Ultra Hızlı)",
            "CPU Çoklu Çekirdek",
            "Bulut API (Groq / OpenAI)"
        ])
        h1.addWidget(self.backend_combo)
        engine_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Whisper Model Boyutu:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "turbo"])
        h2.addWidget(self.model_combo)
        engine_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Dikte Dili:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Türkçe (tr)", "tr")
        self.lang_combo.addItem("İngilizce (en)", "en")
        self.lang_combo.addItem("Otomatik Algıla", "auto")
        h3.addWidget(self.lang_combo)
        engine_layout.addLayout(h3)

        layout.addWidget(engine_group)

        # Behavior settings
        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)

        self.auto_paste_cb = QCheckBox("Dikte edilen metni otomatik aktif pencereye yapıştır (Ctrl+V)")
        self.play_sound_cb = QCheckBox("Kayıt başlarken ve biterken sesli uyarı ver")
        self.overlay_cb = QCheckBox("Ekran üzerinde yüzen ses dalgası kapsülünü (Overlay Widget) göster")

        b_layout.addWidget(self.auto_paste_cb)
        b_layout.addWidget(self.play_sound_cb)
        b_layout.addWidget(self.overlay_cb)

        layout.addWidget(behavior_group)
        layout.addStretch()
        return widget

    def _create_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Hotkey Group
        hotkey_group = QGroupBox("Küresel Kısayol Tuşu")
        hk_layout = QVBoxLayout(hotkey_group)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Kısayol Tuşu:"))
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("Örn: ctrl+alt+d veya f9")
        h1.addWidget(self.hotkey_input)
        hk_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Kısayol Çalışma Modu:"))
        self.hotkey_mode_combo = QComboBox()
        self.hotkey_mode_combo.addItem("Bas-Aç (Toggle) - Tuşa 1 kez basınca başlar, 1 kez basınca biter", "toggle")
        self.hotkey_mode_combo.addItem("Bas-Tut (Hold) - Tuşa basılı tutulduğu sürece kaydeder", "hold")
        h2.addWidget(self.hotkey_mode_combo)
        hk_layout.addLayout(h2)

        layout.addWidget(hotkey_group)

        # Audio Devices
        audio_group = QGroupBox("Mikrofon Girişi")
        a_layout = QVBoxLayout(audio_group)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Mikrofon Aygıtı:"))
        self.mic_combo = QComboBox()
        self.refresh_mic_list()
        h3.addWidget(self.mic_combo)
        a_layout.addLayout(h3)

        a_layout.addWidget(QLabel("Canlı Mikrofon Test Metresi:"))
        self.mic_progress = QProgressBar()
        self.mic_progress.setRange(0, 100)
        a_layout.addWidget(self.mic_progress)

        layout.addWidget(audio_group)
        layout.addStretch()
        return widget

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        cleanup_group = QGroupBox("Yapay Zeka Metin Temizleme ve Noktalama")
        c_layout = QVBoxLayout(cleanup_group)

        self.ai_cleanup_cb = QCheckBox("Akıllı Metin Temizlemeyi Etkinleştir (Dolgu kelimelerini, 'eee', 'yani' seslerini siler)")
        c_layout.addWidget(self.ai_cleanup_cb)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Temizleme Motoru:"))
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("Hızlı Kural Tabanlı Motor (Yerel & Ücretsiz)", "rule_based")
        self.ai_provider_combo.addItem("Google Gemini 2.5 Flash API", "gemini")
        self.ai_provider_combo.addItem("xAI Grok API (Grok-Beta)", "grok")
        self.ai_provider_combo.addItem("Groq LLM (Llama 3.3 70B)", "groq")
        self.ai_provider_combo.addItem("OpenAI LLM (GPT-4o Mini)", "openai")
        h1.addWidget(self.ai_provider_combo)
        c_layout.addLayout(h1)

        h_gemini = QHBoxLayout()
        h_gemini.addWidget(QLabel("Google Gemini API Key:"))
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        h_gemini.addWidget(self.gemini_key_input)
        c_layout.addLayout(h_gemini)

        h_grok = QHBoxLayout()
        h_grok.addWidget(QLabel("xAI Grok API Key:"))
        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.Password)
        h_grok.addWidget(self.grok_key_input)
        c_layout.addLayout(h_grok)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Groq API Key:"))
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        h2.addWidget(self.groq_key_input)
        c_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("OpenAI API Key:"))
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        h3.addWidget(self.openai_key_input)
        c_layout.addLayout(h3)

        c_layout.addWidget(QLabel("Özel Yapay Zeka Promptu:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMaximumHeight(80)
        c_layout.addWidget(self.prompt_edit)

        layout.addWidget(cleanup_group)
        layout.addStretch()
        return widget

    def _create_history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Son Dikte Edilen Metinler:"))
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)

        h = QHBoxLayout()
        copy_btn = QPushButton("📋 Seçilen Metni Kopyala")
        copy_btn.clicked.connect(self.copy_selected_history)
        h.addWidget(copy_btn)

        clear_btn = QPushButton("🗑️ Geçmişi Temizle")
        clear_btn.setObjectName("secondary_btn")
        clear_btn.clicked.connect(self.clear_history)
        h.addWidget(clear_btn)

        layout.addLayout(h)
        return widget

    def refresh_mic_list(self):
        self.mic_combo.clear()
        self.mic_combo.addItem("Varsayılan Sistem Mikrofonu", None)
        devices = AudioRecorder.get_input_devices()
        for dev in devices:
            self.mic_combo.addItem(f"{dev['name']}", dev['index'])

    def load_settings_to_ui(self):
        backend = config_manager.get("stt_backend", "directml")
        backend_idx_map = {"cuda": 0, "directml": 1, "vulkan": 2, "cpu": 3, "cloud": 4}
        self.backend_combo.setCurrentIndex(backend_idx_map.get(backend, 1))

        model = config_manager.get("model_size", "base")
        self.model_combo.setCurrentText(model)

        lang = config_manager.get("language", "tr")
        lang_idx = self.lang_combo.findData(lang)
        if lang_idx >= 0:
            self.lang_combo.setCurrentIndex(lang_idx)

        self.auto_paste_cb.setChecked(config_manager.get("auto_paste", True))
        self.play_sound_cb.setChecked(config_manager.get("play_sound", True))
        self.overlay_cb.setChecked(config_manager.get("overlay_enabled", True))

        self.hotkey_input.setText(config_manager.get("hotkey", "ctrl+alt+d"))
        hk_mode = config_manager.get("hotkey_mode", "toggle")
        hk_mode_idx = self.hotkey_mode_combo.findData(hk_mode)
        if hk_mode_idx >= 0:
            self.hotkey_mode_combo.setCurrentIndex(hk_mode_idx)

        self.ai_cleanup_cb.setChecked(config_manager.get("ai_cleanup_enabled", True))
        provider = config_manager.get("ai_cleanup_provider", "rule_based")
        p_idx = self.ai_provider_combo.findData(provider)
        if p_idx >= 0:
            self.ai_provider_combo.setCurrentIndex(p_idx)

        self.gemini_key_input.setText(config_manager.get("api_key_gemini", ""))
        self.grok_key_input.setText(config_manager.get("api_key_grok", ""))
        self.groq_key_input.setText(config_manager.get("api_key_groq", ""))
        self.openai_key_input.setText(config_manager.get("api_key_openai", ""))
        self.prompt_edit.setText(config_manager.get("custom_prompt", ""))

        self.refresh_history_list()

    def save_ui_settings(self):
        backend_keys = ["cuda", "directml", "vulkan", "cpu", "cloud"]
        config_manager.set("stt_backend", backend_keys[self.backend_combo.currentIndex()])
        config_manager.set("model_size", self.model_combo.currentText())
        config_manager.set("language", self.lang_combo.currentData())

        config_manager.set("auto_paste", self.auto_paste_cb.isChecked())
        config_manager.set("play_sound", self.play_sound_cb.isChecked())
        config_manager.set("overlay_enabled", self.overlay_cb.isChecked())

        config_manager.set("hotkey", self.hotkey_input.text().strip())
        config_manager.set("hotkey_mode", self.hotkey_mode_combo.currentData())

        config_manager.set("audio_device_index", self.mic_combo.currentData())

        config_manager.set("ai_cleanup_enabled", self.ai_cleanup_cb.isChecked())
        config_manager.set("ai_cleanup_provider", self.ai_provider_combo.currentData())
        config_manager.set("api_key_gemini", self.gemini_key_input.text().strip())
        config_manager.set("api_key_grok", self.grok_key_input.text().strip())
        config_manager.set("api_key_groq", self.groq_key_input.text().strip())
        config_manager.set("api_key_openai", self.openai_key_input.text().strip())
        config_manager.set("custom_prompt", self.prompt_edit.toPlainText().strip())

        if self.app_controller:
            self.app_controller.reload_settings()

        QMessageBox.information(self, "Başarılı", "Ayarlar başarıyla kaydedildi.")

    def add_history_entry(self, text: str):
        history = config_manager.load_history()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history.insert(0, {"time": now_str, "text": text})
        config_manager.save_history(history)
        self.refresh_history_list()

    def refresh_history_list(self):
        self.history_list.clear()
        history = config_manager.load_history()
        for item in history:
            text = f"[{item.get('time', '')}] {item.get('text', '')}"
            self.history_list.addItem(QListWidgetItem(text))

    def copy_selected_history(self):
        current_item = self.history_list.currentItem()
        if current_item:
            full_text = current_item.text()
            # strip timestamp
            if "]" in full_text:
                clean_text = full_text.split("]", 1)[1].strip()
            else:
                clean_text = full_text
            QApplication.clipboard().setText(clean_text)
            QMessageBox.information(self, "Kopyalandı", "Metin panoya kopyalandı.")

    def clear_history(self):
        config_manager.save_history([])
        self.history_list.clear()

    def on_dictate_btn_clicked(self):
        self.request_toggle_dictation.emit()

    def set_recording_state(self, is_recording: bool):
        if is_recording:
            self.dictate_btn.setText("⏹️ Kaydı Durdur")
            self.dictate_btn.setStyleSheet("background-color: #ef4444; color: white;")
            self.status_label.setText("Durum: Kaydediliyor...")
            self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.dictate_btn.setText("🎙️ Dikteyi Başlat")
            self.dictate_btn.setStyleSheet("background-color: #6366f1; color: white;")
            self.status_label.setText("Durum: Hazır | AMD GPU DirectML Aktif")
            self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")

    def show_and_raise(self):
        self.show()
        self.activateWindow()

    def quit_app(self):
        if self.app_controller:
            self.app_controller.quit()
        else:
            QApplication.quit()

    def closeEvent(self, event):
        # Minimize to tray instead of quitting
        event.ignore()
        self.hide()
