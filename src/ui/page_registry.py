"""Declarative navigation metadata for the main application shell."""

PAGE_DEFINITIONS = (
    ("nav.home", "nav.home.tooltip", "page.home.subtitle", "_create_dashboard_page"),
    ("nav.speech_to_text", "nav.speech_to_text.tooltip", "page.speech_to_text.subtitle", "_create_general_tab"),
    ("nav.text_processing", "nav.text_processing.tooltip", "page.text_processing.subtitle", "_create_ai_tab"),
    ("nav.file_transcription", "nav.file_transcription.tooltip", "page.file_transcription.subtitle", "_create_file_transcribe_tab"),
    ("nav.settings", "nav.settings.tooltip", "page.settings.subtitle", "_create_audio_tab"),
    ("nav.history", "nav.history.tooltip", "page.history.subtitle", "_create_history_tab"),
    ("nav.diagnostics", "nav.diagnostics.tooltip", "page.diagnostics.subtitle", "_create_dev_tab"),
    ("nav.about", "nav.about.tooltip", "page.about.subtitle", "_create_about_page"),
)
