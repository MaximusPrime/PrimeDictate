import time
import threading
import logging
import win32gui
import win32process
import pyperclip
import keyboard
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.PasteInjector")

class PasteInjector:
    @staticmethod
    def _safe_copy_to_clipboard(text: str, max_retries: int = 5) -> bool:
        for attempt in range(max_retries):
            try:
                pyperclip.copy(text)
                return True
            except Exception as e:
                logger.warning(f"Clipboard copy attempt {attempt+1} failed: {e}")
                time.sleep(0.05)
        return False

    @staticmethod
    def _get_active_window_info():
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return title, pid
        except Exception:
            return "Bilinmeyen Pencere", 0

    def paste_text(self, text: str, restore_clipboard: bool = False):
        if not text or not text.strip():
            return

        text = text.strip()
        win_title, pid = self._get_active_window_info()
        logger.info(f"Injecting text into active window '{win_title}' (PID {pid}): '{text}'")

        try:
            # Backup previous clipboard
            previous_clip = None
            if restore_clipboard:
                try:
                    previous_clip = pyperclip.paste()
                except Exception:
                    previous_clip = None

            # Copy new text safely to clipboard
            success = self._safe_copy_to_clipboard(text)
            if not success:
                logger.error("Failed to copy transcribed text to clipboard after retries.")
                return

            # Trigger paste into focused app
            auto_paste = config_manager.get("auto_paste", True)
            if auto_paste:
                time.sleep(0.08)  # slight delay for Windows focus & clipboard sync
                keyboard.send("ctrl+v")
                logger.info("Sent Ctrl+V key combination.")

            # Restore original clipboard asynchronously if requested
            if restore_clipboard and previous_clip is not None:
                def restore():
                    time.sleep(0.6)
                    self._safe_copy_to_clipboard(previous_clip)
                threading.Thread(target=restore, daemon=True).start()

        except Exception as e:
            logger.error(f"Error in PasteInjector: {e}")

paste_injector = PasteInjector()
