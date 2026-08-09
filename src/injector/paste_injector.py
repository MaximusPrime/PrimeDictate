import time
import threading
import logging
import os
import ctypes
from ctypes import wintypes
import win32gui
import win32process
import win32api
import win32con
import win32security
import pyperclip
import keyboard
from src.config import config_manager
from src.elevation import is_running_as_administrator

logger = logging.getLogger("PrimeDictate.PasteInjector")

class PasteInjector:
    class _GUITHREADINFO(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        )

    @classmethod
    def _focused_control_for_window(cls, hwnd):
        try:
            thread_id, _ = win32process.GetWindowThreadProcessId(hwnd)
            info = cls._GUITHREADINFO()
            info.cbSize = ctypes.sizeof(info)
            if ctypes.windll.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
                focused = int(info.hwndFocus or 0)
                if focused and win32gui.IsWindow(focused):
                    root = win32gui.GetAncestor(focused, win32con.GA_ROOT)
                    if root == hwnd:
                        return focused
        except Exception:
            pass
        return None

    @staticmethod
    def _restore_child_focus(hwnd) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        target_thread = None
        current_thread = None
        attached = False
        try:
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
            current_thread = win32api.GetCurrentThreadId()
            if target_thread != current_thread:
                attached = bool(win32process.AttachThreadInput(current_thread, target_thread, True))
            win32gui.SetFocus(hwnd)
            return True
        except Exception:
            return False
        finally:
            if attached:
                try:
                    win32process.AttachThreadInput(current_thread, target_thread, False)
                except Exception:
                    pass

    @staticmethod
    def _is_process_elevated(pid: int) -> bool | None:
        process = None
        token = None
        try:
            process = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
            return bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
        except Exception:
            return None
        finally:
            if token is not None:
                token.Close()
            if process is not None:
                process.Close()

    @staticmethod
    def _clipboard_sequence() -> int | None:
        try:
            return int(ctypes.windll.user32.GetClipboardSequenceNumber())
        except Exception:
            return None

    @staticmethod
    def _capture_clipboard_snapshot():
        """Capture every Qt MIME format when a GUI clipboard is available."""
        try:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                source = app.clipboard().mimeData()
                formats = {
                    mime_type: bytes(source.data(mime_type))
                    for mime_type in source.formats()
                }
                return "qt", formats
        except Exception:
            pass
        try:
            return "text", pyperclip.paste()
        except Exception:
            return None

    @staticmethod
    def _restore_clipboard_snapshot(snapshot) -> bool:
        if not snapshot:
            return False
        kind, value = snapshot
        if kind == "qt":
            try:
                from PySide6.QtCore import QByteArray, QMimeData
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app is not None:
                    restored = QMimeData()
                    for mime_type, data in value.items():
                        restored.setData(mime_type, QByteArray(data))
                    # QClipboard takes ownership of this newly-created object;
                    # the snapshot retains only immutable Python bytes.
                    app.clipboard().setMimeData(restored)
                    return True
            except Exception:
                return False
        if kind == "text":
            return PasteInjector._safe_copy_to_clipboard(value)
        return False

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
    def capture_target_window():
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and win32gui.IsWindow(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == os.getpid():
                    return None
                # Keep the owning PID alongside the handle. Windows may reuse
                # an HWND after a long transcription if the original closes.
                return hwnd, pid, PasteInjector._focused_control_for_window(hwnd)
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
        target_pid = None
        target_control = None
        if isinstance(target_hwnd, tuple) and len(target_hwnd) in {2, 3}:
            target_hwnd, target_pid, *control = target_hwnd
            target_control = control[0] if control else None
        logger.info("Preparing clipboard injection (%d characters).", len(text))

        try:
            # Backup previous clipboard
            previous_clip = None
            if restore_clipboard:
                previous_clip = self._capture_clipboard_snapshot()

            # Copy new text safely to clipboard
            success = self._safe_copy_to_clipboard(text)
            if not success:
                logger.error("Failed to copy transcribed text to clipboard after retries.")
                return False
            injected_clipboard_sequence = self._clipboard_sequence()

            auto_paste = config_manager.get("auto_paste", True)
            pasted = False

            if auto_paste:
                if target_hwnd and target_pid is not None:
                    try:
                        _, live_target_pid = win32process.GetWindowThreadProcessId(target_hwnd)
                    except Exception:
                        live_target_pid = None
                    if live_target_pid != target_pid:
                        logger.warning("Paste was skipped because the captured target window is stale.")
                        target_hwnd = None
                        target_pid = -1
                    elif self._is_process_elevated(target_pid) is True and not is_running_as_administrator():
                        logger.warning("Paste was skipped because the target is elevated and PrimeDictate is not.")
                        target_hwnd = None
                        target_pid = -1

                # Restore focus to target window if specified
                if target_pid != -1 and target_hwnd and win32gui.IsWindow(target_hwnd):
                    self._force_foreground(target_hwnd)
                    time.sleep(0.08)
                    if target_control and win32gui.IsWindow(target_control):
                        self._restore_child_focus(target_control)

                current_hwnd = win32gui.GetForegroundWindow()

                is_safe_target = False
                if target_pid == -1:
                    logger.warning("Paste was skipped because the captured target is no longer valid.")
                elif target_hwnd:
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
                    # Never reinterpret whichever window happens to be active
                    # after transcription as the target. The text remains on
                    # the clipboard when no external target was captured.
                    logger.warning("Auto-paste skipped because no safe target window was captured.")

                if is_safe_target:
                    time.sleep(0.05)
                    pasted = self._send_paste_keys()
                    logger.info("Sent the paste key combination to the verified target window.")

            # Restore original clipboard asynchronously if requested
            if pasted and restore_clipboard and previous_clip is not None:
                def restore():
                    time.sleep(0.6)
                    current_sequence = self._clipboard_sequence()
                    if (
                        injected_clipboard_sequence is not None
                        and current_sequence is not None
                        and current_sequence != injected_clipboard_sequence
                    ):
                        logger.info("Clipboard restoration skipped because the clipboard changed after injection.")
                        return
                    self._restore_clipboard_snapshot(previous_clip)
                if previous_clip[0] == "qt":
                    # paste_text runs on the Qt thread in production; preserve
                    # GUI-thread ownership while restoring rich MIME formats.
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(600, restore)
                else:
                    threading.Thread(target=restore, daemon=True, name="ClipboardRestore").start()

            return pasted

        except Exception as e:
            logger.error(f"Error in PasteInjector: {e}")
            return False

paste_injector = PasteInjector()
