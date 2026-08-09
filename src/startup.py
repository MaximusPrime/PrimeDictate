"""Windows sign-in startup registration for standard and elevated launches."""

import base64
import getpass
import os
import subprocess
import sys
import time
import winreg
import xml.etree.ElementTree as ET

from src.elevation import ELEVATED_RELAUNCH_ARG, is_running_as_administrator


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PrimeDictate"
ELEVATED_TASK_NAME = "PrimeDictate Elevated Startup"
SHOW_REQUEST_PATH = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "PrimeDictate",
    ".show-elevated-window",
)


def _launch_parts(start_hidden: bool = True):
    arguments = []
    if not getattr(sys, "frozen", False):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        arguments.append(os.path.join(project_root, "run.py"))
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        executable = pythonw if os.path.isfile(pythonw) else sys.executable
        working_directory = project_root
    else:
        executable = sys.executable
        working_directory = os.path.dirname(sys.executable)
    if start_hidden:
        arguments.append("--start-hidden")
    return executable, arguments, working_directory


def _registry_command():
    executable, arguments, _ = _launch_parts(start_hidden=True)
    return subprocess.list2cmdline([executable, *arguments])


def _set_registry_startup(enabled: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _registry_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def elevated_startup_task_exists() -> bool:
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", ELEVATED_TASK_NAME],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.returncode == 0


def _elevated_task_matches_launch(start_with_windows: bool = None) -> bool:
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", ELEVATED_TASK_NAME, "/XML"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        return False
    try:
        root = ET.fromstring(result.stdout.decode("utf-16") if result.stdout.startswith(b"\xff\xfe") else result.stdout.decode(errors="replace"))
        values = {element.tag.rsplit("}", 1)[-1]: (element.text or "") for element in root.iter()}
        executable, arguments, working_directory = _launch_parts(start_hidden=True)
        arguments.append(ELEVATED_RELAUNCH_ARG)
        launch_matches = (
            os.path.normcase(values.get("Command", "")) == os.path.normcase(executable)
            and values.get("Arguments", "") == subprocess.list2cmdline(arguments)
            and os.path.normcase(values.get("WorkingDirectory", "")) == os.path.normcase(working_directory)
        )
        has_logon_trigger = any(element.tag.rsplit("}", 1)[-1] == "LogonTrigger" for element in root.iter())
        return launch_matches and (
            start_with_windows is None or has_logon_trigger == start_with_windows
        )
    except (UnicodeError, ET.ParseError):
        return False


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_powershell_with_one_time_elevation(script: str):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    inner_arguments = ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    if is_running_as_administrator():
        command = ["powershell.exe", *inner_arguments]
    else:
        argument_list = ",".join(_ps_quote(value) for value in inner_arguments)
        launcher = (
            "$p=Start-Process -FilePath 'powershell.exe' "
            f"-ArgumentList @({argument_list}) -Verb RunAs -WindowStyle Hidden -Wait -PassThru; "
            "exit $p.ExitCode"
        )
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", launcher]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "UAC approval was cancelled.").strip()
        raise OSError(detail)


def _configure_elevated_task(enabled: bool, start_with_windows: bool = False):
    if not enabled:
        if not elevated_startup_task_exists():
            return
        script = (
            "$ErrorActionPreference='Stop'; "
            f"Unregister-ScheduledTask -TaskName {_ps_quote(ELEVATED_TASK_NAME)} -Confirm:$false"
        )
        _run_powershell_with_one_time_elevation(script)
        return

    if _elevated_task_matches_launch(start_with_windows):
        return
    executable, arguments, working_directory = _launch_parts(start_hidden=True)
    arguments.append(ELEVATED_RELAUNCH_ARG)
    action_arguments = subprocess.list2cmdline(arguments)
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip() or getpass.getuser()
    user_id = f"{domain}\\{username}" if domain else username
    commands = [
        "$ErrorActionPreference='Stop'",
        f"$action=New-ScheduledTaskAction -Execute {_ps_quote(executable)} -Argument {_ps_quote(action_arguments)} -WorkingDirectory {_ps_quote(working_directory)}",
        f"$principal=New-ScheduledTaskPrincipal -UserId {_ps_quote(user_id)} -LogonType Interactive -RunLevel Highest",
        "$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)",
    ]
    trigger_argument = ""
    if start_with_windows:
        commands.append(f"$trigger=New-ScheduledTaskTrigger -AtLogOn -User {_ps_quote(user_id)}")
        trigger_argument = " -Trigger $trigger"
    commands.append(
        f"Register-ScheduledTask -TaskName {_ps_quote(ELEVATED_TASK_NAME)} -Action $action{trigger_argument} -Principal $principal -Settings $settings -Force | Out-Null"
    )
    script = "; ".join(commands)
    _run_powershell_with_one_time_elevation(script)


def launch_elevated_task(show_window: bool = True) -> bool:
    """Run the pre-authorized elevated task without showing UAC again."""
    if not _elevated_task_matches_launch():
        return False
    if show_window:
        os.makedirs(os.path.dirname(SHOW_REQUEST_PATH), exist_ok=True)
        with open(SHOW_REQUEST_PATH, "w", encoding="ascii") as request_file:
            request_file.write(str(time.time()))
    result = subprocess.run(
        ["schtasks.exe", "/Run", "/TN", ELEVATED_TASK_NAME],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 and show_window:
        try:
            os.remove(SHOW_REQUEST_PATH)
        except FileNotFoundError:
            pass
    return result.returncode == 0


def consume_show_window_request() -> bool:
    try:
        age = time.time() - os.path.getmtime(SHOW_REQUEST_PATH)
        os.remove(SHOW_REQUEST_PATH)
        return 0 <= age <= 30
    except (FileNotFoundError, OSError):
        return False


def configure_start_with_windows(enabled: bool, elevated: bool = False):
    """Configure one startup source, using Task Scheduler for elevated startup.

    Registering/removing the highest-privilege task may produce one UAC prompt.
    Once registered, sign-in launches do not prompt again.
    """
    if elevated:
        _set_registry_startup(False)
        _configure_elevated_task(True, start_with_windows=enabled)
    elif enabled:
        _configure_elevated_task(False)
        _set_registry_startup(True)
    else:
        _set_registry_startup(False)
        _configure_elevated_task(False)
