import os
import sys
import datetime
import logging
from PySide6.QtCore import Qt, Signal, QTimer, QObject
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QGroupBox, QComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QRadioButton, QButtonGroup
)
from src.config import config_manager, get_resource_path, PRESET_PROMPTS
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import model_manager
from src.engine.file_transcriber import FileTranscribeWorker
from src.ui.styles import DARK_GLASS_STYLE

LOGO_PATH = get_resource_path("PrimeDictate-Logo.png")

class QtLogHandler(logging.Handler, QObject):
    log_signal = Signal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

class MainWindow(QMainWindow):
    request_toggle_dictation = Signal()

    def __init__(self, app_controller=None):
        super().__init__()
        self.app_controller = app_controller
        self.setWindowTitle("PrimeDictate - Pro Sesli Yazma ve Yapay Zeka Asistanı")
        self.resize(860, 720)
        self.setStyleSheet(DARK_GLASS_STYLE)

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self.transcribe_worker = None
        self._setup_ui()
        self.load_settings_to_ui()
        self._setup_log_stream()
        self._connect_model_manager_signals()

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
            pix = QPixmap(LOGO_PATH).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_img.setPixmap(pix)
        header_layout.addWidget(logo_img)

        title_layout = QVBoxLayout()
        title_label = QLabel("PrimeDictate Pro")
        title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffffff;")
        subtitle_label = QLabel("Yüksek Performanslı Sesli Yazma ve Yapay Zeka Komut Asistanı")
        subtitle_label.setStyleSheet("font-size: 13px; color: #94a3b8;")
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # Action Buttons
        self.dictate_btn = QPushButton("🎙️ Dikteyi Başlat")
        self.dictate_btn.setMinimumHeight(42)
        self.dictate_btn.clicked.connect(self.on_dictate_btn_clicked)
        header_layout.addWidget(self.dictate_btn)

        main_layout.addLayout(header_layout)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_general_tab(), "⚙️ Genel & Motor")
        self.tabs.addTab(self._create_ai_tab(), "🤖 Yapay Zeka & Kurallar")
        self.tabs.addTab(self._create_file_transcribe_tab(), "📁 Ses/Video Çevirici")
        self.tabs.addTab(self._create_audio_tab(), "🎤 Kısayol & Ses")
        self.tabs.addTab(self._create_history_tab(), "📜 Dikte Geçmişi")
        self.tabs.addTab(self._create_dev_tab(), "🛠️ Canlı Log Konsolu")
        main_layout.addWidget(self.tabs)

        # --- Footer ---
        footer_layout = QHBoxLayout()
        self.status_label = QLabel("Durum: Hazır | Donanım Hızlandırmalı Motor Aktif")
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

        # Operation Mode Selection
        mode_group = QGroupBox("Çalışma Modu")
        m_box = QHBoxLayout(mode_group)
        self.mode_dictation_rb = QRadioButton("🎙️ Dikte Modu (Konuşulanı Aynen/Temizleyerek Yaz)")
        self.mode_assistant_rb = QRadioButton("🧠 Yapay Zeka Komut Asistanı (Söylenen Komutu Uygula & Cevabı Yaz)")
        self.mode_dictation_rb.setChecked(True)
        m_box.addWidget(self.mode_dictation_rb)
        m_box.addWidget(self.mode_assistant_rb)
        layout.addWidget(mode_group)

        # STT Engine Selection
        engine_group = QGroupBox("Çıkarım Motoru ve Donanım Yapılandırması")
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
        self.model_combo.currentTextChanged.connect(self.check_selected_model_status)
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

        # Local Model Downloader Group
        model_group = QGroupBox("Yerel Model Durumu ve İndirme Yöneticisi")
        m_layout = QVBoxLayout(model_group)

        self.model_status_label = QLabel("Model Durumu Kontrol Ediliyor...")
        self.model_status_label.setStyleSheet("color: #cbd5e1; font-weight: 500;")
        m_layout.addWidget(self.model_status_label)

        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.model_progress.setTextVisible(True)
        m_layout.addWidget(self.model_progress)

        h_dl = QHBoxLayout()
        self.download_model_btn = QPushButton("📥 Seçilen Modeli Şimdi İndir")
        self.download_model_btn.clicked.connect(self.download_selected_model)
        h_dl.addWidget(self.download_model_btn)
        h_dl.addStretch()
        m_layout.addLayout(h_dl)

        layout.addWidget(model_group)

        # Behavior settings
        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)

        self.auto_paste_cb = QCheckBox("Dikte edilen metni otomatik aktif pencereye yapıştır (Ctrl+V)")
        self.restore_clip_cb = QCheckBox("Yapıştırma sonrası eski panoyu otomatik geri yükle")
        self.play_sound_cb = QCheckBox("Kayıt başlarken ve biterken sesli uyarı ver")
        self.overlay_cb = QCheckBox("Ekran üzerinde yüzen ses dalgası kapsülünü (Overlay Widget) göster")

        b_layout.addWidget(self.auto_paste_cb)
        b_layout.addWidget(self.restore_clip_cb)
        b_layout.addWidget(self.play_sound_cb)
        b_layout.addWidget(self.overlay_cb)

        layout.addWidget(behavior_group)
        layout.addStretch()
        return widget

    def _create_ai_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        cleanup_group = QGroupBox("Yapay Zeka Temizleme ve Kurallar")
        c_layout = QVBoxLayout(cleanup_group)

        self.ai_cleanup_cb = QCheckBox("Akıllı Yapay Zeka İşlemesini Etkinleştir")
        c_layout.addWidget(self.ai_cleanup_cb)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Yapay Zeka Servis Sağlayıcısı:"))
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("Hızlı Kural Tabanlı Motor (Yerel & Ücretsiz)", "rule_based")
        self.ai_provider_combo.addItem("Özel Yerel LLM (Ollama / LM Studio / OpenRouter)", "custom_ollama")
        self.ai_provider_combo.addItem("Google Gemini 2.5 Flash API", "gemini")
        self.ai_provider_combo.addItem("xAI Grok API (Grok-Beta)", "grok")
        self.ai_provider_combo.addItem("Groq LLM (Llama 3.3 70B)", "groq")
        self.ai_provider_combo.addItem("OpenAI LLM (GPT-4o Mini)", "openai")
        h1.addWidget(self.ai_provider_combo)
        c_layout.addLayout(h1)

        # Preset Rule Selector
        h_preset = QHBoxLayout()
        h_preset.addWidget(QLabel("Hazır Kural Şablonu:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("📝 Standart İmla & Düzeltme Modu", "standard")
        self.preset_combo.addItem("💼 Resmi İş & E-posta Dili", "formal")
        self.preset_combo.addItem("💻 Kodlama & Yazılım Terimleri Koruma", "coding")
        self.preset_combo.addItem("🌐 Anında İngilizceye Çevir", "translate_en")
        self.preset_combo.addItem("📊 Maddeler Haline Getir & Özetle", "summarize")
        h_preset.addWidget(self.preset_combo)
        c_layout.addLayout(h_preset)

        # Custom Endpoint for Ollama / LM Studio
        h_ollama = QHBoxLayout()
        h_ollama.addWidget(QLabel("Yerel/Özel API Base URL:"))
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("http://localhost:11434/v1")
        h_ollama.addWidget(self.custom_url_input)
        h_ollama.addWidget(QLabel("Model Adı:"))
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setPlaceholderText("llama3.2")
        h_ollama.addWidget(self.custom_model_input)
        c_layout.addLayout(h_ollama)

        # API Keys
        h_keys = QHBoxLayout()
        h_keys.addWidget(QLabel("Gemini Key:"))
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        h_keys.addWidget(self.gemini_key_input)

        h_keys.addWidget(QLabel("Grok Key:"))
        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.Password)
        h_keys.addWidget(self.grok_key_input)
        c_layout.addLayout(h_keys)

        h_keys2 = QHBoxLayout()
        h_keys2.addWidget(QLabel("Groq Key:"))
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        h_keys2.addWidget(self.groq_key_input)

        h_keys2.addWidget(QLabel("OpenAI Key:"))
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        h_keys2.addWidget(self.openai_key_input)
        c_layout.addLayout(h_keys2)

        c_layout.addWidget(QLabel("Özel Kullanıcı Kuralları (Ek Talimatlar):"))
        self.custom_rules_edit = QTextEdit()
        self.custom_rules_edit.setPlaceholderText("Örn: Her zaman Türkçe cevap ver, özel isimleri koru, üslubu dostane yap...")
        self.custom_rules_edit.setMaximumHeight(80)
        c_layout.addWidget(self.custom_rules_edit)

        layout.addWidget(cleanup_group)
        layout.addStretch()
        return widget

    def _create_file_transcribe_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Ses veya Video Dosyasını Metne Çevir (.mp3, .wav, .mp4, .m4a)")
        g_layout = QVBoxLayout(group)

        h_file = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Bir ses veya video dosyası seçin...")
        h_file.addWidget(self.file_path_input)

        browse_btn = QPushButton("📁 Gözat...")
        browse_btn.clicked.connect(self.browse_audio_file)
        h_file.addWidget(browse_btn)

        self.transcribe_file_btn = QPushButton("⚡ Çeviriyi Başlat")
        self.transcribe_file_btn.clicked.connect(self.start_file_transcription)
        h_file.addWidget(self.transcribe_file_btn)
        g_layout.addLayout(h_file)

        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        g_layout.addWidget(self.file_progress)

        g_layout.addWidget(QLabel("Çevrilen Metin:"))
        self.file_result_edit = QTextEdit()
        g_layout.addWidget(self.file_result_edit)

        h_actions = QHBoxLayout()
        copy_file_text_btn = QPushButton("📋 Metni Kopyala")
        copy_file_text_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.file_result_edit.toPlainText()))
        h_actions.addWidget(copy_file_text_btn)

        save_file_text_btn = QPushButton("💾 Metni Dosyaya Kaydet")
        save_file_text_btn.clicked.connect(self.save_file_text)
        h_actions.addWidget(save_file_text_btn)
        h_actions.addStretch()

        g_layout.addLayout(h_actions)
        layout.addWidget(group)
        return widget

    def browse_audio_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Ses/Video Dosyası Seç", "", "Ses ve Video Dosyaları (*.mp3 *.wav *.mp4 *.m4a *.mkv *.flac *.ogg)")
        if file_name:
            self.file_path_input.setText(file_name)

    def start_file_transcription(self):
        file_path = self.file_path_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir ses/video dosyası seçin.")
            return

        self.transcribe_file_btn.setEnabled(False)
        self.file_progress.setValue(10)
        self.file_result_edit.setText("Çeviri işlemi başlatılıyor...")

        self.transcribe_worker = FileTranscribeWorker(file_path)
        self.transcribe_worker.progress.connect(self._on_file_progress)
        self.transcribe_worker.finished.connect(self._on_file_finished)
        self.transcribe_worker.error.connect(self._on_file_error)
        self.transcribe_worker.start()

    def _on_file_progress(self, percent: int, msg: str):
        self.file_progress.setValue(percent)
        self.status_label.setText(f"Dosya Çeviriliyor: {msg}")

    def _on_file_finished(self, file_path: str, text: str):
        self.transcribe_file_btn.setEnabled(True)
        self.file_progress.setValue(100)
        self.file_result_edit.setText(text)
        self.status_label.setText("Dosya çevirisi tamamlandı!")
        QMessageBox.information(self, "Başarılı", "Dosya transkripsiyonu tamamlandı.")

    def _on_file_error(self, err: str):
        self.transcribe_file_btn.setEnabled(True)
        self.file_progress.setValue(0)
        QMessageBox.critical(self, "Hata", f"Dosya çevrilirken hata oluştu:\n{err}")

    def save_file_text(self):
        text = self.file_result_edit.toPlainText()
        if not text:
            return
        file_name, _ = QFileDialog.getSaveFileName(self, "Metni Kaydet", "transkripsiyon.txt", "Metin Dosyası (*.txt)")
        if file_name:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(self, "Kaydedildi", f"Metin kaydedildi: {file_name}")

    def _create_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

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

    def _create_dev_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        dev_group = QGroupBox("Geliştirici Tanı Ekranı ve Canlı Log Konsolu")
        d_layout = QVBoxLayout(dev_group)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #020617; color: #38bdf8; font-family: 'Consolas', monospace; font-size: 11px;")
        d_layout.addWidget(self.log_console)

        h_btn = QHBoxLayout()
        clear_log_btn = QPushButton("🧹 Konsolu Temizle")
        clear_log_btn.clicked.connect(lambda: self.log_console.clear())
        h_btn.addWidget(clear_log_btn)

        test_sound_btn = QPushButton("🔊 Mikrofon Tanı Bilgisi")
        test_sound_btn.clicked.connect(self.test_audio_input)
        h_btn.addWidget(test_sound_btn)

        h_btn.addStretch()
        d_layout.addLayout(h_btn)

        layout.addWidget(dev_group)
        return widget

    def _setup_log_stream(self):
        handler = QtLogHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        handler.log_signal.connect(self._append_log)
        logging.getLogger().addHandler(handler)

    def _append_log(self, text: str):
        self.log_console.append(text)

    def test_audio_input(self):
        devices = AudioRecorder.get_input_devices()
        msg = f"Bulunan Mikrofon Sayısı: {len(devices)}\n\n"
        for d in devices:
            msg += f"• [{d['index']}] {d['name']} ({d['default_samplerate']}Hz, {d['channels']} ch)\n"
        QMessageBox.information(self, "Mikrofon Tanı Bilgisi", msg)

    def _connect_model_manager_signals(self):
        model_manager.progress.connect(self._on_model_progress)
        model_manager.download_finished.connect(self._on_model_download_finished)

    def check_selected_model_status(self, model_name: str = None):
        if not model_name:
            model_name = self.model_combo.currentText()

        is_downloaded = model_manager.is_model_downloaded(model_name)
        if is_downloaded:
            self.model_status_label.setText(f"✅ Model '{model_name}' hazır ve bilgisayarda yüklü.")
            self.model_status_label.setStyleSheet("color: #10b981; font-weight: bold;")
            self.model_progress.setValue(100)
            self.download_model_btn.setEnabled(False)
            self.download_model_btn.setText("✅ Model İndirilmiş")
        else:
            self.model_status_label.setText(f"⚠️ Model '{model_name}' henüz bilgisayara indirilmedi.")
            self.model_status_label.setStyleSheet("color: #f59e0b; font-weight: bold;")
            self.model_progress.setValue(0)
            self.download_model_btn.setEnabled(True)
            self.download_model_btn.setText("📥 Seçilen Modeli Şimdi İndir")

    def download_selected_model(self):
        model_name = self.model_combo.currentText()
        self.download_model_btn.setEnabled(False)
        self.download_model_btn.setText("⏳ İndiriliyor...")
        model_manager.download_model_async(model_name)

    def _on_model_progress(self, percent: int, msg: str):
        self.model_progress.setValue(percent)
        self.model_status_label.setText(f"⏳ {msg}")
        self.model_status_label.setStyleSheet("color: #38bdf8; font-weight: bold;")

    def _on_model_download_finished(self, model_name: str, success: bool, error_msg: str):
        if success:
            QMessageBox.information(self, "İndirme Tamamlandı", f"Whisper '{model_name}' modeli başarıyla indirildi ve kullanıma hazır.")
            self.check_selected_model_status(model_name)
        else:
            QMessageBox.critical(self, "İndirme Hatası", f"Model indirilirken hata oluştu:\n{error_msg}")
            self.check_selected_model_status(model_name)

    def refresh_mic_list(self):
        self.mic_combo.clear()
        self.mic_combo.addItem("Varsayılan Sistem Mikrofonu", None)
        devices = AudioRecorder.get_input_devices()
        for dev in devices:
            self.mic_combo.addItem(f"{dev['name']}", dev['index'])

    def load_settings_to_ui(self):
        op_mode = config_manager.get("operation_mode", "dictation")
        if op_mode == "assistant":
            self.mode_assistant_rb.setChecked(True)
        else:
            self.mode_dictation_rb.setChecked(True)

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
        self.restore_clip_cb.setChecked(config_manager.get("restore_clipboard", True))
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

        preset_key = config_manager.get("preset_prompt_key", "standard")
        preset_idx = self.preset_combo.findData(preset_key)
        if preset_idx >= 0:
            self.preset_combo.setCurrentIndex(preset_idx)

        self.custom_url_input.setText(config_manager.get("custom_api_base_url", "http://localhost:11434/v1"))
        self.custom_model_input.setText(config_manager.get("custom_model_name", "llama3.2"))

        self.gemini_key_input.setText(config_manager.get("api_key_gemini", ""))
        self.grok_key_input.setText(config_manager.get("api_key_grok", ""))
        self.groq_key_input.setText(config_manager.get("api_key_groq", ""))
        self.openai_key_input.setText(config_manager.get("api_key_openai", ""))
        self.custom_rules_edit.setText(config_manager.get("custom_user_rules", ""))

        self.check_selected_model_status(model)
        self.refresh_history_list()

    def save_ui_settings(self):
        op_mode = "assistant" if self.mode_assistant_rb.isChecked() else "dictation"
        config_manager.set("operation_mode", op_mode)

        backend_keys = ["cuda", "directml", "vulkan", "cpu", "cloud"]
        config_manager.set("stt_backend", backend_keys[self.backend_combo.currentIndex()])
        config_manager.set("model_size", self.model_combo.currentText())
        config_manager.set("language", self.lang_combo.currentData())

        config_manager.set("auto_paste", self.auto_paste_cb.isChecked())
        config_manager.set("restore_clipboard", self.restore_clip_cb.isChecked())
        config_manager.set("play_sound", self.play_sound_cb.isChecked())
        config_manager.set("overlay_enabled", self.overlay_cb.isChecked())

        config_manager.set("hotkey", self.hotkey_input.text().strip())
        config_manager.set("hotkey_mode", self.hotkey_mode_combo.currentData())
        config_manager.set("audio_device_index", self.mic_combo.currentData())

        config_manager.set("ai_cleanup_enabled", self.ai_cleanup_cb.isChecked())
        config_manager.set("ai_cleanup_provider", self.ai_provider_combo.currentData())
        config_manager.set("preset_prompt_key", self.preset_combo.currentData())
        config_manager.set("custom_api_base_url", self.custom_url_input.text().strip())
        config_manager.set("custom_model_name", self.custom_model_input.text().strip())
        config_manager.set("api_key_gemini", self.gemini_key_input.text().strip())
        config_manager.set("api_key_grok", self.grok_key_input.text().strip())
        config_manager.set("api_key_groq", self.groq_key_input.text().strip())
        config_manager.set("api_key_openai", self.openai_key_input.text().strip())
        config_manager.set("custom_user_rules", self.custom_rules_edit.toPlainText().strip())

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
            self.status_label.setText("Durum: Hazır | Donanım Hızlandırmalı Motor Aktif")
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
        event.ignore()
        self.hide()
