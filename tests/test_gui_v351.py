"""GUI tests for v3.5.1: "Don't move" survives a restart (#82).

The restart runs this script a second time (argument "restart") with the same
APPDATA: one process can only hold one app window.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

RESTART = sys.argv[1:] == ["restart"]
if not RESTART:
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="so351_gui_")
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

import main

folder = (APPDATA / "work").resolve()
app = main.SimpleOrganizerApp()
app.update()

if not RESTART:
    folder.mkdir()
    for name in ("a.pdf", "b.pdf", "c.jpg"):
        (folder / name).write_text(name)
    check("title shows the version", app.title().endswith(f"v{main.APP_VERSION}"))
    app._set_folder(folder)
    scan(app)
    by_name = {app._preview_tree.item(i, "values")[0]: i for i in app._preview_tree.get_children()}
    app._preview_tree.selection_set([by_name["a.pdf"]])
    app._toggle_excluded()
    saved = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
    check("#82 Don't move is saved", saved.get("excluded_files") == [os.path.normcase(str(folder / "a.pdf"))],
          saved.get("excluded_files"))
    app.destroy()

    run = subprocess.run([sys.executable, __file__, "restart"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=os.environ)
    print(run.stdout.replace("\nALL PASSED []", "").rstrip())
    check("restart run passed", run.returncode == 0, run.stderr[-2000:])
    shutil.rmtree(APPDATA, ignore_errors=True)
else:
    check("#82 same folder after restart", app._folder == folder, app._folder)
    scan(app)
    excluded = {p.source.name for p in app._scan_result.plans if p.excluded}
    check("#82 Don't move still set after restart", excluded == {"a.pdf"}, excluded)
    check("#82 not part of the run", "a.pdf" not in {p.source.name for p in app._actionable_plans()})
    other = (APPDATA / "other").resolve(); other.mkdir()
    app._set_folder(other)
    saved = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
    check("#82 list cleared for another folder", saved.get("excluded_files") == [],
          saved.get("excluded_files"))
    app.destroy()

print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
