# autostart.py
"""Start Simple Organizer when the user logs in.

Windows : a value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
          (per user, no admin rights needed)
Linux   : ~/.config/autostart/simple-organizer.desktop (XDG autostart,
          honoured by GNOME, KDE, Xfce, Cinnamon, MATE, LXQt ...)

The app starts with --minimized, so it goes straight to the tray (or the
taskbar) and Auto-organize keeps working without a window in the way.
is_enabled() reads the real system state, so the checkbox in the app is
right even if the user removed the entry in Task Manager or the desktop's
startup settings.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

APP_NAME     = "Simple Organizer"
RUN_KEY      = r"Software\Microsoft\Windows\CurrentVersion\Run"
DESKTOP_NAME = "simple-organizer.desktop"
DEB_LAUNCHER = "/usr/bin/simple-organizer"
DEB_PROGRAM  = "/usr/lib/simple-organizer"
MINIMIZED    = "--minimized"


def is_supported() -> bool:
    return sys.platform == "win32" or sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# The command that starts the app
# ---------------------------------------------------------------------------

def _main_script() -> Path:
    return Path(__file__).resolve().with_name("main.py")


def _windows_python() -> str:
    """pythonw.exe next to python.exe, so no console window opens at login."""
    exe = Path(sys.executable)
    windowed = exe.with_name("pythonw.exe")
    return str(windowed if windowed.exists() else exe)


def command_args() -> list[str]:
    """The program and arguments the login entry runs."""
    if getattr(sys, "frozen", False):          # PyInstaller exe
        return [str(Path(sys.executable).resolve()), MINIMIZED]
    if sys.platform == "win32":
        return [_windows_python(), str(_main_script()), MINIMIZED]
    # Installed from the .deb package: use its start script.
    if os.path.isfile(DEB_LAUNCHER) and str(_main_script()).startswith(DEB_PROGRAM + "/"):
        return [DEB_LAUNCHER, MINIMIZED]
    return [sys.executable, str(_main_script()), MINIMIZED]


def _windows_command() -> str:
    return " ".join(a if a.startswith("-") else f'"{a}"' for a in command_args())


# ---------------------------------------------------------------------------
# Linux (XDG)
# ---------------------------------------------------------------------------

def autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base) if base and os.path.isabs(base) else Path.home() / ".config"
    return root / "autostart"


def desktop_file() -> Path:
    return autostart_dir() / DESKTOP_NAME


def _desktop_exec(args: list[str]) -> str:
    # Desktop Entry spec: quote arguments with spaces, escape " ` $ \ inside quotes.
    out = []
    for a in args:
        if a and all(c.isalnum() or c in "-_./=+:," for c in a):
            out.append(a)
        else:
            esc = a.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
            out.append(f'"{esc}"')
    return " ".join(out)


def desktop_entry() -> str:
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            "Comment=Keep folders organised in the background\n"
            f"Exec={_desktop_exec(command_args())}\n"
            "Icon=simple-organizer\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
            "X-GNOME-Autostart-Delay=10\n")


def _linux_enabled() -> bool:
    path = desktop_file()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        key, _, value = (part.strip() for part in line.partition("="))
        if key == "Hidden" and value.lower() == "true":
            return False
        if key == "X-GNOME-Autostart-enabled" and value.lower() == "false":
            return False
    return True


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _winreg():   # imported lazily: the module exists only on Windows
    import winreg
    return winreg


def _windows_enabled() -> bool:
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(str(value).strip())
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    try:
        if sys.platform == "win32":
            return _windows_enabled()
        if sys.platform.startswith("linux"):
            return _linux_enabled()
    except Exception:  # noqa: BLE001 -- the checkbox must never break the app
        return False
    return False


def enable() -> None:
    """Create or refresh the login entry. Raises OSError on failure."""
    if sys.platform == "win32":
        winreg = _winreg()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _windows_command())
    elif sys.platform.startswith("linux"):
        path = desktop_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(desktop_entry(), encoding="utf-8")
        os.replace(tmp, path)
    else:
        raise OSError("Starting at login is not supported on this system.")


def disable() -> None:
    """Remove the login entry. Raises OSError on failure; absent is fine."""
    if sys.platform == "win32":
        winreg = _winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    elif sys.platform.startswith("linux"):
        try:
            desktop_file().unlink()
        except FileNotFoundError:
            pass


def _split_command(text: str) -> list[str]:
    """The arguments of a Windows Run value or a desktop Exec line."""
    if sys.platform == "win32":
        return [m.group(1) if m.group(1) is not None else m.group(2)
                for m in re.finditer(r'"([^"]*)"|(\S+)', text)]
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def current_args() -> list[str] | None:
    """The arguments of the existing login entry, or None if there is none."""
    try:
        if sys.platform == "win32":
            winreg = _winreg()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
            return _split_command(str(value))
        if sys.platform.startswith("linux"):
            for line in desktop_file().read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition("=")
                if key.strip() == "Exec":
                    return _split_command(value.strip())
    except (OSError, ValueError):
        return None
    return None


def _same_or_missing(entry: list[str]) -> bool:
    """True if the entry starts this program, or a program that is gone."""
    ours = [a for a in command_args() if a != MINIMIZED]
    theirs = [a for a in entry if a != MINIMIZED]
    if [os.path.normcase(a) for a in theirs] == [os.path.normcase(a) for a in ours]:
        return True
    paths = [a for a in theirs if os.path.isabs(a)]
    return not paths or any(not os.path.exists(p) for p in paths)


def refresh() -> None:
    """Rewrite an existing entry when it starts this program (e.g. an older
    format) or a program that no longer exists (the exe was moved).

    An entry for another copy that still exists is left alone: trying a
    second copy once must not move the login start to it (#114).
    """
    if not is_enabled():
        return
    entry = current_args()
    if entry is not None and not _same_or_missing(entry):
        return
    try:
        enable()
    except OSError:
        pass


__all__ = ["is_supported", "is_enabled", "enable", "disable", "refresh",
           "command_args", "desktop_entry", "desktop_file", "MINIMIZED"]
