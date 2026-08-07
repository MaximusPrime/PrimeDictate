import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from src.i18n import set_language, t
from src.ui.floating_overlay import FloatingOverlay
from src.ui.main_window import MainWindow


class UIStructureTests(unittest.TestCase):
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

    def test_ui_supports_english_and_full_whisper_language_list(self):
        window = MainWindow()
        set_language("en")
        window._apply_ui_language()
        self.assertEqual(window.nav_buttons[0].text(), "Home")
        self.assertEqual(window.lang_combo.count(), 101)
        self.assertGreaterEqual(window.lang_combo.findData("de"), 0)
        self.assertGreaterEqual(window.lang_combo.findData("yue"), 0)
        self.assertEqual(window.lang_combo.itemText(window.lang_combo.findData("tr")), "Turkish (tr)")
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
        self.assertEqual(t("Ayarları Kaydet"), "Save Settings")
        set_language("tr")
        self.assertEqual(t("Save Settings"), "Ayarları Kaydet")

    def test_overlay_restores_position_inside_available_screen(self):
        with patch("src.ui.floating_overlay.config_manager.get", return_value={"x": 999999, "y": 999999}):
            overlay = FloatingOverlay()
        screen_geometry = overlay._target_screen(QPoint(0, 0)).availableGeometry()
        self.assertTrue(screen_geometry.adjusted(0, 0, -overlay.width(), -overlay.height()).contains(overlay.pos()))
        self.assertEqual(overlay.size().width(), 438)
        self.assertEqual(overlay.size().height(), 74)
        overlay.close()

    def test_overlay_stop_button_uses_controller_callback(self):
        callback = Mock()
        overlay = FloatingOverlay(stop_callback=callback)
        overlay.set_recording_active(True)
        overlay.stop_button.click()
        callback.assert_called_once_with()
        self.assertFalse(overlay.stop_button.isEnabled())
        overlay.close()

    def test_studio_logo_is_declared_in_all_build_paths(self):
        root = Path(__file__).resolve().parents[1]
        asset = root / "assets" / "maximus-prime-software.png"
        self.assertTrue(asset.is_file())
        for manifest in ("PrimeDictate.spec", "PrimeDictate-Portable.spec", "build.py"):
            contents = (root / manifest).read_text(encoding="utf-8")
            self.assertIn("maximus-prime-software.png", contents)
            self.assertIn("PrimeDictate-AppIcon.png", contents)


if __name__ == "__main__":
    unittest.main()
