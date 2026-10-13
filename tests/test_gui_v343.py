"""GUI tests for the v3.4.3 fixes. Drives the real app; no modal dialog is opened."""
import os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so343_gui_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
import config, main, organizer
from organizer import FilePlan, ScanResult

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def pump(app, seconds, until):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        if until():
            return True
        time.sleep(0.005)
    return False

app = main.SimpleOrganizerApp()
app.update()
check("title shows the version", app.title().endswith(f"v{main.APP_VERSION}"))

# ---------- #16 large result is filled in slices ----------
N = 30_000
big = ScanResult(plans=[FilePlan(Path(f"C:/x/f{i}.txt"), Path(f"C:/x/Documents/f{i}.txt"), "Documents")
                        for i in range(N)], total_files=N)
app._scan_result = big
t0 = time.perf_counter()
app._render_scan_result()
first_call = time.perf_counter() - t0
check("#16 render call returns quickly", first_call < 0.15, f"{first_call:.3f}s")
check("#16 only part of the rows inserted at first", 0 < len(app._preview_items) < N, len(app._preview_items))
import _tkinter   # one event at a time, exactly like mainloop
worst = 0.0
end = time.monotonic() + 60
while len(app._preview_items) < N and time.monotonic() < end:
    t = time.perf_counter()
    app.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT)
    worst = max(worst, time.perf_counter() - t)
check("#16 all rows arrive", len(app._preview_items) == N, len(app._preview_items))
check("#16 no single UI step blocks long", worst < 0.2, f"{worst:.3f}s")
app._scan_result = big
app._render_scan_result()
app._scan_result = None
app._render_scan_result()          # a newer render cancels the running fill
pump(app, 0.5, lambda: False)
check("#16 cancelled fill adds no stale rows", not app._preview_tree.get_children())

# ---------- #17 log is bounded ----------
for i in range(main._LOG_MAX_LINES + 700):
    app._log(f"line {i}")
lines = int(app._log_box.index("end-1c").split(".")[0]) - 1
check("#17 log keeps at most _LOG_MAX_LINES", lines == main._LOG_MAX_LINES, lines)
check("#17 newest line kept, oldest dropped",
      f"line {main._LOG_MAX_LINES + 699}" in app._log_box.get("end-2l", "end")
      and "line 0\n" not in app._log_box.get("1.0", "3.0"))

# ---------- #21 crash of a moving task drops the stale plan ----------
small = ScanResult(plans=[FilePlan(Path("C:/x/a.txt"), Path("C:/x/Documents/a.txt"), "Documents")], total_files=1)
app._scan_result = small
app._render_scan_result()
real_showerror = main._showerror
main._showerror = lambda *a, **k: None   # the real one is modal
app._start_task("test", lambda p, l: (_ for _ in ()).throw(RuntimeError("boom")))
pump(app, 5, lambda: not app._busy_flag)
check("#21 scan result dropped after crash of a moving task", app._scan_result is None)
check("#21 Organize disabled", str(app._organize_btn.cget("state")) == "disabled")
app._scan_result = small
app._render_scan_result()
app._start_task("scan", lambda p, l: (_ for _ in ()).throw(RuntimeError("boom")), moves_files=False)
pump(app, 5, lambda: not app._busy_flag)
check("#21 crash of a scan keeps the shown result", app._scan_result is small)
main._showerror = real_showerror

# ---------- #22 Caps Lock ----------
for key in "ROZQ":
    check(f"#22 <Control-{key}> bound", bool(app.bind_all(f"<Control-{key}>")))

# ---------- #24 approvals persist and paused status is visible ----------
folder = Path.home()            # an "unusual" folder
app._folder = folder
app._schedule_enabled.set(True)
app._update_schedule_status()
check("#24 schedule shows Paused for an unconfirmed unusual folder",
      app._schedule_status_var.get().startswith("Paused"))
toasts = []
real_notify = app._notify
app._notify = lambda *a, **k: toasts.append(a)
app._run_scheduled_organize()
app._run_scheduled_organize()
check("#24 skipped run shows one notification", len(toasts) == 1 and not app._busy_flag, toasts)
app._notify = real_notify
app._approve(folder)
app._save_settings()
check("#24 status becomes Active after confirming", app._schedule_status_var.get().startswith("Active"))
check("#24 approval stored in settings.json",
      os.path.normcase(str(folder)) in [os.path.normcase(f) for f in config.load_settings()["approved_folders"]])
app._schedule_enabled.set(False)
app._update_schedule_status()

# ---------- #26 stepper adopts an automatic correction ----------
calls = []
app._sched_spin._command = lambda: calls.append(1)
app._schedule_interval.set(5000)
app._num(app._schedule_interval, "schedule_interval_minutes", commit=True)
app._sched_spin._nudge(0)       # focus leaves the field
check("#26 corrected value is not seen as a change", calls == [] and app._schedule_interval.get() == 1440, calls)

# ---------- #27 geometry ----------
app.state("normal"); app.geometry("1000x750+120+80"); app.update()
g = app._geometry_settings()
check("#27 normal geometry saved with position",
      g.get("window_width") == 1000 and g.get("window_x") == 120 and g.get("window_maximized") is False, g)
app.state("zoomed"); app.update()
g = app._geometry_settings()
check("#27 maximised: only the flag is saved", g == {"window_maximized": True}, g)
app.state("normal"); app.update()
app._settings.update({"window_width": 99999, "window_height": 99999, "window_x": -50000,
                      "window_y": 50000, "window_maximized": False})
app._restore_geometry(); app.update()
left, top, right, bottom = app._work_area(app.winfo_x(), app.winfo_y())
check("#27 oversized / off-screen window fitted to the monitor",
      app.winfo_width() <= right - left and left - 10 <= app.winfo_x() <= right
      and top - 40 <= app.winfo_y() <= bottom, (app.wm_geometry(), (left, top, right, bottom)))

app.destroy()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
