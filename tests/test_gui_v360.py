"""GUI tests for v3.6.0: Cancel button (#89), emptied folders option (#87),
background mode (tray / minimise) and start at login."""
import json, os, shutil, sys, tempfile, time
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="so360_gui_")
APPDATA = Path(os.environ["APPDATA"])
os.environ["XDG_CONFIG_HOME"] = str(APPDATA / "xdg")
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
DATA = APPDATA / "simple_organizer"
DATA.mkdir(parents=True, exist_ok=True)

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

def settings():
    return json.loads((DATA / "settings.json").read_text(encoding="utf-8"))

import main, organizer, autostart, tray

# Never touch the real login entry of the person running the tests.
calls: list[str] = []
state = {"on": False}
autostart.enable = lambda: (calls.append("enable"), state.update(on=True))
autostart.disable = lambda: (calls.append("disable"), state.update(on=False))
autostart.is_enabled = lambda: state["on"]
autostart.refresh = lambda: None

app = main.SimpleOrganizerApp()
app.update()
check("title shows 3.6.0", app.title().endswith("v3.6.0"), app.title())
check("Cancel button hidden when idle", not app._cancel_btn.winfo_ismapped())
check("Remove emptied folders on by default", app._remove_empty.get())
check("background mode off by default", not app._tray_on_close.get())
check("start at login reflects the system", app._autostart_var.get() is False)

# ---------- #89 Cancel button during an Organize ----------
folder = (APPDATA / "work").resolve(); folder.mkdir()
for i in range(40):
    (folder / f"f{i}.pdf").write_text(str(i))
app._folder = folder
app._start_scan(confirmed=True)
pump(app, 20, lambda: app._scan_result is not None and not app._busy_flag)

real_move = organizer.safe_move
def slow_move(src, dst):
    time.sleep(0.05)
    real_move(src, dst)
organizer.safe_move = slow_move
try:
    app._start_organize(app._actionable_plans(), False, "Organising...")
    pump(app, 0.3)
    check("Cancel button shown while organising", app._cancel_btn.winfo_ismapped())
    app._cancel_task()
    check("Cancel button disabled after click", str(app._cancel_btn.cget("state")) == "disabled")
    pump(app, 20, lambda: not app._busy_flag)
finally:
    organizer.safe_move = real_move
pump(app, 0.3)
left = [n for n in os.listdir(folder) if n.endswith(".pdf")]
check("Organize stopped early", 0 < len(left) < 40, len(left))
check("Cancel button hidden again", not app._cancel_btn.winfo_ismapped())
check("status says cancelled", "cancelled" in app._status_var.get().lower(), app._status_var.get())
check("partial run can be undone", not organizer.undo_last_run()
      and len([n for n in os.listdir(folder) if n.endswith(".pdf")]) == 40)

# Cancel a scan.
app._scan_result = None
app._start_scan(confirmed=True)
app._cancel_task()
pump(app, 20, lambda: not app._busy_flag)
check("cancelled scan shows no result", app._scan_result is None)

# ---------- #87 option is saved ----------
app._remove_empty.set(False); app._save_settings()
check("Remove emptied folders saved", settings()["remove_empty_dirs"] is False)
app._remove_empty.set(True); app._save_settings()

# ---------- background mode ----------
app._tray_on_close.set(True); app._on_tray_toggle()
check("tray_on_close saved", settings()["tray_on_close"] is True)
app._on_close()
pump(app, 0.5)
check("closing hides the window instead of quitting",
      app._hidden and app.winfo_exists() and app.state() in ("withdrawn", "iconic"), app.state())
if tray.is_available():
    check("tray icon running", app._tray is not None and app._tray.running)
app._schedule_enabled.set(False)
app._event_queue.put({"type": "tray", "value": "schedule"})
pump(app, 0.3)
check("tray menu toggles Auto-organize", app._schedule_enabled.get())
app._event_queue.put({"type": "tray", "value": "schedule"})
pump(app, 0.3)

# A second start asks this one to show its window.
from utils import request_show
request_show()
pump(app, 2, lambda: not app._hidden)
check("second start shows the hidden window", not app._hidden and app.state() == "normal", app.state())

# ---------- start at login ----------
app._tray_on_close.set(False)
app._autostart_var.set(True); app._on_autostart_toggle()
check("start at login enabled", calls[-1] == "enable" and app._autostart_var.get())
check("start at login also keeps the app running when closed", app._tray_on_close.get())
app._autostart_var.set(False); app._on_autostart_toggle()
check("start at login disabled", calls[-1] == "disable" and not app._autostart_var.get())

# ---------- Quit from the tray really quits ----------
app._event_queue.put({"type": "tray", "value": "quit"})
pump(app, 1)
try:
    gone = not app.winfo_exists()
except Exception:
    gone = True
check("Quit closes the app", gone)
check("tray stopped on quit", app._tray is None)

# --minimized start (own process: a second Tk app in one process loses its images)
import subprocess
code = (f"import sys; sys.path.insert(0, {ROOT!r}); import main, autostart; "
        "autostart.refresh = lambda: None; "
        "a = main.SimpleOrganizerApp(start_minimized=True); "
        "[a.update() for _ in range(50)]; "
        "print('STATE', a._hidden, a.state()); a._quit_app()")
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                     env={**os.environ}).stdout
check("--minimized starts hidden", "STATE True withdrawn" in out or "STATE True iconic" in out, out)

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
