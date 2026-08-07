import os
import datetime
import logging
from PySide6.QtCore import Qt, Signal, QObject, QUrl
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QComboBox, QLineEdit, QPushButton, QCheckBox, QTextEdit,
    QProgressBar, QListWidget, QListWidgetItem, QMessageBox, QApplication,
    QFileDialog, QButtonGroup, QStackedWidget, QScrollArea,
    QFrame, QGridLayout, QSystemTrayIcon
)
from src import __version__
from src.config import STT_LANGUAGES, STT_LANGUAGE_NAMES_TR, config_manager, get_resource_path
from src.i18n import get_language, set_language, t
from src.metadata import EMAIL, REPOSITORY, STUDIO, WEBSITE
from src.audio.recorder import AudioRecorder
from src.engine.model_manager import model_manager
from src.engine.stt_vulkan import VulkanSTTEngine
from src.engine.file_transcriber import FileTranscribeWorker
from src.startup import configure_start_with_windows
from src.ui.styles import PREMIUM_STYLE
from src.ui.brand import app_mark_pixmap

LOGO_PATH = get_resource_path(os.path.join("assets", "PrimeDictate-AppIcon.png"))

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
    PAGE_DEFINITIONS = (
        ("Ana Sayfa", "Genel durum ve hızlı dikte", "Dikte çalışma alanınızın genel görünümü", "_create_dashboard_page"),
        ("Ses → Metin", "STT motoru, model ve çalışma konumu", "Sesin nerede ve hangi modelle yazıya dönüştürüleceğini belirleyin", "_create_general_tab"),
        ("Metin İşleme & API", "Düzenleme yöntemi ve servis erişimi", "Ham STT çıktısının düzenlenmesini ve servis erişimlerini yönetin", "_create_ai_tab"),
        ("Dosya Transkripsiyonu", "Ses ve video dosyaları", "Ses ve video dosyalarını metne dönüştürün", "_create_file_transcribe_tab"),
        ("Ses & Kısayollar", "Mikrofon ve global tuş", "Mikrofon ve global erişim ayarları", "_create_audio_tab"),
        ("Geçmiş", "Önceki transkriptler", "Önceki transkriptleri bulun ve yeniden kullanın", "_create_history_tab"),
        ("Tanılama", "Gelişmiş teknik kayıtlar", "Teknik durum ve sorun giderme araçları", "_create_dev_tab"),
        ("Hakkında", "Ürün, sürüm ve geliştirici bilgileri", "PrimeDictate hakkında", "_create_about_page"),
    )

    def __init__(self, app_controller=None):
        super().__init__()
        self.app_controller = app_controller
        set_language(config_manager.get("ui_language", "tr"))
        self.setWindowTitle(f"PrimeDictate - {t('Yapay Zeka Destekli Sesli Yazma')}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(PREMIUM_STYLE)

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self.transcribe_worker = None
        self._setup_ui()
        self.load_settings_to_ui()
        self._apply_ui_language()
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
        for index, (label, tooltip, _, _) in enumerate(self.PAGE_DEFINITIONS):
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
        title, _, subtitle, _ = self.PAGE_DEFINITIONS[index]
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.page_title.setText(t(title))
        self.page_subtitle.setText(t(subtitle))
        self.footer_widget.setVisible(index != len(self.PAGE_DEFINITIONS) - 1)

    def _apply_ui_language(self):
        self.setWindowTitle(f"PrimeDictate - {t('Yapay Zeka Destekli Sesli Yazma')}")
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
                widget.setText(t(widget.text()))
            elif isinstance(widget, QGroupBox):
                widget.setTitle(t(widget.title()))
            if isinstance(widget, (QLineEdit, QTextEdit)):
                widget.setPlaceholderText(t(widget.placeholderText()))
            if widget.toolTip():
                widget.setToolTip(t(widget.toolTip()))
            if isinstance(widget, QComboBox):
                for index in range(widget.count()):
                    widget.setItemText(index, t(widget.itemText(index)))
        if hasattr(self, "about_version_label"):
            self.about_version_label.setText(f"{t('Sürüm')} {__version__}  •  GPL-3.0")
        if hasattr(self, "lang_combo"):
            for index in range(self.lang_combo.count()):
                code = self.lang_combo.itemData(index)
                if code == "auto":
                    self.lang_combo.setItemText(index, t("Otomatik algıla"))
                elif code in STT_LANGUAGES:
                    self.lang_combo.setItemText(index, f"{self._language_name(code)} ({code})")
        self._set_page(self.pages.currentIndex())
        self._update_backend_fields()
        self._update_ai_provider_fields()

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
        self.hero_title = QLabel("Konuşun. Gerisini PrimeDictate halletsin.")
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
        layout.addWidget(hero)

        self.dashboard_metrics_widget = QWidget()
        metrics = QGridLayout(self.dashboard_metrics_widget)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setSpacing(12)
        engine_card, self.dashboard_engine = self._create_metric_card("Aktif Motor", "Yerel CPU")
        model_card, self.dashboard_model = self._create_metric_card("Model", "base")
        hotkey_card, self.dashboard_hotkey = self._create_metric_card("Kısayol", "Ctrl + Alt + D")
        privacy_card, self.dashboard_privacy = self._create_metric_card("Gizlilik", "Yerel")
        language_card, self.dashboard_language = self._create_metric_card("Konuşma Dili", "Turkish (tr)")
        metrics.addWidget(engine_card, 0, 0)
        metrics.addWidget(model_card, 0, 1)
        metrics.addWidget(language_card, 0, 2)
        metrics.addWidget(hotkey_card, 1, 0)
        metrics.addWidget(privacy_card, 1, 1, 1, 2)
        layout.addWidget(self.dashboard_metrics_widget)

        self.dashboard_onboarding = QFrame()
        self.dashboard_onboarding.setObjectName("onboardingCard")
        onboarding_layout = QVBoxLayout(self.dashboard_onboarding)
        onboarding_layout.setContentsMargins(22, 20, 22, 20)
        onboarding_layout.setSpacing(10)
        onboarding_eyebrow = QLabel("BAŞLANGIÇ")
        onboarding_eyebrow.setObjectName("sectionEyebrow")
        onboarding_title = QLabel("PrimeDictate'i kullanıma hazırlayın")
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
        onboarding_action.clicked.connect(lambda: self._set_page(1))
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
        engine_layout.setSpacing(12)

        engine_intro = QLabel(
            "Bu aşama yalnızca konuşmayı yazıya çevirir. Yerel seçenekler sesi cihazda işler; "
            "bulut seçeneği ses kaydını seçtiğiniz servise gönderir."
        )
        engine_intro.setObjectName("sectionDescription")
        engine_intro.setWordWrap(True)
        engine_layout.addWidget(engine_intro)

        h1 = QHBoxLayout()
        backend_label = QLabel("STT çalışma konumu")
        backend_label.setObjectName("fieldLabel")
        h1.addWidget(backend_label)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Yerel GPU • Vulkan (AMD / Intel / NVIDIA)", "vulkan")
        self.backend_combo.addItem("Yerel GPU • CUDA (NVIDIA)", "cuda")
        self.backend_combo.addItem("Yerel CPU • Özel ve uyumlu", "cpu")
        self.backend_combo.addItem("Bulut STT • Groq / OpenAI / Gemini", "cloud")
        self.backend_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.backend_combo.setMinimumContentsLength(24)
        self.backend_combo.setToolTip("Vulkan için uyumlu ekran kartı sürücüsü ve Vulkan ile derlenmiş whisper.cpp gerekir.")
        h1.addWidget(self.backend_combo, 1)
        engine_layout.addLayout(h1)

        self.backend_description = QLabel()
        self.backend_description.setObjectName("infoNote")
        self.backend_description.setWordWrap(True)
        engine_layout.addWidget(self.backend_description)

        self.local_stt_widget = QFrame()
        self.local_stt_widget.setObjectName("subCard")
        local_layout = QVBoxLayout(self.local_stt_widget)
        local_layout.setContentsMargins(14, 13, 14, 13)
        local_layout.setSpacing(10)
        local_title = QLabel("YEREL WHISPER YAPILANDIRMASI")
        local_title.setObjectName("sectionEyebrow")
        local_layout.addWidget(local_title)

        h2 = QHBoxLayout()
        model_label = QLabel("Yerel model boyutu")
        model_label.setObjectName("fieldLabel")
        h2.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3-turbo"])
        self.model_combo.currentTextChanged.connect(self.check_selected_model_status)
        h2.addWidget(self.model_combo, 1)
        local_layout.addLayout(h2)
        model_hint = QLabel(
            "Küçük modeller daha hızlı ve hafiftir; büyük modeller daha fazla bellek kullanır, "
            "genellikle daha yüksek doğruluk sağlar. Bu seçim yalnızca yerel motorları etkiler."
        )
        model_hint.setObjectName("mutedLabel")
        model_hint.setWordWrap(True)
        local_layout.addWidget(model_hint)

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
        self.cloud_stt_model_combo.setEditable(True)
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

        h3 = QHBoxLayout()
        language_label = QLabel("Konuşma dili")
        language_label.setObjectName("fieldLabel")
        h3.addWidget(language_label)
        self.lang_combo = QComboBox()
        self.lang_combo.setEditable(True)
        self.lang_combo.setInsertPolicy(QComboBox.NoInsert)
        self.lang_combo.addItem("Otomatik algıla", "auto")
        featured_languages = ["tr", "en", "de", "fr", "es", "it", "pt", "ar", "ru", "zh", "ja", "ko"]
        for code in featured_languages:
            self.lang_combo.addItem(f"{self._language_name(code)} ({code})", code)
        for code, name in sorted(STT_LANGUAGES.items(), key=lambda item: item[1]):
            if code not in featured_languages:
                self.lang_combo.addItem(f"{self._language_name(code)} ({code})", code)
        self.lang_combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.lang_combo.completer().setFilterMode(Qt.MatchContains)
        h3.addWidget(self.lang_combo, 1)
        engine_layout.addLayout(h3)
        self.backend_combo.currentIndexChanged.connect(self._update_backend_fields)

        layout.addWidget(engine_group)

        self.model_group = QGroupBox("Yerel Whisper Modeli")
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

        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)
        b_layout.setSpacing(10)

        self.auto_paste_cb = QCheckBox("Metni aktif pencereye otomatik yapıştır")
        self.restore_clip_cb = QCheckBox("Yapıştırmadan sonra önceki pano metnini geri yükle")
        self.restore_clip_cb.setToolTip("Yalnızca düz metin korunur; resim, dosya ve biçimlendirilmiş pano içerikleri geri yüklenmez.")
        self.history_enabled_cb = QCheckBox("Dikte geçmişini bu cihazda sakla")
        self.play_sound_cb = QCheckBox("Kayıt başlangıç ve bitiş seslerini çal")
        self.overlay_cb = QCheckBox("Yüzen ses dalgası göstergesini kullan")
        self.start_windows_cb = QCheckBox("Windows ile otomatik başlat")
        self.cloud_fallback_cb = QCheckBox("Yerel motor başarısızsa buluta geçmeme izin ver")
        self.cloud_fallback_cb.setToolTip("Açıldığında ses kaydı, yalnızca yerel işlem başarısız olursa seçili bulut STT servisine gönderilebilir.")
        self.cloud_fallback_cb.toggled.connect(self._update_backend_fields)

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
        uses_fallback = not is_cloud and self.cloud_fallback_cb.isChecked()
        descriptions = {
            "vulkan": "Vulkan, desteklenen ekran kartında yerel whisper.cpp çalıştırır. Ses cihazdan çıkmaz; AMD ve Intel GPU'lar için önerilen hızlandırma seçeneğidir.",
            "cuda": "CUDA, Whisper modelini NVIDIA ekran kartında yerel olarak çalıştırır. Uyumlu NVIDIA sürücüsü ve yeterli ekran kartı belleği gerekir.",
            "cpu": "CPU, modeli tamamen bilgisayarınızda çalıştırır. En geniş uyumluluğu ve yerel gizliliği sağlar; büyük modellerde daha yavaş olabilir.",
            "cloud": "Bulut STT, ses kaydını seçilen sağlayıcıya yükler ve uzak bir transkripsiyon modeli kullanır. Yerel model indirilmez veya kullanılmaz.",
        }
        self.backend_description.setText(t(descriptions.get(backend, "")))
        self.local_stt_widget.setVisible(not is_cloud)
        self.cloud_stt_widget.setVisible(is_cloud or uses_fallback)
        self.model_group.setVisible(not is_cloud)
        self.vulkan_runtime_widget.setVisible(backend == "vulkan")
        self.cloud_fallback_cb.setEnabled(not is_cloud)
        if is_cloud:
            self.cloud_stt_title.setText(t("BULUT STT YAPILANDIRMASI • AKTİF MOTOR"))
            self.cloud_stt_note.setText(t(
                "Ses kaydı bu sağlayıcıya gönderilir. Buradaki model yalnızca sesi yazıya çevirir; "
                "metin düzenleme modeli Metin İşleme & API sayfasında ayrı seçilir."
            ))
        else:
            self.cloud_stt_title.setText(t("BULUT STT YAPILANDIRMASI • YEDEK MOTOR"))
            self.cloud_stt_note.setText(t(
                "Bu servis yalnızca yerel STT başarısız olursa kullanılır. Bulut geçişini kapatırsanız ses cihazdan çıkmaz."
            ))
        if backend == "vulkan":
            self._refresh_vulkan_status()
        if not is_cloud and hasattr(self, "model_combo"):
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
        notes = {
            "groq": "Groq, Whisper tabanlı uzak STT modelleri kullanır. Seçilen konuşma dili API'ye standart dil kodu olarak gönderilir.",
            "openai": "OpenAI dil yönlendirmesi seçilen model ailesine göre uygulanır. Özel bir model adı kullanırsanız uyumsuz dil parametresi gönderilmez.",
            "gemini": "Gemini Audio üretken ve çok kipli bir bulut modelidir. Dil seçimi yapılandırılmış STT alanı yerine güvenli transkripsiyon talimatıyla yönlendirilir; sonuç davranışı modele bağlıdır.",
        }
        self.cloud_provider_note.setText(t(notes.get(provider, "")))

    def browse_vulkan_runtime(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            t("İsteğe bağlı özel Vulkan runtime seç"),
            "",
            t("whisper.cpp CLI (whisper-cli.exe);;Uygulamalar (*.exe)"),
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
        self.ai_provider_combo.addItem("xAI Grok • Bulut LLM", "grok")
        self.ai_provider_combo.addItem("Groq • Bulut LLM", "groq")
        self.ai_provider_combo.addItem("OpenAI • Bulut LLM", "openai")
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
        self.ai_model_combo.setEditable(True)
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
        self.gemini_key_label = QLabel("Gemini API anahtarı")
        self.gemini_key_label.setObjectName("fieldLabel")
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_key_input.setPlaceholderText("Google AI Studio API anahtarı")
        keys_grid.addWidget(self.gemini_key_label, 0, 0)
        keys_grid.addWidget(self.gemini_key_input, 0, 1)

        self.grok_key_label = QLabel("Grok API anahtarı")
        self.grok_key_label.setObjectName("fieldLabel")
        self.grok_key_input = QLineEdit()
        self.grok_key_input.setEchoMode(QLineEdit.Password)
        self.grok_key_input.setPlaceholderText("xAI API anahtarı")
        keys_grid.addWidget(self.grok_key_label, 1, 0)
        keys_grid.addWidget(self.grok_key_input, 1, 1)

        self.groq_key_label = QLabel("Groq API anahtarı")
        self.groq_key_label.setObjectName("fieldLabel")
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        self.groq_key_input.setPlaceholderText("Groq Cloud API anahtarı")
        keys_grid.addWidget(self.groq_key_label, 2, 0)
        keys_grid.addWidget(self.groq_key_input, 2, 1)

        self.openai_key_label = QLabel("OpenAI API anahtarı")
        self.openai_key_label.setObjectName("fieldLabel")
        self.openai_key_input = QLineEdit()
        self.openai_key_input.setEchoMode(QLineEdit.Password)
        self.openai_key_input.setPlaceholderText("OpenAI Platform API anahtarı")
        keys_grid.addWidget(self.openai_key_label, 3, 0)
        keys_grid.addWidget(self.openai_key_input, 3, 1)
        keys_grid.setColumnStretch(1, 1)
        key_layout.addLayout(keys_grid)
        layout.addWidget(self.cloud_keys_widget)
        layout.addStretch()
        return widget

    def _update_ai_provider_fields(self, *_):
        provider = self.ai_provider_combo.currentData()
        enabled = self.ai_cleanup_cb.isChecked()
        is_cloud_ai = provider in {"gemini", "grok", "groq", "openai"}
        descriptions = {
            "rule_based": "Tamamen yerel çalışır. Dolgu seslerini temizler, ilk harfi büyütür ve temel noktalama ekler. Profil, özel talimat veya üretken AI modeli kullanmaz.",
            "custom_ollama": "STT metnini belirttiğiniz Ollama veya LM Studio sunucusundaki yerel modele gönderir. Düzenleme profilleri ve ek kurallar uygulanır.",
            "gemini": "STT metnini Google Gemini bulut modeline gönderir. Ses değil, yalnızca yazıya çevrilmiş metin bu aşamada işlenir.",
            "grok": "STT metnini xAI Grok bulut modeline gönderir. Ses değil, yalnızca yazıya çevrilmiş metin bu aşamada işlenir.",
            "groq": "STT metnini Groq üzerindeki LLM'e gönderir. Ses değil, yalnızca yazıya çevrilmiş metin bu aşamada işlenir.",
            "openai": "STT metnini OpenAI metin modeline gönderir. Ses değil, yalnızca yazıya çevrilmiş metin bu aşamada işlenir.",
        }
        self.ai_processing_settings.setVisible(enabled)
        self.ai_provider_description.setText(t(descriptions.get(provider, "")))
        self.custom_provider_widget.setVisible(enabled and provider == "custom_ollama")
        self.ai_model_widget.setVisible(enabled and is_cloud_ai)
        self.ai_prompt_widget.setVisible(enabled and provider != "rule_based")
        required_key_providers = set()
        if enabled and is_cloud_ai:
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
        h_actions.addStretch()

        g_layout.addLayout(h_actions)
        layout.addWidget(group)
        return widget

    def browse_audio_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            t("Ses/Video Dosyası Seç"),
            "",
            t("Ses ve Video Dosyaları (*.mp3 *.wav *.mp4 *.m4a *.mkv *.flac *.ogg)"),
        )
        if file_name:
            self.file_path_input.setText(file_name)

    def start_file_transcription(self):
        if self.app_controller and getattr(self.app_controller.state, "value", "idle") != "idle":
            QMessageBox.warning(self, t("İşlem devam ediyor"), t("Dosya transkripsiyonundan önce aktif dikte işlemini tamamlayın."))
            return
        file_path = self.file_path_input.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, t("Hata"), t("Lütfen geçerli bir ses/video dosyası seçin."))
            return

        self.transcribe_file_btn.setEnabled(False)
        self.cancel_transcribe_btn.setEnabled(True)
        self.dictate_btn.setEnabled(False)
        self.file_progress.setValue(10)
        self.file_result_edit.setText(t("Çeviri işlemi başlatılıyor..."))

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
            self.status_label.setText(t("İşlem iptal ediliyor"))

    def _on_file_progress(self, percent: int, msg: str):
        self.file_progress.setValue(percent)
        self.status_label.setText(f"{t('Dosya Çeviriliyor')}: {msg}")

    def _on_file_finished(self, file_path: str, text: str):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(100)
        self.file_result_edit.setText(text)
        self.status_label.setText(t("Dosya çevirisi tamamlandı!"))
        QMessageBox.information(self, t("Başarılı"), t("Dosya transkripsiyonu tamamlandı."))

    def _on_file_error(self, err: str):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        QMessageBox.critical(self, t("Hata"), f"{t('Dosya çevrilirken hata oluştu')}:\n{err}")

    def _on_file_cancelled(self):
        self.transcribe_file_btn.setEnabled(True)
        self.cancel_transcribe_btn.setEnabled(False)
        self.dictate_btn.setEnabled(True)
        self.file_progress.setValue(0)
        self.status_label.setText(t("Dosya transkripsiyonu iptal edildi"))

    def save_file_text(self):
        text = self.file_result_edit.toPlainText()
        if not text:
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self, t("Metni Kaydet"), "transcription.txt", t("Metin Dosyası (*.txt)")
        )
        if file_name:
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(text)
            QMessageBox.information(self, t("Kaydedildi"), f"{t('Metin kaydedildi')}: {file_name}")

    def _create_audio_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        language_group = QGroupBox("Uygulama Dili")
        language_layout = QVBoxLayout(language_group)
        language_row = QHBoxLayout()
        language_label = QLabel("Arayüz dili")
        language_label.setObjectName("fieldLabel")
        language_row.addWidget(language_label)
        self.ui_language_combo = QComboBox()
        self.ui_language_combo.addItem("Türkçe", "tr")
        self.ui_language_combo.addItem("English", "en")
        language_row.addWidget(self.ui_language_combo, 1)
        language_layout.addLayout(language_row)
        language_note = QLabel("Dil değişikliği ayarlar kaydedildiğinde uygulanır.")
        language_note.setObjectName("mutedLabel")
        language_layout.addWidget(language_note)
        layout.addWidget(language_group)

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
        self.log_console.setStyleSheet("background-color: #080c11; color: #76a8b4; font-family: 'Consolas', monospace; font-size: 11px;")
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
        msg = f"{t('Bulunan Mikrofon Sayısı')}: {len(devices)}\n\n"
        for d in devices:
            msg += f"• [{d['index']}] {d['name']} ({d['default_samplerate']}Hz, {d['channels']} ch)\n"
        QMessageBox.information(self, t("Mikrofon Tanı Bilgisi"), msg)

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
            self.model_status_label.setText(t("Model '{model}' hazır ve bilgisayarda yüklü.").format(model=model_name))
            self.model_status_label.setStyleSheet("color: #78d6ad; font-weight: 600;")
            self.model_progress.setValue(100)
            self.download_model_btn.setEnabled(False)
            self.download_model_btn.setText(t("Model hazır"))
        else:
            self.model_status_label.setText(t("Model '{model}' henüz bilgisayara indirilmedi.").format(model=model_name))
            self.model_status_label.setStyleSheet("color: #e2c173; font-weight: 600;")
            self.model_progress.setValue(0)
            self.download_model_btn.setEnabled(True)
            self.download_model_btn.setText(t("Seçilen Modeli İndir"))

    def download_selected_model(self):
        model_name = self.model_combo.currentText()
        backend = self.backend_combo.currentData()
        self.download_model_btn.setEnabled(False)
        self.download_model_btn.setText(t("İndiriliyor..."))
        model_manager.download_model_async(model_name, backend)

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
            QMessageBox.information(self, t("İndirme Tamamlandı"), t("Whisper '{model}' modeli başarıyla indirildi ve kullanıma hazır.").format(model=model_name))
            if backend == self.backend_combo.currentData():
                self.check_selected_model_status(model_name)
        else:
            QMessageBox.critical(self, t("İndirme Hatası"), f"{t('Model indirilirken hata oluştu')}:\n{error_msg}")
            if backend == self.backend_combo.currentData():
                self.check_selected_model_status(model_name)

    def refresh_mic_list(self):
        self.mic_combo.clear()
        self.mic_combo.addItem("Varsayılan Sistem Mikrofonu", None)
        devices = AudioRecorder.get_input_devices()
        for dev in devices:
            self.mic_combo.addItem(f"{dev['name']}", dev['index'])

    def load_settings_to_ui(self):
        ui_language = config_manager.get("ui_language", "tr")
        ui_language_index = self.ui_language_combo.findData(ui_language)
        self.ui_language_combo.setCurrentIndex(max(0, ui_language_index))

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
        self.lang_combo.setCurrentIndex(lang_idx if lang_idx >= 0 else self.lang_combo.findData("auto"))

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
        provider = self.ai_provider_combo.currentData()
        backend = self.backend_combo.currentData()
        cloud_provider = self.cloud_stt_combo.currentData()
        credentials = {
            "gemini": self.gemini_key_input.text().strip(),
            "grok": self.grok_key_input.text().strip(),
            "groq": self.groq_key_input.text().strip(),
            "openai": self.openai_key_input.text().strip(),
        }
        if backend != "cloud" and not model_manager.is_model_downloaded(self.model_combo.currentText(), backend):
            QMessageBox.warning(self, t("Kurulum tamamlanamadı"), t("Seçilen yerel Whisper modelini önce indirin."))
            self._set_page(1)
            return
        if backend == "cloud" and (not self.cloud_stt_model_combo.currentText().strip() or not credentials.get(cloud_provider)):
            QMessageBox.warning(self, t("Kurulum tamamlanamadı"), t("Bulut STT için model ve API anahtarı gereklidir."))
            return
        if backend != "cloud" and self.cloud_fallback_cb.isChecked() and (
            not credentials.get(cloud_provider) or not self.cloud_stt_model_combo.currentText().strip()
        ):
            QMessageBox.warning(self, t("Kurulum tamamlanamadı"), t("Bulut fallback için STT modeli ve sağlayıcı API anahtarı gereklidir."))
            return
        if self.ai_cleanup_cb.isChecked() and provider in credentials:
            if not credentials[provider] or not self.ai_model_combo.currentText().strip():
                QMessageBox.warning(self, t("Kurulum tamamlanamadı"), t("Bulut metin işleme için model ve API anahtarı gereklidir."))
                return
        if self.ai_cleanup_cb.isChecked() and provider == "custom_ollama":
            if not self.custom_url_input.text().strip() or not self.custom_model_input.text().strip():
                QMessageBox.warning(self, t("Kurulum tamamlanamadı"), t("Yerel LLM için API adresi ve model adı gereklidir."))
                return
        vulkan_executable = self.vulkan_executable_input.text().strip()
        if backend == "vulkan" and vulkan_executable and not os.path.isfile(vulkan_executable):
            QMessageBox.warning(self, t("Geçersiz Vulkan runtime"), t("Seçilen whisper-cli.exe dosyası bulunamadı."))
            return
        if backend == "vulkan":
            runtime_ok, runtime_message = VulkanSTTEngine.runtime_status(vulkan_executable or None)
            if not runtime_ok:
                QMessageBox.warning(self, t("Vulkan runtime kullanılamıyor"), runtime_message)
                return

        settings = {
            "ui_language": self.ui_language_combo.currentData(),
            "setup_completed": True,
            "stt_backend": backend,
            "model_size": self.model_combo.currentText(),
            "language": self.lang_combo.currentData() or "auto",
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
            QMessageBox.critical(self, t("Ayarlar kaydedilemedi"), str(exc))
            return

        set_language(settings["ui_language"])
        if self.app_controller:
            self.app_controller.reload_settings()

        self._apply_ui_language()
        self._refresh_dashboard()
        QMessageBox.information(self, t("Başarılı"), t("Ayarlar başarıyla kaydedildi."))

    def _refresh_dashboard(self):
        setup_completed = config_manager.get("setup_completed", False)
        self.dashboard_metrics_widget.setVisible(setup_completed)
        self.dashboard_onboarding.setVisible(not setup_completed)
        self.dictate_btn.setEnabled(setup_completed)
        if not setup_completed:
            self.hero_title.setText(t("Dikteye başlamadan önce kısa kurulumu tamamlayın."))
            self.hero_caption.setText(t("Doğru STT motorunu ve konuşma dilini seçerek güvenilir bir çalışma alanı oluşturun."))
            self.hero_state.setText(t("Henüz etkin yapılandırma yok"))
            return

        self.hero_title.setText(t("Konuşun. Gerisini PrimeDictate halletsin."))
        self.hero_caption.setText(t("Global kısayolunuzla herhangi bir uygulamada dikteye başlayın."))
        backend_labels = {
            "vulkan": "AMD / Vulkan",
            "cuda": "NVIDIA CUDA",
            "cpu": "Yerel CPU",
            "cloud": "Bulut STT",
        }
        backend = config_manager.get("stt_backend", "cpu")
        self.dashboard_engine.setText(t(backend_labels.get(backend, "Yerel CPU")))
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
        self.dashboard_privacy.setText(t(privacy))
        language = config_manager.get("language", "tr")
        language_text = t("Otomatik algıla") if language == "auto" else f"{self._language_name(language)} ({language})"
        self.dashboard_language.setText(language_text)

    def update_transcription_metadata(self, info: dict):
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
            QMessageBox.information(self, t("Kopyalandı"), t("Metin panoya kopyalandı."))

    def clear_history(self):
        answer = QMessageBox.question(
            self,
            t("Geçmişi temizle"),
            t("Tüm dikte geçmişi kalıcı olarak silinsin mi?"),
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
        localized_message = t(message)
        self.status_label.setText(f"●  {localized_message}")
        self.hero_state.setText(localized_message)
        setup_completed = config_manager.get("setup_completed", False)
        self.dictate_btn.setEnabled(setup_completed and state in {"idle", "recording"})
        self.dictate_btn.setObjectName("dangerAction" if state == "recording" else "primaryAction")
        self.dictate_btn.setText(t("Durdur" if state == "recording" else "Dikte Et"))
        self.dictate_btn.style().unpolish(self.dictate_btn)
        self.dictate_btn.style().polish(self.dictate_btn)

        colors = {
            "idle": ("#10231d", "#245441", "#78d6ad"),
            "recording": ("#2a171a", "#71343b", "#f08d96"),
            "transcribing": ("#282215", "#6b582b", "#e2c173"),
            "success": ("#10231d", "#245441", "#78d6ad"),
            "error": ("#2a171a", "#71343b", "#f08d96"),
        }
        bg, border, color = colors.get(state, colors["idle"])
        self.status_label.setStyleSheet(
            f"background-color:{bg}; border:1px solid {border}; border-radius:9px;"
            f"color:{color}; font-weight:600; padding:0 14px;"
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
