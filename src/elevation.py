"""Windows elevation helpers shared by installed, portable and source runs."""

import ctypes
import os
import subprocess
import sys


ELEVATED_RELAUNCH_ARG = "--elevated-relaunch"


def is_running_as_administrator() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _launch_command(argv=None):
    argv = list(sys.argv if argv is None else argv)
    forwarded = [arg for arg in argv[1:] if arg != ELEVATED_RELAUNCH_ARG]
    forwarded.append(ELEVATED_RELAUNCH_ARG)
    if getattr(sys, "frozen", False):
        return sys.executable, forwarded, os.path.dirname(sys.executable)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(project_root, "run.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    executable = pythonw if os.path.isfile(pythonw) else sys.executable
    return executable, [script, *forwarded], project_root


def relaunch_as_administrator(argv=None) -> bool:
    if is_running_as_administrator():
        return False
    executable, arguments, working_directory = _launch_command(argv)
    parameters = subprocess.list2cmdline(arguments)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        working_directory,
        1,
    )
    return int(result) > 32


def should_attempt_configured_elevation(config, argv=None) -> bool:
    argv = list(sys.argv if argv is None else argv)
    return bool(
        config.get("run_as_administrator", False)
        and not is_running_as_administrator()
        and ELEVATED_RELAUNCH_ARG not in argv
    )
