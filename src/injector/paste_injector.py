import time
import threading
import logging
import os
import win32gui
import win32process
import win32api
import win32con
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

    @staticmethod
    def capture_target_window():
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and win32gui.IsWindow(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == os.getpid():
                    return None
                return hwnd
        except Exception:
            pass
        return None

    @staticmethod
    def _force_foreground(hwnd):
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            # ALT-key tap trick unlocks Windows SetForegroundWindow restriction
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_EXTENDEDKEY, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_EXTENDEDKEY | win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            return True
        except Exception as e:
            logger.warning(f"Could not restore focus to target window {hwnd}: {e}")
            return False

    @staticmethod
    def _send_paste_keys():
        try:
            # Native Windows keybd_event for Ctrl+V
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            logger.warning(f"Native keybd_event failed: {e}")
            try:
                keyboard.send("ctrl+v")
                return True
            except Exception:
                return False

    def paste_text(self, text: str, restore_clipboard: bool = False, target_hwnd=None) -> bool:
        if not text or not text.strip():
            return False

        text = text.strip()
        win_title, pid = self._get_active_window_info()
        logger.info("Injecting %d characters into window '%s' (PID %s).", len(text), win_title, pid)

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
                return False

            auto_paste = config_manager.get("auto_paste", True)
            pasted = False

            if auto_paste:
                # Restore focus to target window if specified
                if target_hwnd and win32gui.IsWindow(target_hwnd):
                    self._force_foreground(target_hwnd)
                    time.sleep(0.08)

                current_hwnd = win32gui.GetForegroundWindow()
                current_title, current_pid = self._get_active_window_info()

                is_safe_target = False
                if target_hwnd:
                    if current_hwnd == target_hwnd:
                        is_safe_target = True
                    else:
                        try:
                            root_curr = win32gui.GetAncestor(current_hwnd, win32con.GA_ROOT) if current_hwnd else 0
                            root_target = win32gui.GetAncestor(target_hwnd, win32con.GA_ROOT) if target_hwnd else 0
                            if (root_curr and root_curr == target_hwnd) or (root_target and root_target == current_hwnd) or (root_curr and root_target and root_curr == root_target):
                                is_safe_target = True
                            else:
                                logger.warning("Paste was skipped because target window focus could not be safely verified.")
                        except Exception:
                            logger.warning("Paste was skipped because target window focus could not be safely verified.")
                else:
                    if current_pid != 0 and current_pid != os.getpid():
                        is_safe_target = True
                    else:
                        logger.warning("Auto-paste skipped because current focused window is PrimeDictate itself.")

                if is_safe_target:
                    time.sleep(0.05)
                    pasted = self._send_paste_keys()
                    logger.info("Sent Ctrl+V key combination into '%s'.", current_title)

            # Restore original clipboard asynchronously if requested
            if pasted and restore_clipboard and previous_clip is not None:
                def restore():
                    time.sleep(0.6)
                    self._safe_copy_to_clipboard(previous_clip)
                threading.Thread(target=restore, daemon=True).start()

            return pasted

        except Exception as e:
            logger.error(f"Error in PasteInjector: {e}")
            return False

paste_injector = PasteInjector()
