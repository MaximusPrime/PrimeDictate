import time
import threading
import logging
import pyperclip
import keyboard
from src.config import config_manager

logger = logging.getLogger("PrimeDictate.PasteInjector")

class PasteInjector:
    @staticmethod
    def paste_text(text: str, restore_clipboard: bool = False):
        if not text or not text.strip():
            return

        text = text.strip()

        try:
            # Backup previous clipboard content if required
            previous_clip = None
            if restore_clipboard:
                try:
                    previous_clip = pyperclip.paste()
                except Exception:
                    previous_clip = None

            # Set new transcribed text to clipboard
            pyperclip.copy(text)
            logger.info(f"Copied text to clipboard: '{text}'")

            # Auto paste into active focused window if enabled
            auto_paste = config_manager.get("auto_paste", True)
            if auto_paste:
                time.sleep(0.05)  # slight delay for clipboard sync
                keyboard.send("ctrl+v")
                logger.info("Sent Ctrl+V key combination to active window.")

            # Restore original clipboard asynchronously if enabled
            if restore_clipboard and previous_clip is not None:
                def restore():
                    time.sleep(0.5)
                    try:
                        pyperclip.copy(previous_clip)
                    except Exception:
                        pass
                threading.Thread(target=restore, daemon=True).start()

        except Exception as e:
            logger.error(f"Error injecting text via clipboard: {e}")

paste_injector = PasteInjector()
