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

class MainWindowPagesMixin:
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
        duration_row.addWidget(self.max_recording_combo, 1)
        a_layout.addLayout(duration_row)

        layout.addWidget(audio_group)

        behavior_group = QGroupBox("Davranış ve Otomasyon")
        b_layout = QVBoxLayout(behavior_group)
        b_layout.setSpacing(10)

        self.auto_paste_cb = QCheckBox("Metni aktif pencereye otomatik yapıştır")
        self.restore_clip_cb = QCheckBox("Yapıştırmadan sonra önceki pano metnini geri yükle")
        self.restore_clip_cb.setToolTip(translate("settings.restore_clipboard.tooltip"))
        self._bind_translation(
            self.restore_clip_cb,
            "tooltip",
            "settings.restore_clipboard.tooltip",
            self.restore_clip_cb.setToolTip,
        )
        self.history_enabled_cb = QCheckBox("Dikte geçmişini bu cihazda sakla")
        self.play_sound_cb = QCheckBox("Kayıt başlangıç ve bitiş seslerini çal")
        self.overlay_cb = QCheckBox("Yüzen ses dalgası göstergesini kullan")
        self.overlay_always_on_cb = QCheckBox("Yüzen dikte kutusunu her zaman göster (Sürekli görünür)")
        self.start_windows_cb = QCheckBox("Windows ile otomatik başlat")
        self.admin_mode_cb = QCheckBox(translate("settings.run_as_admin"))
        self._bind_translation(
            self.admin_mode_cb,
            "text",
            "settings.run_as_admin",
            self.admin_mode_cb.setText,
        )
        self.admin_mode_status = QLabel()
        self.admin_mode_status.setObjectName("mutedLabel")
        self.admin_mode_status.setWordWrap(True)
        self.admin_mode_cb.toggled.connect(self._update_admin_mode_status)
        self.start_windows_cb.toggled.connect(self._update_admin_mode_status)

        b_layout.addWidget(self.auto_paste_cb)
        b_layout.addWidget(self.restore_clip_cb)
        b_layout.addWidget(self.history_enabled_cb)
        b_layout.addWidget(self.play_sound_cb)
        b_layout.addWidget(self.overlay_cb)
        b_layout.addWidget(self.overlay_always_on_cb)
        b_layout.addWidget(self.start_windows_cb)
        b_layout.addWidget(self.admin_mode_cb)
        b_layout.addWidget(self.admin_mode_status)

        layout.addWidget(behavior_group)
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
