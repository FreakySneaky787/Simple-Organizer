"""GUI smoke test: drives the real app without opening any modal dialog."""
import os, sys, tempfile, shutil, json, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so_gui_appdata_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
FOLDER = Path.home() / "so_selftest_tmp"
shutil.rmtree(FOLDER, ignore_errors=True)
FOLDER.mkdir()

import organizer, main
fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

# ---------- journal flush mid-run ----------
for i in range(3):
    (FOLDER / f"f{i}.txt").write_text(str(i))
organizer.JOURNAL_FLUSH_SECONDS = 0
seen = []
real_move = organizer.safe_move
def spy_move(src, dst):
    seen.append(len(list(organizer.HISTORY_DIR.glob("run_*.json"))))
    return real_move(src, dst)
organizer.safe_move = spy_move
organizer.organise_files(organizer.scan_folder(FOLDER).plans)
organizer.safe_move = real_move
check("history written while the run is still going", seen[1:] and all(seen[1:]), seen)
check("only one run file for one run", len(list(organizer.HISTORY_DIR.glob("run_*.json"))) == 1)
organizer.undo_last_run()
organizer.JOURNAL_FLUSH_SECONDS = 2.0

# ---------- app ----------
(FOLDER / "a.jpg").write_bytes(b"same")
(FOLDER / "b.jpg").write_bytes(b"same")
(FOLDER / "c.pdf").write_bytes(b"pdf")

app = main.SimpleOrganizerApp()
app.update()
app._set_folder(FOLDER)

def pump(seconds=10.0, until=lambda: not app._busy_flag):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        if until():
            return True
        time.sleep(0.01)
    return False

check("window icon set (fallback drawn)", app._icon is not None)
check("no drop hint without tkdnd", "drop" not in app._folder_tip._text and not app._dnd_enabled)

# stepper
calls = []
app._on_schedule_toggle = lambda: calls.append(1)   # instance override for counting
app._sched_spin._command = app._on_schedule_toggle
app._schedule_interval.set(60); app._sched_spin._value = 60
app._sched_spin._nudge(0)
check("focus-out without change does not restart timer", calls == [])
app._sched_spin._entry.delete(0, "end")
app._sched_spin._nudge(0)
check("empty field falls back to last value", app._schedule_interval.get() == 60 and calls == [])
app._sched_spin._nudge(1)
check("step snaps 60 -> 75 and runs command once", app._schedule_interval.get() == 75 and calls == [1])
app._schedule_interval.set(1); app._sched_spin._value = 1
app._sched_spin._nudge(1)
check("step snaps 1 -> 15", app._schedule_interval.get() == 15)
app._max_depth.set(999)
check("_num clamps", app._num(app._max_depth, "max_depth") == 50 and app._max_depth.get() == 999)
check("_num commit writes back", app._num(app._max_depth, "max_depth", commit=True) == 50 and app._max_depth.get() == 50)
app._scan_timeout.set(0)
check("timeout 0 clamped to 5", app._num(app._scan_timeout, "scan_timeout") == 5)
app._scan_timeout.set(30)

# scan
app._start_scan(confirmed=True)
check("scan finished", pump())
check("preview rows mapped to plans", len(app._preview_items) == 6, app._preview_items)
check("duplicate rows mapped to paths", len(app._dup_paths) == 2, app._dup_paths)
check("organize enabled after scan", str(app._organize_btn.cget("state")) == "normal")

# busy disables every action button and shortcut handlers
app._set_busy(True)
states = {n: str(getattr(app, n).cget("state")) for n in
          ("_organize_btn", "_undo_btn", "_history_btn", "_commit_btn", "_revert_btn", "_trash_btn")}
check("all action buttons disabled while busy", set(states.values()) == {"disabled"}, states)
app._confirm_and_undo(); app._confirm_and_organize(); app._confirm_and_commit()
app._confirm_and_revert(); app._open_history_dialog(); app._confirm_and_trash()
check("no dialog opened while busy", not app._overlays)
before = app._scan_result
app._start_scan()
check("second scan refused while busy", app._scan_result is before)
app._set_busy(False)
check("organize re-enabled after busy", str(app._organize_btn.cget("state")) == "normal")

# trash simulation: file vanished -> prune
(FOLDER / "b.jpg").unlink()
app._prune_scan_result([FOLDER / "b.jpg"])
check("vanished file pruned from plan", all(p.source.name != "b.jpg" for p in app._scan_result.plans))
check("duplicate group dissolved", app._scan_result.duplicate_groups == [] and not app._dup_paths)

# scheduled run waits for an open dialog
app._schedule_enabled.set(True)
app._overlays.append(object())   # pretend a dialog is open
app._run_scheduled_organize()
check("scheduled run postponed while dialog open", app._schedule_pending and not app._busy_flag)
app._run_scheduled_organize()
check("no second pending run", app._schedule_pending)
app._overlays.clear()
check("postponed run starts after dialog closed",
      pump(4, until=lambda: app._busy_flag or not app._schedule_pending) and not app._schedule_pending)
check("auto run finished", pump(15, until=lambda: not app._busy_flag and organizer.has_last_run()))
pump(1)
check("auto-organize moved files", (FOLDER / "Images" / "a.jpg").exists())
app._schedule_enabled.set(False)

# close while busy waits
app._set_busy(True)
app._on_close()
check("close while busy is postponed", app._close_requested and app.winfo_exists())
app._set_busy(False)
closed = False
try:
    for _ in range(50):
        app.update(); time.sleep(0.01)
except Exception:
    closed = True
try:
    closed = closed or not app.winfo_exists()
except Exception:
    closed = True
check("window closes once the task is done", closed)

organizer.undo_last_run()
shutil.rmtree(FOLDER, ignore_errors=True)
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
