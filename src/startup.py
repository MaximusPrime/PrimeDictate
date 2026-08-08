import os
import sys
import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PrimeDictate"


def configure_start_with_windows(enabled: bool):
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}" --start-hidden'
            else:
                pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                command = f'"{pythonw}" "{os.path.join(project_root, "run.py")}" --start-hidden'
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
