import ast
import os
from pathlib import Path
import threading
import time
import unittest
import string
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPoint, QThread, Slot
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from src.i18n import EN, MESSAGES, set_language, translate
from src.ui.floating_overlay import FloatingOverlay
from src.ui.main_window import MainWindow
from src.ui.tray_icon import SystemTrayManager
from run import AppSignals, PrimeDictateApp


class UIStructureTests(unittest.TestCase):
    def test_quit_hides_all_surfaces_and_quits_even_if_worker_is_slow(self):
        controller = PrimeDictateApp.__new__(PrimeDictateApp)
        controller._quitting = False
        controller._shutdown_requested = threading.Event()
        controller.overlay = Mock()
        controller.tray = Mock()
        controller.hotkey_listener = Mock()
        controller.recorder = Mock(is_recording=False)
        controller.main_window = Mock()
        controller.main_window.prepare_shutdown.return_value = False
        controller._processing_thread = None
        controller.operation_coordinator = Mock()
        controller.instance_lock = Mock()
        controller.app = Mock()

        controller.quit()

        controller.overlay.hide.assert_called_once_with()
        controller.tray.shutdown.assert_called_once_with()
        controller.hotkey_listener.stop_listening.assert_called_once_with()
        controller.main_window.hide.assert_called_once_with()
        controller.app.quit.assert_called_once_with()

    def test_worker_completion_signal_is_queued_to_gui_thread(self):
        app = QApplication.instance() or QApplication([])
        delivered = threading.Event()
        receiver_threads = []

        class TestController(PrimeDictateApp):
            @Slot(str)
            def receive(self, _text):
                receiver_threads.append(QThread.currentThread())
                delivered.set()

        controller = TestController.__new__(TestController)
        QObject.__init__(controller)
        signals = AppSignals(controller)
        signals.transcription_complete.connect(controller.receive)

        worker = threading.Thread(target=lambda: signals.transcription_complete.emit("ready"))
        worker.start()
        worker.join(timeout=2)
        deadline = time.monotonic() + 2
        while not delivered.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        self.assertTrue(delivered.is_set())
        self.assertIs(receiver_threads[0], app.thread())

    def test_checkbox_style_does_not_draw_outer_focus_border(self):
        style_source = (Path(__file__).resolve().parents[1] / "src" / "ui" / "styles.py").read_text(encoding="utf-8")
        self.assertIn("QCheckBox {{ spacing: 9px; color: #c8cfd7; outline: none; border: none; }}", style_source)
        self.assertNotIn("QCheckBox:focus::indicator", style_source)

    def test_stable_translation_keys_have_both_languages(self):
        self.assertTrue(MESSAGES)
        for key, translations in MESSAGES.items():
            with self.subTest(key=key):
                self.assertEqual(set(translations), {"tr", "en"})
                self.assertTrue(translations["tr"].strip())
                self.assertTrue(translations["en"].strip())

    def test_stable_translation_placeholders_match_between_languages(self):
        formatter = string.Formatter()
        for key, translations in MESSAGES.items():
            with self.subTest(key=key):
                tr_fields = {name for _, name, _, _ in formatter.parse(translations["tr"]) if name}
                en_fields = {name for _, name, _, _ in formatter.parse(translations["en"]) if name}
                self.assertEqual(tr_fields, en_fields)

    def test_legacy_translation_calls_are_confined_to_compatibility_bridge(self):
        source_root = Path(__file__).resolve().parents[1] / "src"
        calls = []
        for source_path in source_root.rglob("*.py"):
            if source_path.name == "i18n.py":
                continue
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
                    calls.append((source_path.relative_to(source_root).as_posix(), node.lineno))
        self.assertEqual(calls, [])

    def test_stable_translation_keys_are_strict_and_language_aware(self):
        set_language("tr")
        self.assertEqual(translate("privacy.local"), "Yerel")
        set_language("en")
        self.assertEqual(translate("privacy.local"), "Local")
        with self.assertRaises(KeyError):
            translate("missing.key")

    def test_all_literal_translation_calls_are_in_the_language_catalog(self):
        source_root = Path(__file__).resolve().parents[1] / "src"
        catalog_strings = set(EN) | set(EN.values())
        missing = set()
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "t":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    text = node.args[0].value
                    if text and text not in catalog_strings:
                        missing.add(text)
        self.assertEqual(sorted(missing), [], f"Missing i18n catalog entries: {sorted(missing)!r}")

    def test_all_literal_stable_translation_calls_are_in_the_message_catalog(self):
        source_root = Path(__file__).resolve().parents[1] / "src"
        missing = set()
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "translate":
                    continue
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    key = node.args[0].value
                    if key not in MESSAGES:
                        missing.add(key)
        self.assertEqual(sorted(missing), [], f"Missing stable i18n keys: {sorted(missing)!r}")

    def test_literal_widget_text_is_covered_by_the_language_catalog(self):
        source_root = Path(__file__).resolve().parents[1] / "src" / "ui"
        catalog_strings = set(EN) | set(EN.values())
        constructors = {"QLabel", "QPushButton", "QCheckBox", "QGroupBox"}
        methods = {"setText", "setPlaceholderText", "setToolTip", "setTitle", "addItem"}
        technical_literals = {
            "", "PD", "PrimeDictate", "PRIVATE DICTATION", "CTRL + ALT + D", "→", "⋮⋮",
            "English", "Türkçe", "🌐 English", "🌐 Türkçe",
            "http://localhost:11434/v1", "llama3.2",
            "Groq Whisper", "OpenAI Transcribe", "Google Gemini Audio",
        }
        missing = set()
        for source_path in source_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                is_constructor = isinstance(node.func, ast.Name) and node.func.id in constructors
                is_method = isinstance(node.func, ast.Attribute) and node.func.attr in methods
                if not (is_constructor or is_method):
                    continue
                argument = node.args[0]
                if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                    continue
                text = argument.value
                if text not in technical_literals and text not in catalog_strings:
                    missing.add(text)
        self.assertEqual(sorted(missing), [], f"Uncatalogued widget text: {sorted(missing)!r}")

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        set_language("tr")

    def test_page_metadata_drives_navigation_and_content(self):
        window = MainWindow()
        self.assertEqual(len(window.PAGE_DEFINITIONS), window.pages.count())
        self.assertEqual(len(window.PAGE_DEFINITIONS), len(window.nav_buttons))
        self.assertEqual(len({item[3] for item in window.PAGE_DEFINITIONS}), len(window.PAGE_DEFINITIONS))
        for title_key, tooltip_key, subtitle_key, _ in window.PAGE_DEFINITIONS:
            self.assertIn(title_key, MESSAGES)
            self.assertIn(tooltip_key, MESSAGES)
            self.assertIn(subtitle_key, MESSAGES)
        window.close()

    def test_keyboard_navigation_and_accessible_names_are_declared(self):
        window = MainWindow()
        shortcuts = {shortcut.key().toString() for shortcut in window.findChildren(QShortcut)}
        self.assertTrue({"Ctrl+1", "Ctrl+8", "Ctrl+S", "Ctrl+F", "Esc"}.issubset(shortcuts))
        self.assertTrue(window.dictate_btn.accessibleName())
        self.assertTrue(window.status_label.accessibleName())
        self.assertTrue(all(button.accessibleName() for button in window.nav_buttons))
        window.close()

    def test_sidebar_uses_compact_width_on_narrow_window(self):
        window = MainWindow()
        window.resize(1000, 700)
        window._update_responsive_layout()
        self.assertEqual(window.sidebar_widget.width(), 210)
        window.resize(1200, 700)
        window._update_responsive_layout()
        self.assertEqual(window.sidebar_widget.width(), window._preferred_sidebar_width)
        window.close()

    def test_tray_menu_is_state_aware_and_fully_retranslated(self):
        window = MainWindow()
        window.show_page = Mock()
        toggle = Mock()
        tray = SystemTrayManager(window, toggle_callback=toggle)

        set_language("tr")
        tray.retranslate()
        self.assertEqual(tray.show_action.text(), "Kontrol Panelini Aç")
        self.assertEqual(tray.settings_action.text(), "Ayarlar")
        self.assertEqual(tray.history_action.text(), "Geçmiş")
        self.assertEqual(tray.exit_action.text(), "PrimeDictate'ten Çık")

        tray.set_dictation_state("recording")
        self.assertEqual(tray.toggle_action.text(), "Dikteyi Durdur")
        self.assertTrue(tray.toggle_action.isEnabled())
        tray.set_dictation_state("transcribing")
        self.assertEqual(tray.toggle_action.text(), "Dikte işleniyor…")
        self.assertFalse(tray.toggle_action.isEnabled())
        tray.set_dictation_state("idle", enabled=False)
        self.assertEqual(tray.toggle_action.text(), "Dikteyi Başlat")
        self.assertFalse(tray.toggle_action.isEnabled())

        set_language("en")
        tray.retranslate()
        self.assertEqual(tray.show_action.text(), "Open Dashboard")
        self.assertEqual(tray.settings_action.text(), "Settings")
        self.assertEqual(tray.history_action.text(), "History")
        self.assertEqual(tray.exit_action.text(), "Exit PrimeDictate")

        tray.settings_action.trigger()
        window.show_page.assert_called_once_with(4)
        tray.shutdown()
        window.close()

    def test_cloud_backend_hides_local_model_controls(self):
        window = MainWindow()
        window.backend_combo.setCurrentIndex(window.backend_combo.findData("cloud"))
        self.app.processEvents()
        self.assertTrue(window.local_stt_widget.isHidden())
        self.assertTrue(window.model_group.isHidden())
        self.assertFalse(window.cloud_stt_widget.isHidden())
        window.close()

    def test_dashboard_hides_runtime_metrics_before_setup(self):
        window = MainWindow()
        original_get = window.__class__.__module__ + ".config_manager.get"
        with patch(original_get, side_effect=lambda key, default=None: False if key == "setup_completed" else default):
            window._refresh_dashboard()
        self.assertFalse(window.dashboard_onboarding.isHidden())
        self.assertTrue(window.dashboard_metrics_widget.isHidden())
        self.assertFalse(window.dictate_btn.isEnabled())
        window.close()

    def test_guided_setup_moves_between_required_pages(self):
        window = MainWindow()
        with patch("src.ui.main_window.config_manager.get", side_effect=lambda key, default=None: False if key == "setup_completed" else default):
            window._start_setup_flow()
            self.assertEqual(window.pages.currentIndex(), 1)
            self.assertFalse(window.setup_engine_step.isHidden())
            window._set_page(4)
            self.assertEqual(window.pages.currentIndex(), 4)
            self.assertFalse(window.setup_audio_step.isHidden())
            self.assertTrue(window.setup_engine_step.isHidden())
        window.close()

    def test_history_empty_and_filtered_states_update_actions(self):
        window = MainWindow()
        with patch("src.ui.main_window.config_manager.load_history", return_value=[]):
            window.refresh_history_list()
        self.assertFalse(window.history_empty_label.isHidden())
        self.assertTrue(window.history_list.isHidden())
        self.assertFalse(window.history_copy_btn.isEnabled())

        history = [{"time": "2026-08-08 10:00:00", "text": "örnek dikte"}]
        with patch("src.ui.main_window.config_manager.load_history", return_value=history):
            window.history_search.setText("örnek")
        self.assertEqual(window.history_list.count(), 1)
        self.assertFalse(window.history_list.isHidden())
        window.history_list.setCurrentRow(0)
        self.assertTrue(window.history_copy_btn.isEnabled())
        self.assertTrue(window.history_delete_btn.isEnabled())
        window.close()

    def test_ui_supports_english_and_full_whisper_language_list(self):
        window = MainWindow()
        set_language("en")
        window._apply_ui_language()
        self.assertEqual(window.nav_buttons[0].text(), "Home")
        metric_labels = {label.text() for label in window.dashboard_metrics_widget.findChildren(type(window.page_title)) if label.objectName() == "metricLabel"}
        self.assertEqual(metric_labels, {"ACTIVE ENGINE", "MODEL", "SPOKEN LANGUAGE", "PRIVACY"})
        self.assertEqual(window.lang_combo.count(), 101)
        self.assertGreaterEqual(window.lang_combo.findData("de"), 0)
        self.assertGreaterEqual(window.lang_combo.findData("yue"), 0)
        self.assertEqual(window.lang_combo.itemText(window.lang_combo.findData("tr")), "Turkish (tr)")
        window.close()

    def test_repeated_language_switch_preserves_each_widget_source(self):
        window = MainWindow()
        hold_index = window.hotkey_mode_combo.findData("hold")
        toggle_index = window.hotkey_mode_combo.findData("toggle")
        set_language("en")
        window._apply_ui_language()
        self.assertEqual(window.save_btn.text(), "Save Settings")
        set_language("tr")
        window._apply_ui_language()
        self.assertEqual(window.save_btn.text(), "Ayarları Kaydet")
        self.assertTrue(window.hotkey_mode_combo.itemText(hold_index).startswith("Bas-Konuş"))
        self.assertTrue(window.hotkey_mode_combo.itemText(toggle_index).startswith("Aç / Kapat"))
        set_language("en")
        window._apply_ui_language()
        set_language("tr")
        window._apply_ui_language()
        self.assertEqual(window.save_btn.text(), "Ayarları Kaydet")
        self.assertTrue(window.hotkey_mode_combo.itemText(hold_index).startswith("Bas-Konuş"))
        window.close()

    def test_turkish_interface_localizes_language_names(self):
        window = MainWindow()
        set_language("tr")
        window._apply_ui_language()
        self.assertEqual(window.lang_combo.itemText(window.lang_combo.findData("tr")), "Türkçe (tr)")
        self.assertEqual(window.lang_combo.itemText(window.lang_combo.findData("de")), "Almanca (de)")
        window.close()

    def test_setup_cannot_complete_without_local_model(self):
        window = MainWindow()
        window.backend_combo.setCurrentIndex(window.backend_combo.findData("cpu"))
        with patch("src.ui.main_window.model_manager.is_model_downloaded", return_value=False), \
             patch("src.ui.main_window.QMessageBox.warning") as warning, \
             patch("src.ui.main_window.config_manager.update") as update:
            window.save_ui_settings()

        warning.assert_called_once()
        update.assert_not_called()
        window.close()

    def test_language_catalog_round_trip(self):
        set_language("en")
        self.assertEqual(translate("action.save_settings"), "Save Settings")
        set_language("tr")
        self.assertEqual(translate("action.save_settings"), "Ayarları Kaydet")

    def test_main_window_services_can_be_injected(self):
        models = Mock()
        models.progress.connect = Mock()
        models.download_finished.connect = Mock()
        providers = Mock()
        with patch.object(MainWindow, "_start_hardware_detection"):
            window = MainWindow(models=models, providers=providers)
        self.assertIs(window.model_manager, models)
        self.assertIs(window.provider_catalog, providers)
        window.close()

    def test_shutdown_requests_file_worker_interruption_and_waits(self):
        window = MainWindow()
        worker = Mock()
        worker.isRunning.return_value = True
        worker.wait.return_value = True
        window.transcribe_worker = worker

        self.assertTrue(window.prepare_shutdown(timeout_ms=25))

        worker.requestInterruption.assert_called_once_with()
        worker.wait.assert_called_once_with(25)
        worker.deleteLater.assert_called_once_with()
        self.assertIsNone(window.transcribe_worker)
        window.close()

    def test_overlay_restores_position_inside_available_screen(self):
        with patch("src.ui.floating_overlay.config_manager.get", return_value={"x": 999999, "y": 999999}):
            overlay = FloatingOverlay()
        screen_geometry = overlay._target_screen(QPoint(0, 0)).availableGeometry()
        self.assertTrue(screen_geometry.adjusted(0, 0, -overlay.width(), -overlay.height()).contains(overlay.pos()))
        self.assertEqual(overlay.size().width(), 186)
        self.assertEqual(overlay.size().height(), 46)
        overlay.close()

    def test_overlay_stop_button_uses_controller_callback(self):
        callback = Mock()
        overlay = FloatingOverlay(stop_callback=callback)
        overlay.set_recording_active(True)
        overlay.stop_button.click()
        callback.assert_called_once_with()
        self.assertFalse(overlay.stop_button.isEnabled())
        overlay.close()

    def test_overlay_play_button_stays_enabled_when_start_is_rejected(self):
        callback = Mock()
        overlay = FloatingOverlay(start_callback=callback)

        overlay.play_button.click()

        callback.assert_called_once_with()
        self.assertTrue(overlay.play_button.isEnabled())
        overlay.close()

    def test_successful_dictation_releases_state_before_history_refresh(self):
        controller = PrimeDictateApp.__new__(PrimeDictateApp)
        controller._shutdown_requested = threading.Event()
        controller.target_window = None
        controller.main_window = Mock()
        controller.main_window.add_history_entry.side_effect = RuntimeError("render failed")
        controller.engine_manager = Mock(last_transcription_info={})
        controller.overlay = Mock()
        controller._finish_dictation_operation = Mock()
        controller._set_state = Mock()

        with patch("run.paste_injector.paste_text", return_value=False), \
             patch("run.config_manager.get", side_effect=lambda key, default=None: default):
            controller._on_transcription_complete("örnek")

        controller._finish_dictation_operation.assert_called_once_with()
        controller._set_state.assert_called_once()
        self.assertEqual(controller._set_state.call_args.args[0].value, "success")

    def test_studio_logo_is_declared_in_all_build_paths(self):
        root = Path(__file__).resolve().parents[1]
        asset = root / "assets" / "maximus-prime-software.png"
        self.assertTrue(asset.is_file())
        for manifest in ("PrimeDictate.spec", "PrimeDictate-Portable.spec", "build.py"):
            contents = (root / manifest).read_text(encoding="utf-8")
            self.assertIn("maximus-prime-software.png", contents)
            self.assertIn("PrimeDictate-AppIcon.png", contents)

    def test_ui_font_size_options_excludes_small_90(self):
        window = MainWindow()
        combo = window.ui_font_size_combo
        self.assertEqual(combo.count(), 2)
        self.assertEqual(combo.itemData(0), "normal")
        self.assertEqual(combo.itemData(1), "large")
        self.assertEqual(combo.findData("small"), -1)
        window.close()

    def test_hotkey_recorder_widget_records_key_combination(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from src.ui.main_window import HotkeyRecorderWidget

        recorder = HotkeyRecorderWidget()
        recorder._start_recording()

        # Simulate Ctrl + Alt + D
        press_ctrl = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Control, Qt.ControlModifier)
        recorder.keyPressEvent(press_ctrl)
        self.assertTrue(recorder._recording)

        press_alt = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Alt, Qt.ControlModifier | Qt.AltModifier)
        recorder.keyPressEvent(press_alt)
        self.assertTrue(recorder._recording)

        press_d = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_D, Qt.ControlModifier | Qt.AltModifier)
        recorder.keyPressEvent(press_d)
        self.assertFalse(recorder._recording)
        self.assertEqual(recorder.get_hotkey(), "ctrl+alt+d")

    def test_hotkey_recorder_rejects_unmodified_typing_key(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from src.ui.main_window import HotkeyRecorderWidget

        recorder = HotkeyRecorderWidget()
        changed = []
        recorder.hotkey_changed.connect(changed.append)
        recorder._start_recording()
        recorder.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_D, Qt.NoModifier))

        self.assertTrue(recorder._recording)
        self.assertEqual(recorder.get_hotkey(), "ctrl+alt+d")
        self.assertEqual(changed, [])
        self.assertIn("değiştirici", recorder.text().casefold())
        recorder._stop_recording()

    def test_hotkey_capture_does_not_reload_old_config_after_change(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent

        window = MainWindow()
        listener = Mock()
        listener.update_hotkey.return_value = True
        controller = Mock()
        controller.state.value = "idle"
        controller.hotkey_listener = listener
        window.app_controller = controller

        recorder = window.hotkey_recorder
        recorder._start_recording()
        listener.stop_listening.assert_called_once_with()
        recorder.keyPressEvent(
            QKeyEvent(QKeyEvent.KeyPress, Qt.Key_K, Qt.ControlModifier | Qt.ShiftModifier)
        )

        listener.update_hotkey.assert_called_once_with("ctrl+shift+k", window.hotkey_mode_combo.currentData())
        listener.start_listening.assert_not_called()
        self.assertEqual(recorder.get_hotkey(), "ctrl+shift+k")
        window.close()


if __name__ == "__main__":
    unittest.main()
