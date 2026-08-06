import os
import datetime
import logging
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QRadioButton, QButtonGroup, QStackedWidget, QScrollArea,
    QFrame, QGridLayout, QSystemTrayIcon
)
from src.config import config_manager, get_resource_path
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import model_manager
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.file_transcriber import FileTranscribeWorker
from src.startup import configure_start_with_windows
from src.ui.styles import PREMIUM_STYLE

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
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(PREMIUM_STYLE)

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

        shell_layout = QHBoxLayout(central_widget)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.setSpacing(8)

        brand_layout = QHBoxLayout()
        logo_img = QLabel()
        if os.path.exists(LOGO_PATH):
            pix = QPixmap(LOGO_PATH).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_img.setPixmap(pix)
        brand_text = QVBoxLayout()
        title_label = QLabel("PrimeDictate")
        title_label.setObjectName("brandTitle")
        subtitle_label = QLabel("VOICE WORKSPACE")
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
        nav_items = [
            ("Ana Sayfa", "Genel durum ve hızlı dikte"),
            ("Motor & Davranış", "Dikte motoru ve otomasyon"),
            ("AI & Kurallar", "Metin işleme profilleri"),
            ("Dosya Transkripsiyonu", "Ses ve video dosyaları"),
            ("Ses & Kısayollar", "Mikrofon ve global tuş"),
            ("Geçmiş", "Önceki transkriptler"),
            ("Tanılama", "Gelişmiş teknik kayıtlar"),
        ]
        for index, (label, tooltip) in enumerate(nav_items):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda checked=False, i=index: self._set_page(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            side_layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        side_layout.addStretch()

        privacy_label = QLabel("Yerel kullanım varsayılandır.\nBulut geçişi açık izne bağlıdır.")
        privacy_label.setObjectName("mutedLabel")
        privacy_label.setWordWrap(True)
        side_layout.addWidget(privacy_label)
        shell_layout.addWidget(sidebar)

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

        self.status_label = QLabel("Hazır")
        self.status_label.setObjectName("statusPill")
        header_layout.addWidget(self.status_label)

        self.dictate_btn = QPushButton("Dikteyi Başlat")
        self.dictate_btn.setObjectName("primaryAction")
        self.dictate_btn.clicked.connect(self.on_dictate_btn_clicked)
        header_layout.addWidget(self.dictate_btn)
        content_layout.addLayout(header_layout)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._wrap_page(self._create_dashboard_page()))
        self.pages.addWidget(self._wrap_page(self._create_general_tab()))
        self.pages.addWidget(self._wrap_page(self._create_ai_tab()))
        self.pages.addWidget(self._wrap_page(self._create_file_transcribe_tab()))
        self.pages.addWidget(self._wrap_page(self._create_audio_tab()))
        self.pages.addWidget(self._wrap_page(self._create_history_tab()))
        self.pages.addWidget(self._wrap_page(self._create_dev_tab()))
        content_layout.addWidget(self.pages, 1)

        footer_layout = QHBoxLayout()
        footer_note = QLabel("Ayarlar bu cihazda saklanır. API anahtarları Windows kimlik kasasında korunur.")
        footer_note.setObjectName("mutedLabel")
        footer_layout.addWidget(footer_note)
        footer_layout.addStretch()
        save_btn = QPushButton("Ayarları Kaydet")
        save_btn.setObjectName("secondary_btn")
        save_btn.clicked.connect(self.save_ui_settings)
        footer_layout.addWidget(save_btn)
        content_layout.addLayout(footer_layout)
        shell_layout.addWidget(content, 1)

    def _wrap_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background-color: #090b10;")
        scroll.setWidget(page)
        return scroll

    def _set_page(self, index: int):
        titles = [
            ("Ana Sayfa", "Dikte çalışma alanınızın genel görünümü"),
            ("Motor & Davranış", "Performans, dil ve otomasyon seçenekleri"),
            ("AI & Kurallar", "Transkriptlerin nasıl işleneceğini belirleyin"),
            ("Dosya Transkripsiyonu", "Ses ve video dosyalarını metne dönüştürün"),
            ("Ses & Kısayollar", "Mikrofon ve global erişim ayarları"),
            ("Geçmiş", "Önceki transkriptleri bulun ve yeniden kullanın"),
            ("Tanılama", "Teknik durum ve sorun giderme araçları"),
        ]
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])

    def _create_metric_card(self, label: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        caption = QLabel(label.upper())
        caption.setObjectName("metricLabel")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        layout.addWidget(caption)
        layout.addWidget(value_label)
        return card, value_label

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
        self.hero_title = QLabel("Konuşun. Gerisini PrimeDictate halletsin.")
        self.hero_title.setObjectName("heroTitle")
        hero_caption = QLabel("Global kısayolunuzla herhangi bir uygulamada dikteye başlayın.")
        hero_caption.setObjectName("heroCaption")
        hero_caption.setWordWrap(True)
        self.hero_state = QLabel("Sistem hazır")
        self.hero_state.setObjectName("mutedLabel")
        hero_text.addWidget(self.hero_title)
        hero_text.addWidget(hero_caption)
        hero_text.addSpacing(10)
        hero_text.addWidget(self.hero_state)
        hero_layout.addLayout(hero_text, 1)
        layout.addWidget(hero)

        metrics = QGridLayout()
        metrics.setSpacing(12)
        engine_card, self.dashboard_engine = self._create_metric_card("Aktif Motor", "Yerel CPU")
        model_card, self.dashboard_model = self._create_metric_card("Model", "base")
        hotkey_card, self.dashboard_hotkey = self._create_metric_card("Kısayol", "Ctrl + Alt + D")
        privacy_card, self.dashboard_privacy = self._create_metric_card("Gizlilik", "Yerel")
        metrics.addWidget(engine_card, 0, 0)
        metrics.addWidget(model_card, 0, 1)
        metrics.addWidget(hotkey_card, 1, 0)
        metrics.addWidget(privacy_card, 1, 1)
        layout.addLayout(metrics)
        layout.addStretch()
        return widget

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        pipeline = QFrame()
        pipeline.setObjectName("pipelineCard")
        pipeline_layout = QHBoxLayout(pipeline)
        pipeline_layout.setContentsMargins(18, 14, 18, 14)
        stt_stage = QLabel("1   SESİ METNE DÖNÜŞTÜR\nMotor ve STT modeli")
        stt_stage.setObjectName("pipelineStage")
        arrow = QLabel("→")
        arrow.setObjectName("pipelineArrow")
        cleanup_stage = QLabel("2   METNİ DÜZENLE\nAI sağlayıcısı ve düzenleme modeli")
        cleanup_stage.setObjectName("pipelineStage")
        pipeline_layout.addWidget(stt_stage, 1)
        pipeline_layout.addWidget(arrow)
        pipeline_layout.addWidget(cleanup_stage, 1)
        layout.addWidget(pipeline)

        # Operation Mode Selection
        mode_group = QGroupBox("Çalışma Modu")
        m_box = QHBoxLayout(mode_group)
        self.mode_dictation_rb = QRadioButton("Dikte — konuşmayı yazıya çevir")
        self.mode_assistant_rb = QRadioButton("AI Asistan — sesli komutu uygula")
        self.mode_dictation_rb.setChecked(True)
        m_box.addWidget(self.mode_dictation_rb, 1)
        m_box.addWidget(self.mode_assistant_rb, 1)
        layout.addWidget(mode_group)

        # STT Engine Selection
        engine_group = QGroupBox("Çıkarım Motoru ve Donanım Yapılandırması")
        engine_layout = QVBoxLayout(engine_group)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Çalışma Motoru:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("AMD / Intel / NVIDIA — Vulkan", "vulkan")
        self.backend_combo.addItem("NVIDIA — CUDA / cuDNN", "cuda")
        self.backend_combo.addItem("CPU — Yerel int8", "cpu")
        self.backend_combo.addItem("Bulut — Groq / OpenAI / Gemini", "cloud")
        self.backend_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.backend_combo.setMinimumContentsLength(24)
        self.backend_combo.setToolTip("Vulkan için uyumlu ekran kartı sürücüsü ve Vulkan ile derlenmiş whisper.cpp gerekir.")
        h1.addWidget(self.backend_combo)
        engine_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Whisper Model Boyutu:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3-turbo"])
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

        self.cloud_stt_widget = QWidget()
        cloud_layout = QHBoxLayout(self.cloud_stt_widget)
        cloud_layout.setContentsMargins(0, 0, 0, 0)
        cloud_layout.addWidget(QLabel("Bulut STT sağlayıcısı:"))
        self.cloud_stt_combo = QComboBox()
        self.cloud_stt_combo.addItem("Groq Whisper", "groq")
        self.cloud_stt_combo.addItem("OpenAI Transcribe", "openai")
        self.cloud_stt_combo.addItem("Google Gemini Audio", "gemini")
        cloud_layout.addWidget(self.cloud_stt_combo)
        cloud_layout.addWidget(QLabel("STT modeli:"))
        self.cloud_stt_model_combo = QComboBox()
        self.cloud_stt_model_combo.setEditable(True)
        cloud_layout.addWidget(self.cloud_stt_model_combo)
        engine_layout.addWidget(self.cloud_stt_widget)
        self.cloud_stt_note = QLabel("STT modeli yalnızca sesi yazıya çevirir; düzenleme modeli ayrı seçilir.")
        self.cloud_stt_note.setObjectName("mutedLabel")
        engine_layout.addWidget(self.cloud_stt_note)
        self.cloud_stt_combo.currentIndexChanged.connect(self._update_cloud_stt_models)

        self.vulkan_runtime_widget = QWidget()
        vulkan_layout = QVBoxLayout(self.vulkan_runtime_widget)
        vulkan_layout.setContentsMargins(0, 0, 0, 0)
        runtime_row = QHBoxLayout()
        runtime_row.addWidget(QLabel("Dahili Vulkan Runtime:"))
        self.vulkan_executable_input = QLineEdit()
        self.vulkan_executable_input.setPlaceholderText("Otomatik kullanılır • isteğe bağlı özel whisper-cli.exe")
        runtime_row.addWidget(self.vulkan_executable_input, 1)
        runtime_browse_btn = QPushButton("Özel Runtime")
        runtime_browse_btn.setObjectName("secondary_btn")
        runtime_browse_btn.clicked.connect(self.browse_vulkan_runtime)
        runtime_row.addWidget(runtime_browse_btn)
        vulkan_layout.addLayout(runtime_row)
        self.vulkan_status_label = QLabel("Vulkan runtime kontrol edilmedi")
        self.vulkan_status_label.setObjectName("mutedLabel")
        vulkan_layout.addWidget(self.vulkan_status_label)
        engine_layout.addWidget(self.vulkan_runtime_widget)
        self.backend_combo.currentIndexChanged.connect(self._update_backend_fields)

        layout.addWidget(engine_group)

        # Local Model Downloader Group
        self.model_group = QGroupBox("Yerel Model Durumu ve İndirme Yöneticisi")
        m_layout = QVBoxLayout(self.model_group)

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

        layout.addWidget(self.model_group)

        # Behavior settings
        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)

        self.auto_paste_cb = QCheckBox("Metni aktif pencereye otomatik yapıştır")
        self.restore_clip_cb = QCheckBox("Yapıştırmadan sonra eski panoyu geri yükle")
        self.history_enabled_cb = QCheckBox("Dikte geçmişini bu cihazda sakla")
        self.play_sound_cb = QCheckBox("Kayıt başlangıç ve bitiş seslerini çal")
        self.overlay_cb = QCheckBox("Yüzen ses dalgası göstergesini kullan")
        self.start_windows_cb = QCheckBox("Windows ile otomatik başlat")
        self.cloud_fallback_cb = QCheckBox("Yerel motor başarısızsa buluta geçmeme izin ver")
        self.cloud_fallback_cb.setToolTip("Açıldığında kayıt, yerel işlem başarısız olursa bulut servisine gönderilebilir.")

        b_layout.addWidget(self.auto_paste_cb)
        b_layout.addWidget(self.restore_clip_cb)
        b_layout.addWidget(self.history_enabled_cb)
        b_layout.addWidget(self.play_sound_cb)
        b_layout.addWidget(self.overlay_cb)
        b_layout.addWidget(self.start_windows_cb)
        b_layout.addWidget(self.cloud_fallback_cb)

        layout.addWidget(behavior_group)
        layout.addStretch()
        return widget

    def _update_backend_fields(self, *_):
        backend = self.backend_combo.currentData()
        is_cloud = backend == "cloud"
        self.cloud_stt_widget.setVisible(is_cloud)
        self.cloud_stt_note.setVisible(is_cloud)
        self.model_group.setVisible(not is_cloud)
        self.vulkan_runtime_widget.setVisible(backend == "vulkan")
        if backend == "vulkan":
            self._refresh_vulkan_status()
        if hasattr(self, "model_combo"):
            self.check_selected_model_status()

    def _update_cloud_stt_models(self, *_):
        provider = self.cloud_stt_combo.currentData()
        models = {
            "groq": ["whisper-large-v3-turbo", "whisper-large-v3"],
            "openai": ["gpt-4o-mini-transcribe", "gpt-4o-transcribe", "whisper-1"],
            "gemini": ["gemini-3.6-flash"],
        }
        saved_model = config_manager.get(f"stt_model_{provider}", "")
        self.cloud_stt_model_combo.clear()
        self.cloud_stt_model_combo.addItems(models.get(provider, []))
        if saved_model:
            self.cloud_stt_model_combo.setCurrentText(saved_model)

    def browse_vulkan_runtime(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "İsteğe bağlı özel Vulkan runtime seç",
            "",
            "whisper.cpp CLI (whisper-cli.exe);;Uygulamalar (*.exe)",
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

        cleanup_group = QGroupBox("Yapay Zeka Temizleme ve Kurallar")
        c_layout = QVBoxLayout(cleanup_group)

        self.ai_cleanup_cb = QCheckBox("Akıllı Yapay Zeka İşlemesini Etkinleştir")
        c_layout.addWidget(self.ai_cleanup_cb)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Yapay Zeka Servis Sağlayıcısı:"))
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("Hızlı Kural Tabanlı Motor (Yerel & Ücretsiz)", "rule_based")
        self.ai_provider_combo.addItem("Yerel LLM (Ollama / LM Studio)", "custom_ollama")
        self.ai_provider_combo.addItem("Google Gemini", "gemini")
        self.ai_provider_combo.addItem("xAI Grok", "grok")
        self.ai_provider_combo.addItem("Groq LLM", "groq")
        self.ai_provider_combo.addItem("OpenAI LLM", "openai")
        h1.addWidget(self.ai_provider_combo)
        c_layout.addLayout(h1)

        self.ai_model_widget = QWidget()
        ai_model_layout = QHBoxLayout(self.ai_model_widget)
        ai_model_layout.setContentsMargins(0, 0, 0, 0)
        ai_model_layout.addWidget(QLabel("Düzenleme modeli:"))
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(True)
        ai_model_layout.addWidget(self.ai_model_combo)
        c_layout.addWidget(self.ai_model_widget)

        # Preset Rule Selector
        h_preset = QHBoxLayout()
        h_preset.addWidget(QLabel("Hazır Kural Şablonu:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Standart İmla & Düzeltme", "standard")
        self.preset_combo.addItem("Resmi İş & E-posta Dili", "formal")
        self.preset_combo.addItem("Kodlama & Teknik Terimler", "coding")
        self.preset_combo.addItem("İngilizceye Çevir", "translate_en")
        self.preset_combo.addItem("Maddeler Halinde Özetle", "summarize")
        h_preset.addWidget(self.preset_combo)
        c_layout.addLayout(h_preset)

        # Custom Endpoint for Ollama / LM Studio
        self.custom_provider_widget = QWidget()
        h_ollama = QHBoxLayout(self.custom_provider_widget)
        h_ollama.setContentsMargins(0, 0, 0, 0)
        h_ollama.addWidget(QLabel("Yerel/Özel API Base URL:"))
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("http://localhost:11434/v1")
        h_ollama.addWidget(self.custom_url_input)
        h_ollama.addWidget(QLabel("Model Adı:"))
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setPlaceholderText("llama3.2")
        h_ollama.addWidget(self.custom_model_input)
        c_layout.addWidget(self.custom_provider_widget)

        # API Keys
        self.cloud_keys_widget = QWidget()
        key_layout = QVBoxLayout(self.cloud_keys_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        h_keys = QHBoxLayout()
        self.gemini_key_label = QLabel("Gemini Key:")
        h_keys.addWidget(self.gemini_key_label)
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        h_keys.addWidget(self.gemini_key_input)

        self.grok_key_label = QLabel("Grok Key:")
        h_keys.addWidget(self.grok_key_label)
        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.Password)
        h_keys.addWidget(self.grok_key_input)
        key_layout.addLayout(h_keys)

        h_keys2 = QHBoxLayout()
        self.groq_key_label = QLabel("Groq Key:")
        h_keys2.addWidget(self.groq_key_label)
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        h_keys2.addWidget(self.groq_key_input)

        self.openai_key_label = QLabel("OpenAI Key:")
        h_keys2.addWidget(self.openai_key_label)
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        h_keys2.addWidget(self.openai_key_input)
        key_layout.addLayout(h_keys2)
        c_layout.addWidget(self.cloud_keys_widget)

        c_layout.addWidget(QLabel("Özel Kullanıcı Kuralları (Ek Talimatlar):"))
        self.custom_rules_edit = QTextEdit()
        self.custom_rules_edit.setPlaceholderText("Örn: Her zaman Türkçe cevap ver, özel isimleri koru, üslubu dostane yap...")
        self.custom_rules_edit.setMaximumHeight(80)
        c_layout.addWidget(self.custom_rules_edit)
        self.ai_provider_combo.currentIndexChanged.connect(self._update_ai_provider_fields)

        layout.addWidget(cleanup_group)
        layout.addStretch()
        return widget

    def _update_ai_provider_fields(self, *_):
        provider = self.ai_provider_combo.currentData()
        self.custom_provider_widget.setVisible(provider == "custom_ollama")
        self.ai_model_widget.setVisible(provider in {"gemini", "grok", "groq", "openai"})
        required_key_providers = set()
        if provider in {"gemini", "grok", "groq", "openai"}:
            required_key_providers.add(provider)
        if self.backend_combo.currentData() == "cloud" or self.cloud_fallback_cb.isChecked():
            required_key_providers.add(self.cloud_stt_combo.currentData())
        self.cloud_keys_widget.setVisible(bool(required_key_providers))
        for key_provider, label, field in (
            ("gemini", self.gemini_key_label, self.gemini_key_input),
            ("grok", self.grok_key_label, self.grok_key_input),
            ("groq", self.groq_key_label, self.groq_key_input),
            ("openai", self.openai_key_label, self.openai_key_input),
        ):
            visible = key_provider in required_key_providers
            label.setVisible(visible)
            field.setVisible(visible)
        self._update_ai_models(provider)

    def _update_ai_models(self, provider: str):
        models = {
            "gemini": ["gemini-3.6-flash"],
            "openai": ["gpt-4o-mini"],
            "groq": ["llama-3.3-70b-versatile"],
            "grok": ["grok-beta"],
        }
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(models.get(provider, []))
        saved_model = config_manager.get(f"ai_model_{provider}", "")
        if saved_model:
            self.ai_model_combo.setCurrentText(saved_model)

    def _create_file_transcribe_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Ses veya Video Dosyasını Metne Çevir (.mp3, .wav, .mp4, .m4a)")
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
        h_actions.addStretch()

        g_layout.addLayout(h_actions)
        layout.addWidget(group)
        return widget

    def browse_audio_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Ses/Video Dosyası Seç", "", "Ses ve Video Dosyaları (*.mp3 *.wav *.mp4 *.m4a *.mkv *.flac *.ogg)")
        if file_name:
            self.file_path_input.setText(file_name)

    def start_file_transcription(self):
        if self.app_controller and getattr(self.app_controller.state, "value", "idle") != "idle":
            QMessageBox.warning(self, "İşlem devam ediyor", "Dosya transkripsiyonundan önce aktif dikte işlemini tamamlayın.")
            return
        file_path = self.file_path_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir ses/video dosyası seçin.")
            return

        self.transcribe_file_btn.setEnabled(False)
        self.cancel_transcribe_btn.setEnabled(True)
        self.dictate_btn.setEnabled(False)
        self.file_progress.setValue(10)
        self.file_result_edit.setText("Çeviri işlemi başlatılıyor...")

        self.transcribe_worker = FileTranscribeWorker(file_path)
        self.transcribe_worker.progress.connect(self._on_file_progress)
        self.transcribe_worker.finished.connect(self._on_file_finished)
        self.transcribe_worker.error.connect(self._on_file_error)
        self.transcribe_worker.cancelled.connect(self._on_file_cancelled)
        self.transcribe_worker.start()

    def cancel_file_transcription(self):
        if self.transcribe_worker and self.transcribe_worker.isRunning():
            self.transcribe_worker.requestInterruption()
            self.cancel_transcribe_btn.setEnabled(False)
            self.status_label.setText("İşlem iptal ediliyor")

    def _on_file_progress(self, percent: int, msg: str):
        self.file_progress.setValue(percent)
        self.status_label.setText(f"Dosya Çeviriliyor: {msg}")

    def _on_file_finished(self, file_path: str, text: str):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(100)
        self.file_result_edit.setText(text)
        self.status_label.setText("Dosya çevirisi tamamlandı!")
        QMessageBox.information(self, "Başarılı", "Dosya transkripsiyonu tamamlandı.")

    def _on_file_error(self, err: str):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        QMessageBox.critical(self, "Hata", f"Dosya çevrilirken hata oluştu:\n{err}")

    def _on_file_cancelled(self):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        self.status_label.setText("Dosya transkripsiyonu iptal edildi")

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

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Geçmişte ara...")
        self.history_search.textChanged.connect(self.refresh_history_list)
        layout.addWidget(self.history_search)
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)

        h = QHBoxLayout()
        copy_btn = QPushButton("Seçilen Metni Kopyala")
        copy_btn.clicked.connect(self.copy_selected_history)
        h.addWidget(copy_btn)

        clear_btn = QPushButton("Geçmişi Temizle")
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
        clear_log_btn = QPushButton("Konsolu Temizle")
        clear_log_btn.clicked.connect(lambda: self.log_console.clear())
        h_btn.addWidget(clear_log_btn)

        test_sound_btn = QPushButton("Mikrofon Tanı Bilgisi")
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
        self.backend_combo.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.cloud_stt_combo.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.cloud_fallback_cb.toggled.connect(self._update_ai_provider_fields)

    def check_selected_model_status(self, model_name: str = None):
        backend = self.backend_combo.currentData()
        if backend == "cloud":
            return
        if not model_name:
            model_name = self.model_combo.currentText()

        is_downloaded = model_manager.is_model_downloaded(model_name, backend)
        if is_downloaded:
            self.model_status_label.setText(f"Model '{model_name}' hazır ve bilgisayarda yüklü.")
            self.model_status_label.setStyleSheet("color: #10b981; font-weight: bold;")
            self.model_progress.setValue(100)
            self.download_model_btn.setEnabled(False)
            self.download_model_btn.setText("Model hazır")
        else:
            self.model_status_label.setText(f"Model '{model_name}' henüz bilgisayara indirilmedi.")
            self.model_status_label.setStyleSheet("color: #f59e0b; font-weight: bold;")
            self.model_progress.setValue(0)
            self.download_model_btn.setEnabled(True)
            self.download_model_btn.setText("Seçilen Modeli İndir")

    def download_selected_model(self):
        model_name = self.model_combo.currentText()
        backend = self.backend_combo.currentData()
        self.download_model_btn.setEnabled(False)
        self.download_model_btn.setText("İndiriliyor...")
        model_manager.download_model_async(model_name, backend)

    def _on_model_progress(self, percent: int, msg: str):
        if percent < 0:
            self.model_progress.setRange(0, 0)
        else:
            self.model_progress.setRange(0, 100)
            self.model_progress.setValue(percent)
        self.model_status_label.setText(msg)
        self.model_status_label.setStyleSheet("color: #38bdf8; font-weight: bold;")

    def _on_model_download_finished(self, backend: str, model_name: str, success: bool, error_msg: str):
        self.model_progress.setRange(0, 100)
        if success:
            QMessageBox.information(self, "İndirme Tamamlandı", f"Whisper '{model_name}' modeli başarıyla indirildi ve kullanıma hazır.")
            if backend == self.backend_combo.currentData():
                self.check_selected_model_status(model_name)
        else:
            QMessageBox.critical(self, "İndirme Hatası", f"Model indirilirken hata oluştu:\n{error_msg}")
            if backend == self.backend_combo.currentData():
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

        backend = config_manager.get("stt_backend", "cpu")
        backend_index = self.backend_combo.findData(backend)
        if backend_index < 0:
            backend_index = self.backend_combo.findData("cpu")
        self.backend_combo.setCurrentIndex(backend_index)
        self.vulkan_executable_input.setText(config_manager.get("vulkan_executable", ""))
        cloud_provider = config_manager.get("cloud_stt_provider", "groq")
        cloud_index = self.cloud_stt_combo.findData(cloud_provider)
        if cloud_index >= 0:
            self.cloud_stt_combo.setCurrentIndex(cloud_index)
        self._update_cloud_stt_models()
        self._update_backend_fields()

        model = config_manager.get("model_size", "base")
        if model == "turbo":
            model = "large-v3-turbo"
        self.model_combo.setCurrentText(model)

        lang = config_manager.get("language", "tr")
        lang_idx = self.lang_combo.findData(lang)
        if lang_idx >= 0:
            self.lang_combo.setCurrentIndex(lang_idx)

        self.auto_paste_cb.setChecked(config_manager.get("auto_paste", True))
        self.restore_clip_cb.setChecked(config_manager.get("restore_clipboard", True))
        self.history_enabled_cb.setChecked(config_manager.get("history_enabled", True))
        self.play_sound_cb.setChecked(config_manager.get("play_sound", True))
        self.overlay_cb.setChecked(config_manager.get("overlay_enabled", True))
        self.start_windows_cb.setChecked(config_manager.get("start_with_windows", False))
        self.cloud_fallback_cb.setChecked(config_manager.get("allow_cloud_fallback", False))

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
        self._update_ai_provider_fields()

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
        self._refresh_dashboard()

    def save_ui_settings(self):
        op_mode = "assistant" if self.mode_assistant_rb.isChecked() else "dictation"
        provider = self.ai_provider_combo.currentData()
        backend = self.backend_combo.currentData()
        cloud_provider = self.cloud_stt_combo.currentData()
        if op_mode == "assistant" and provider == "rule_based":
            QMessageBox.warning(
                self,
                "AI sağlayıcısı gerekli",
                "AI Asistan modu için yerel veya bulut tabanlı bir LLM sağlayıcısı seçin."
            )
            return
        vulkan_executable = self.vulkan_executable_input.text().strip()
        if backend == "vulkan" and vulkan_executable and not os.path.isfile(vulkan_executable):
            QMessageBox.warning(self, "Geçersiz Vulkan runtime", "Seçilen whisper-cli.exe dosyası bulunamadı.")
            return
        if backend == "vulkan":
            runtime_ok, runtime_message = VulkanSTTEngine.runtime_status(vulkan_executable or None)
            if not runtime_ok:
                QMessageBox.warning(self, "Vulkan runtime kullanılamıyor", runtime_message)
                return

        settings = {
            "operation_mode": op_mode,
            "stt_backend": backend,
            "model_size": self.model_combo.currentText(),
            "language": self.lang_combo.currentData(),
            "cloud_stt_provider": cloud_provider,
            f"stt_model_{cloud_provider}": self.cloud_stt_model_combo.currentText().strip(),
            "vulkan_executable": vulkan_executable,
            "auto_paste": self.auto_paste_cb.isChecked(),
            "restore_clipboard": self.restore_clip_cb.isChecked(),
            "history_enabled": self.history_enabled_cb.isChecked(),
            "play_sound": self.play_sound_cb.isChecked(),
            "overlay_enabled": self.overlay_cb.isChecked(),
            "start_with_windows": self.start_windows_cb.isChecked(),
            "allow_cloud_fallback": self.cloud_fallback_cb.isChecked(),
            "hotkey": self.hotkey_input.text().strip(),
            "hotkey_mode": self.hotkey_mode_combo.currentData(),
            "audio_device_index": self.mic_combo.currentData(),
            "ai_cleanup_enabled": self.ai_cleanup_cb.isChecked(),
            "ai_cleanup_provider": provider,
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
            QMessageBox.critical(self, "Ayarlar kaydedilemedi", str(exc))
            return

        if self.app_controller:
            self.app_controller.reload_settings()

        self._refresh_dashboard()
        QMessageBox.information(self, "Başarılı", "Ayarlar başarıyla kaydedildi.")

    def _refresh_dashboard(self):
        backend_labels = {
            "vulkan": "AMD / Vulkan",
            "cuda": "NVIDIA CUDA",
            "cpu": "Yerel CPU",
            "cloud": "Bulut STT",
        }
        backend = config_manager.get("stt_backend", "cpu")
        self.dashboard_engine.setText(backend_labels.get(backend, "Yerel CPU"))
        if backend == "cloud":
            cloud_provider = config_manager.get("cloud_stt_provider", "groq")
            dashboard_model = config_manager.get(f"stt_model_{cloud_provider}", cloud_provider)
        else:
            dashboard_model = config_manager.get("model_size", "base")
        self.dashboard_model.setText(dashboard_model)
        self.dashboard_hotkey.setText(config_manager.get("hotkey", "ctrl+alt+d").upper())
        privacy = "Bulut etkin" if backend == "cloud" else "Yerel"
        if config_manager.get("allow_cloud_fallback", False) and backend != "cloud":
            privacy = "Yerel + izinli fallback"
        self.dashboard_privacy.setText(privacy)

    def add_history_entry(self, text: str):
        if not config_manager.get("history_enabled", True):
            return
        history = config_manager.load_history()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history.insert(0, {"time": now_str, "text": text})
        config_manager.save_history(history)
        self.refresh_history_list()

    def refresh_history_list(self):
        self.history_list.clear()
        history = config_manager.load_history()
        query = self.history_search.text().strip().casefold() if hasattr(self, "history_search") else ""
        for item in history:
            raw_text = item.get("text", "")
            if query and query not in raw_text.casefold():
                continue
            display_text = f"{item.get('time', '')}   {raw_text}"
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.UserRole, raw_text)
            self.history_list.addItem(list_item)

    def copy_selected_history(self):
        current_item = self.history_list.currentItem()
        if current_item:
            clean_text = current_item.data(Qt.UserRole) or current_item.text()
            QApplication.clipboard().setText(clean_text)
            QMessageBox.information(self, "Kopyalandı", "Metin panoya kopyalandı.")

    def clear_history(self):
        answer = QMessageBox.question(
            self,
            "Geçmişi temizle",
            "Tüm dikte geçmişi kalıcı olarak silinsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        config_manager.save_history([])
        self.history_list.clear()

    def on_dictate_btn_clicked(self):
        self.request_toggle_dictation.emit()

    def set_recording_state(self, is_recording: bool):
        self.set_app_state("recording" if is_recording else "idle", "Dinleniyor" if is_recording else "Hazır")

    def set_app_state(self, state: str, message: str):
        self.status_label.setText(message)
        self.hero_state.setText(message)
        self.dictate_btn.setEnabled(state in {"idle", "recording"})
        self.dictate_btn.setObjectName("dangerAction" if state == "recording" else "primaryAction")
        self.dictate_btn.setText("Kaydı Durdur" if state == "recording" else "Dikteyi Başlat")
        self.dictate_btn.style().unpolish(self.dictate_btn)
        self.dictate_btn.style().polish(self.dictate_btn)

        colors = {
            "idle": ("#15251f", "#235441", "#69ddb0"),
            "recording": ("#30191d", "#6f2d38", "#ff8794"),
            "transcribing": ("#282316", "#635229", "#f0c86a"),
            "success": ("#15251f", "#235441", "#69ddb0"),
            "error": ("#30191d", "#6f2d38", "#ff8794"),
        }
        bg, border, color = colors.get(state, colors["idle"])
        self.status_label.setStyleSheet(
            f"background-color:{bg}; border:1px solid {border}; border-radius:14px;"
            f"color:{color}; font-weight:650; padding:6px 12px;"
        )

    def show_and_raise(self):
        self.show()
        self.activateWindow()

    def quit_app(self):
        if self.app_controller:
            self.app_controller.quit()
        else:
            QApplication.quit()

    def closeEvent(self, event):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            self.quit_app()
            return
        event.ignore()
        self.hide()
