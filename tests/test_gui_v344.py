"""GUI tests for the v3.4.4 fixes. Drives the real app; no blocking dialog is opened."""
import ctypes, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so344_gui_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
import main, organizer, utils
from organizer import FilePlan

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

lock = utils.acquire_instance_lock()
app = main.SimpleOrganizerApp()
app._instance_lock = lock
app.update()
check("title shows the version", app.title().endswith(f"v{main.APP_VERSION}"))

# ---------- #30 a second start does not open a second window ----------
t0 = time.monotonic()
second = subprocess.run([sys.executable, "-c",
    "import sys; sys.path.insert(0, ' + repr(ROOT) + '); import main; main.main(); print('exited')"],
    capture_output=True, text=True, timeout=60, env={**os.environ})
check("#30 second start exits on its own (no second app)", "exited" in second.stdout and
      time.monotonic() - t0 < 30, second.stdout + second.stderr)

# ---------- #32 History undo asks first ----------
work = APPDATA / "work"; work.mkdir()
(work / "a.pdf").write_text("a")
organizer.organise_files([FilePlan(work / "a.pdf", work / "Documents" / "a.pdf", "Documents", root=work)])
app._refresh_persistent_buttons()
asked = []
real_ask = main._askyesno
main._askyesno = lambda **kw: asked.append(kw["message"]) or False
dlg = main._HistoryDialog(app)
app.update()

# ---------- #34 dialogs are owned by the main window ----------
check("#34 dialog is owned by the main window (Win32 owner)",
      ctypes.windll.user32.GetWindow(int(dlg.wm_frame(), 16), 4) == int(app.wm_frame(), 16))
user32 = ctypes.windll.user32
app.lift(); app.focus_force(); pump(app, 0.3)
dlg_hwnd, app_hwnd = int(dlg.wm_frame(), 16), int(app.wm_frame(), 16)
above, h = False, dlg_hwnd
for _ in range(5000):
    h = user32.GetWindow(h, 2)        # GW_HWNDNEXT: next window below
    if not h:
        break
    if h == app_hwnd:
        above = True
        break
check("#34 dialog stays above the main window after the main window is raised", above)

dlg._on_undo()
app.update()
main._askyesno = real_ask
check("#32 undo from History asks for confirmation", len(asked) == 1 and "1 file(s)" in asked[0], asked)
check("#32 declining leaves the run alone", (work / "Documents" / "a.pdf").exists() and not app._busy_flag)

# ---------- #36 Ctrl+Z inside a number field ----------
calls = []
real_undo = app._confirm_and_undo
app._confirm_and_undo = lambda: calls.append("undo")
app._bind_shortcuts()                      # rebind so the patched method is used
entry = app._max_depth_spin._entry
entry.focus_force(); pump(app, 0.2)
entry.event_generate("<Control-z>"); app.update()
check("#36 Ctrl+Z in a number field does not open Undo", calls == [], calls)
app._preview_tree.focus_force(); pump(app, 0.2)
app._preview_tree.event_generate("<Control-z>"); app.update()
check("#36 Ctrl+Z elsewhere still opens Undo", calls == ["undo"], calls)
app._confirm_and_undo = real_undo
app._bind_shortcuts()

# ---------- #39 position only where it is reliable ----------
app.geometry("1000x750+120+80"); app.update()
check("#39 Windows keeps the position", "window_x" in app._geometry_settings())
app._keeps_position = lambda: False
g = app._geometry_settings()
check("#39 elsewhere only size is saved", "window_x" not in g and g.get("window_width") == 1000, g)
del app._keeps_position

# ---------- #42 errors are reported, not swallowed ----------
log_file = APPDATA / "simple_organizer" / "error.log"
toasts = []
real_notify = app._notify
app._notify("probe", "probe", "info"); app.update()
check("#34 notification is owned by the main window",
      ctypes.windll.user32.GetWindow(int(app._toast.wm_frame(), 16), 4) == int(app.wm_frame(), 16))
app._notify = lambda *a, **k: toasts.append(a)
app.after(0, lambda: 1 / 0)
pump(app, 0.5)
check("#42 callback error written to error.log", log_file.exists() and "ZeroDivisionError" in log_file.read_text())
check("#42 callback error shown in the log and as notification",
      "Unexpected error" in app._log_box.get("1.0", "end") and toasts and toasts[-1][0] == "Something went wrong")
real_err = main._showerror
main._showerror = lambda *a, **k: None
app._start_task("crash", lambda p, l: {}["missing"])
pump(app, 5, lambda: not app._busy_flag)
main._showerror = real_err
check("#42 worker crash traceback written to error.log",
      "task failed" in log_file.read_text() and "KeyError" in log_file.read_text())

# ---------- #46 window handle for the trash dialog ----------
h = app._native_handle()
check("#46 native window handle available", isinstance(h, int) and user32.IsWindow(h))

# ---------- #48 missing folder ----------
toasts.clear()
app._folder = Path(r"C:\does\not\exist\anymore")
app._schedule_enabled.set(True)
app._run_scheduled_organize()
app._run_scheduled_organize()
check("#48 status shows the folder is missing", "not found" in app._schedule_status_var.get(),
      app._schedule_status_var.get())
check("#48 one notification, no scan started", len(toasts) == 1 and not app._busy_flag, toasts)
app._schedule_enabled.set(False)
app._folder = work
app._notify = real_notify

# ---------- #49 settings write failure is reported once ----------
real_save = main.save_settings
def warnings():
    return app._log_box.get("1.0", "end").count("Settings could not be saved")
before = warnings()
main.save_settings = lambda s: False
for _ in range(4):
    app._save_settings()
check("#49 failure logged once, not on every save", warnings() - before == 1, warnings() - before)
main.save_settings = lambda s: True
app._save_settings()
main.save_settings = lambda s: False
app._save_settings()
check("#49 logged again after a success in between", warnings() - before == 2)
main.save_settings = real_save

app.destroy()
lock.close()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
