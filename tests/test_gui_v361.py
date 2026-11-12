"""GUI tests for v3.6.1: messages while hidden in the tray (#109), Quit with a
dialog open (#110) and the cancel message (#111)."""
import os, shutil, sys, tempfile, time
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="so361_gui_")
APPDATA = Path(os.environ["APPDATA"])
os.environ["XDG_CONFIG_HOME"] = str(APPDATA / "xdg")
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def pump(app, seconds, until=lambda: False):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        if until():
            return True
        time.sleep(0.01)
    return False

import main, autostart

autostart.enable = lambda: None
autostart.disable = lambda: None
autostart.is_enabled = lambda: False
autostart.refresh = lambda: None

class FakeTray:
    running = True
    can_notify = True
    def __init__(self): self.notes = []
    def notify(self, message, title=""): self.notes.append((title, message))
    def refresh(self): pass
    def stop(self): self.running = False

errors_shown: list[str] = []
main._showerror = lambda title, message, parent: errors_shown.append(message)

app = main.SimpleOrganizerApp()
app.update()
check("title shows 3.6.1", app.title().endswith("v3.6.1"), app.title())

# ---------- #109 messages while hidden ----------
fake = FakeTray()
app._tray = fake
app._ensure_tray = lambda: True
app._tray_on_close.set(True)
app._hidden_hint_shown = True
app._on_close()
pump(app, 0.3)
check("#109 window hidden", app._hidden)
app._notify("Auto-organize paused", "The folder was not found.", "warning")
check("#109 hidden: system notification instead of a toast",
      fake.notes == [("Auto-organize paused", "The folder was not found.")] and not app._toast, fake.notes)

app._task_moves_files = False
app._event_queue.put({"type": "error", "value": "Boom"})
pump(app, 0.5)
check("#109 hidden: no dialog for an error", errors_shown == [], errors_shown)
check("#109 hidden: nothing counts as an open dialog", not app._modal_open())
check("#109 hidden: the error is notified", any("went wrong" in t.lower() for t, _ in fake.notes), fake.notes)

# Without system notifications the message waits for the window.
fake.can_notify = False
app._notify("Folder organised", "All files were moved.")
check("#109 no notifications: message kept", app._pending_notice is not None)
app._show_from_background()
pump(app, 0.5)
check("#109 shown again: the waiting error dialog appears", errors_shown == ["Boom"], errors_shown)
check("#109 shown again: the waiting message is shown", app._pending_notice is None and app._toast is not None)

# ---------- #110 Quit while a dialog is open ----------
app._overlays.append(main.tk.Toplevel(app))
app._quit_app()
pump(app, 0.2)
check("#110 Quit with a dialog open does not quit", app.winfo_exists())
check("#110 and does not remember the request", not app._quitting)
app._overlays.pop().destroy()
app._on_close()
pump(app, 0.3)
check("#110 closing later still goes to the tray", app._hidden and app.winfo_exists())
app._show_from_background()
pump(app, 0.2)

# ---------- #111 cancel message with errors ----------
app._handle_organize_done(["x could not be moved"], staging=False, cancelled=True)
check("#111 cancelled run reports its errors", "1 error" in app._status_var.get(), app._status_var.get())

app._tray = None
app._quit_app()
pump(app, 0.5)
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
