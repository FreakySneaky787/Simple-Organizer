"""GUI tests for v3.5.3: "Don't move" per folder (#101), automatic runs keep the tab (#105)."""
import json, os, shutil, sys, tempfile, time
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="so353_gui_")
APPDATA = Path(os.environ["APPDATA"])
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

def scan(app):
    app._scan_result = None
    app._start_scan(confirmed=True)
    pump(app, 30, lambda: app._scan_result is not None and not app._busy_flag)
    pump(app, 0.5)

def saved_excluded():
    return json.loads((DATA / "settings.json").read_text(encoding="utf-8")).get("excluded_files")

import main, organizer

app = main.SimpleOrganizerApp()
app.update()
check("title shows the version", app.title().endswith(f"v{main.APP_VERSION}"), app.title())

# ---------- #101 Don't move survives picking the same folder or another one ----------
folder = (APPDATA / "work").resolve(); folder.mkdir()
other = (APPDATA / "other").resolve(); other.mkdir()
for name in ("a.pdf", "b.pdf", "c.jpg"):
    (folder / name).write_text(name)
app._set_folder(folder)
scan(app)
by_name = {app._preview_tree.item(i, "values")[0]: i for i in app._preview_tree.get_children()}
app._preview_tree.selection_set([by_name["a.pdf"], by_name["c.jpg"]])
app._toggle_excluded()
keys = sorted(os.path.normcase(str(folder / n)) for n in ("a.pdf", "c.jpg"))
check("#101 Don't move is saved", sorted(saved_excluded() or []) == keys, saved_excluded())

app._set_folder(folder)   # Browse -> the same folder again
check("#101 same folder again keeps the list", sorted(saved_excluded() or []) == keys, saved_excluded())
app._set_folder(other)
app._set_folder(folder)
check("#101 another folder and back keeps the list", sorted(saved_excluded() or []) == keys, saved_excluded())
scan(app)
excluded = {p.source.name for p in app._scan_result.plans if p.excluded}
check("#101 still applied by the scan", excluded == {"a.pdf", "c.jpg"}, excluded)

(folder / "c.jpg").unlink()
scan(app)
check("#101 entry of a deleted file is dropped",
      saved_excluded() == [os.path.normcase(str(folder / "a.pdf"))], saved_excluded())

# ---------- #105 automatic runs keep the selected tab and a shown scan ----------
app._approve(folder)
app._schedule_enabled.set(True)
check("manual scan result is shown", bool(app._actionable_plans()))
shown = app._scan_result
app._run_scheduled_organize()
pump(app, 1)
check("#105 automatic run skipped while a scan is shown",
      app._scan_result is shown and not app._busy_flag and (folder / "b.pdf").exists())

app._scan_result = None
app._render_scan_result()
app._notebook.select(app._dup_tab_idx)
pump(app, 0.2)
app._run_scheduled_organize()
check("#105 automatic run finished",
      pump(app, 20, until=lambda: not app._busy_flag and organizer.has_last_run()))
pump(app, 1)
check("#105 automatic run moved the file", (folder / "Documents" / "b.pdf").exists())
check("#105 Don't move still respected", (folder / "a.pdf").exists())
check("#105 selected tab unchanged", app._notebook.index("current") == app._dup_tab_idx,
      app._notebook.index("current"))
app._schedule_enabled.set(False)

app.destroy()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
