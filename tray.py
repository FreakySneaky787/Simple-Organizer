# tray.py
"""System tray icon for Simple Organizer (Windows and Linux).

Uses pystray, which is optional: without it (or without a tray on the
desktop) is_available() is False and the app falls back to minimising the
window to the taskbar.

Linux backends, tried by pystray in this order: AppIndicator (GNOME needs the
"AppIndicator and KStatusNotifierItem Support" extension, which Ubuntu and
Debian's GNOME ship), GTK and plain X11. On Debian the package recommends
python3-pystray, python3-gi and gir1.2-ayatanaappindicator3-0.1.

The menu callbacks run on pystray's thread. They never touch Tk: they only
call the functions they were given, which must be thread-safe (the app puts
an event into its queue).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, Callable

_ICON_PNG = Path(__file__).resolve().with_name("icon.png")
_import_error: str = ""
pystray: Any = None
Image:   Any = None


def _load() -> bool:
    """Import pystray when it is first needed, not at program start.

    On Linux pystray connects to the display while it is imported: started
    too early (no DISPLAY yet) it fails, so a failed attempt is retried.
    """
    global pystray, Image, _import_error
    if pystray is not None:
        return True
    try:
        from PIL import Image as _image_module
        import pystray as _pystray
    except Exception as exc:  # noqa: BLE001 -- ImportError, or no display backend on Linux
        _import_error = str(exc) or exc.__class__.__name__
        return False
    pystray, Image, _import_error = _pystray, _image_module, ""
    return True


def _resource(name: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)   # PyInstaller one-file bundle
    return Path(base) / name if base else _ICON_PNG.with_name(name)


def is_available() -> bool:
    return _load()


def unavailable_reason() -> str:
    if _load():
        return ""
    if "No module named" in _import_error and sys.platform.startswith("linux"):
        return ("The tray needs python3-pystray (sudo apt install python3-pystray "
                "gir1.2-ayatanaappindicator3-0.1).")
    return f"The tray could not be started ({_import_error})."


def _image() -> Any:
    try:
        return Image.open(_resource("icon.png"))
    except Exception:  # noqa: BLE001 -- a plain square is better than no tray icon
        return Image.new("RGBA", (64, 64), (59, 130, 246, 255))


class TrayIcon:
    """The tray icon and its menu. All callbacks must be thread-safe."""

    def __init__(
        self,
        title: str,
        on_open: Callable[[], None],
        on_organize: Callable[[], None],
        on_toggle_schedule: Callable[[], None],
        schedule_on: Callable[[], bool],
        on_quit: Callable[[], None],
    ) -> None:
        self._title = title
        self._on_open = on_open
        self._on_organize = on_organize
        self._on_toggle_schedule = on_toggle_schedule
        self._schedule_on = schedule_on
        self._on_quit = on_quit
        self._icon: Any = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._icon is not None

    def start(self) -> bool:
        """Show the icon. Returns False if no tray could be created."""
        if not _load():
            return False
        with self._lock:
            if self._icon is not None:
                return True
            menu = pystray.Menu(
                pystray.MenuItem("Open Simple Organizer", lambda *_: self._on_open(), default=True),
                pystray.MenuItem("Organize now", lambda *_: self._on_organize()),
                pystray.MenuItem("Auto-organize", lambda *_: self._on_toggle_schedule(),
                                 checked=lambda _item: self._schedule_on()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda *_: self._on_quit()),
            )
            try:
                icon = pystray.Icon("simple_organizer", _image(), self._title, menu)
                # run_detached lets Tk keep the main thread; where a backend
                # cannot do that, run the icon's own loop on a thread.
                try:
                    icon.run_detached()
                except NotImplementedError:
                    threading.Thread(target=icon.run, name="tray", daemon=True).start()
            except Exception:  # noqa: BLE001 -- no tray on this desktop
                return False
            self._icon = icon
            return True

    def refresh(self) -> None:
        """Redraw the menu (the Auto-organize check mark)."""
        icon = self._icon
        if icon is not None:
            try:
                icon.update_menu()
            except Exception:  # noqa: BLE001
                pass

    def notify(self, message: str, title: str = "") -> None:
        icon = self._icon
        if icon is not None and getattr(icon, "HAS_NOTIFICATION", False):
            try:
                icon.notify(message, title or self._title)
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        with self._lock:
            icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                pass
