"""GUI tests for the last review before v3.5.0: Don't move is kept for later scans
(also automatic ones), missing folder, CSV injection, empty Preview texts."""
import csv, json, os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so350f_gui_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)
DATA = APPDATA / "simple_organizer"
DATA.mkdir(parents=True)

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

import main
app = main.SimpleOrganizerApp()
app.update()

def scan():
    app._start_scan(confirmed=True)
    pump(app, 30, lambda: app._scan_result is not None and not app._busy_flag)
    pump(app, 0.5)

def rows_by_name():
    return {app._preview_tree.item(i, "values")[0]: i for i in app._preview_tree.get_children()}

# ---------- a missing folder is reported, not scanned ----------
warnings = []
real_warning = main._showwarning
main._showwarning = lambda title, message, parent: warnings.append((title, message))
app._folder = APPDATA / "unplugged"
app._start_scan()
pump(app, 0.3)
main._showwarning = real_warning
check("missing folder: warning instead of a scan", warnings and warnings[0][0] == "Folder not found"
      and not app._busy_flag, warnings)
check("missing folder: status says so", app._status_var.get() == "Folder not found.", app._status_var.get())

# A scheduled run whose folder vanishes right before the scan must not leave
# auto-mode on: the next manual scan would then organise without asking.
app._schedule_enabled.set(True)
real_is_dir = Path.is_dir
calls = []
def flaky_is_dir(self):
    if str(self) == str(app._folder):
        calls.append(1)
        return len(calls) == 1      # there for the schedule check, gone for the scan
    return real_is_dir(self)
Path.is_dir = flaky_is_dir
real_reason = main.risky_folder_reason
main.risky_folder_reason = lambda folder: None
app._run_scheduled_organize()
Path.is_dir = real_is_dir
main.risky_folder_reason = real_reason
check("vanished folder: no scan started", not app._busy_flag and len(calls) >= 2, calls)
check("vanished folder: auto-mode is off again", app._auto_mode is False)
app._schedule_enabled.set(False)

# ---------- Don't move is kept for the next scan of the folder ----------
folder = APPDATA / "work"; folder.mkdir()
for name in ("keep.pdf", "a.pdf", "c.jpg"):
    (folder / name).write_text(name)
app._set_folder(folder)
scan()
app._preview_tree.selection_set([rows_by_name()["keep.pdf"]])
app._toggle_excluded()
scan()
check("rescan keeps Don't move", "excluded" in app._preview_tree.item(rows_by_name()["keep.pdf"], "tags")
      and len(app._actionable_plans()) == 2)
check("rescan logs the kept file", "1 file(s) stay where they are" in app._log_box.get("1.0", "end"))

# An automatic run must not move the file either.
app._approve(folder)   # the test folder is below AppData, which needs one approval
app._schedule_enabled.set(True)
app._run_scheduled_organize()
pump(app, 30, lambda: (folder / "Documents" / "a.pdf").exists() and not app._busy_flag)
pump(app, 0.5)
check("automatic run leaves the Don't move file alone", (folder / "keep.pdf").exists()
      and (folder / "Documents" / "a.pdf").exists() and (folder / "Images" / "c.jpg").exists(),
      sorted(str(p.relative_to(folder)) for p in folder.rglob("*")))
app._schedule_enabled.set(False)
app._scheduler.stop()

scan()
app._preview_tree.selection_set([rows_by_name()["keep.pdf"]])
app._toggle_excluded()          # move again
scan()
check("move again is kept too", len(app._actionable_plans()) == 1)
app._preview_tree.selection_set([rows_by_name()["keep.pdf"]])
app._toggle_excluded()
other = APPDATA / "other"; other.mkdir()
(other / "keep.pdf").write_text("x")
app._set_folder(other)
scan()
check("another folder starts without Don't move", len(app._actionable_plans()) == 1
      and not app._excluded_keys)

# ---------- empty Preview explains itself ----------
app._set_folder(folder)
check("empty text before a scan", "press Scan" in app._preview_empty.cget("text"))
scan()
app._filter_var.set("nothing-matches-this"); pump(app, 0.5)
check("empty text for a search without matches", app._preview_empty.cget("text") == "No file matches the search.",
      app._preview_empty.cget("text"))
check("empty label visible", bool(app._preview_empty.winfo_manager()))
app._on_filter_escape(); pump(app, 0.5)
empty = APPDATA / "empty"; empty.mkdir()
app._set_folder(empty)
scan()
check("empty text for a folder without files", "No files" in app._preview_empty.cget("text"),
      app._preview_empty.cget("text"))
# A folder named like the category of its files: already in place (#84 in v3.5.1).
placed = APPDATA / "Documents"; placed.mkdir()
(placed / "x.pdf").write_text("x")
app._set_folder(placed)
scan()
check("empty text when everything is in place", "already in its folder" in app._preview_empty.cget("text"),
      app._preview_empty.cget("text"))

# ---------- CSV: file names are never formulas ----------
inj = APPDATA / "inj"; inj.mkdir()
for name in ("=1+1.txt", "-draft.txt", "+49 call.txt", "@home.txt", "plain.txt"):
    (inj / name).write_text(name)
app._set_folder(inj)
scan()
target = APPDATA / "export.csv"
real_save = main.filedialog.asksaveasfilename
main.filedialog.asksaveasfilename = lambda **k: str(target)
app._export_csv()
main.filedialog.asksaveasfilename = real_save
rows = list(csv.reader(target.read_bytes().decode("utf-8-sig").splitlines(), delimiter=main.csv_delimiter()))
names = sorted(r[1] for r in rows[1:])
check("CSV: risky names start with an apostrophe",
      names == sorted(["'=1+1.txt", "'-draft.txt", "'+49 call.txt", "'@home.txt", "plain.txt"]), names)
check("CSV: no cell starts a formula", not any(c[:1] in "=+-@" for r in rows for c in r if c))

# ---------- Export is disabled while a task runs ----------
app._set_busy(True)
check("Export disabled while busy", str(app._export_btn.cget("state")) == "disabled")
app._set_busy(False)
check("Export enabled again", str(app._export_btn.cget("state")) == "normal")

# ---------- undo in the scanned drive root counts as the current folder ----------
app._folder = Path("C:\\")
check("drive root: run below it is the current folder", app._is_current_folder("C:\\Downloads"))
check("drive root: itself", app._is_current_folder("C:\\"))
app._folder = folder
check("other folder is not current", not app._is_current_folder(str(other)))
check("prefix is not enough", not app._is_current_folder(str(folder) + "2"))

app.destroy()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
