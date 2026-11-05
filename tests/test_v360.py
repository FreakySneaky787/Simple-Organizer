"""Core tests for v3.6.0: cancel (#89), remove emptied folders (#87),
duplicates of sorted files (#88) and start at login."""
import json, os, shutil, sys, tempfile, threading
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so360_"))
os.environ["APPDATA"] = str(APPDATA)
os.environ["XDG_CONFIG_HOME"] = str(APPDATA / "xdg")
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import organizer, rules, autostart
from rules import Rule

def fresh(*parts):
    d = APPDATA.joinpath("w", *parts)
    d.mkdir(parents=True)
    return d.resolve()

def tree(d):
    return sorted(p.relative_to(d).as_posix() + ("/" if p.is_dir() else "") for p in d.rglob("*"))

def newest_run():
    return json.loads(organizer._newest_run_file().read_text(encoding="utf-8"))

# ---------- #89 cancel an Organize after the current file ----------
d = fresh("cancel")
for i in range(10):
    (d / f"f{i}.pdf").write_text(f"file {i}")
r = organizer.scan_folder(d)
cancel = threading.Event()
moved: list[int] = []
def progress(cur, total):
    moved.append(cur)
    if cur == 4:
        cancel.set()
log: list[str] = []
errors = organizer.organise_files(r.plans, progress_callback=progress, log_callback=log.append,
                                  cancel=cancel)
in_docs = sorted(os.listdir(d / "Documents"))
check("#89 stops after the current file", len(in_docs) == 4, in_docs)
check("#89 the rest stays in place", len([n for n in os.listdir(d) if n.endswith(".pdf")]) == 6)
check("#89 no errors", not errors, errors)
check("#89 cancel is logged", any("[CANCELLED]" in m for m in log), log)
run = newest_run()
check("#89 history has the moved files and is marked", len(run["moves"]) == 4 and run["cancelled"], run)
check("#89 undo restores them", not organizer.undo_last_run()
      and len([n for n in os.listdir(d) if n.endswith(".pdf")]) == 10 and not (d / "Documents").exists(),
      tree(d))

# Cancel already set: nothing is moved and no history run is written.
before = organizer._newest_run_file()
cancel = threading.Event(); cancel.set()
organizer.organise_files(organizer.scan_folder(d).plans, cancel=cancel)
check("#89 cancelled before start moves nothing", not (d / "Documents").exists(), tree(d))
check("#89 ... and writes no history", organizer._newest_run_file() == before)

# Cancel a scan.
cancel = threading.Event(); cancel.set()
r = organizer.scan_folder(d, cancel=cancel)
check("#89 cancelled scan is marked and empty", r.cancelled and not r.plans and not r.duplicate_groups,
      (r.cancelled, len(r.plans)))
deep = fresh("cancel_rec")
for i in range(30):
    (deep / f"d{i}").mkdir(); (deep / f"d{i}" / "x.txt").write_text(str(i))
r = organizer.scan_folder(deep, recursive=True, cancel=cancel)
check("#89 cancelled recursive scan", r.cancelled and not r.plans)

# ---------- #87 remove folders a recursive Organize emptied ----------
d = fresh("empty")
(d / "Project" / "deep").mkdir(parents=True)
(d / "Project" / "deep" / "r.pdf").write_text("report")
(d / "Keep" / "sub").mkdir(parents=True)
(d / "Keep" / "a.pdf").write_text("a")
(d / "Keep" / "notes.unknownext").write_text("stays? no, goes to Others")
(d / "Keep" / "sub" / ".hidden").write_text("hidden file stays")
(d / "Untouched").mkdir()   # was empty before: not this run's business
r = organizer.scan_folder(d, recursive=True)
log = []
errors = organizer.organise_files(r.plans, log_callback=log.append, remove_empty_dirs=True)
check("#87 no errors", not errors, errors)
check("#87 emptied folders removed", not (d / "Project").exists(), tree(d))
check("#87 folder with a hidden file stays", (d / "Keep" / "sub" / ".hidden").exists(), tree(d))
check("#87 folder that was empty before stays", (d / "Untouched").is_dir())
check("#87 scanned folder stays", d.is_dir())
check("#87 cleanup is logged", any("[CLEANUP]" in m for m in log), log)
run = newest_run()
removed = sorted(os.path.relpath(x, d) for x in run["removed_dirs"])
check("#87 removed folders recorded", removed == sorted(["Project", os.path.join("Project", "deep")]), removed)
check("#87 undo re-creates them", not organizer.undo_last_run()
      and (d / "Project" / "deep" / "r.pdf").is_file() and (d / "Keep" / "a.pdf").is_file(), tree(d))

# Default off: nothing removed.
r = organizer.scan_folder(d, recursive=True)
organizer.organise_files(r.plans)
check("#87 off by default in the core", (d / "Project" / "deep").is_dir(), tree(d))
organizer.undo_last_run()

# Staging never removes folders.
r = organizer.scan_folder(d, recursive=True)
organizer.organise_files(r.plans, staging=True, remove_empty_dirs=True)
check("#87 staging keeps the folders", (d / "Project" / "deep").is_dir(), tree(d))
organizer.revert_staging()

# ---------- #88 duplicates of files that are already sorted ----------
d = fresh("dupes")
(d / "Documents").mkdir()
(d / "Documents" / "cv.pdf").write_text("my cv, same bytes")
(d / "cv (1).pdf").write_text("my cv, same bytes")
(d / "other.pdf").write_text("something else")
(d / "Images" / "Photos").mkdir(parents=True)
(d / "Images" / "Photos" / "old.jpg").write_bytes(b"\xff\xd8 photo bytes")
(d / "same_but_sorted_only.txt").write_text("unique")
(d / "Documents" / "a.txt").write_text("two sorted copies")
(d / "Documents" / "b.txt").write_text("two sorted copies")
(d / "new.jpg").write_bytes(b"\xff\xd8 photo bytes")
r = organizer.scan_folder(d)
groups = [sorted(os.path.relpath(p, d) for p in g) for g in r.duplicate_groups]
check("#88 new file vs sorted file found",
      sorted(["cv (1).pdf", os.path.join("Documents", "cv.pdf")]) in groups, groups)
check("#88 also in sub-category folders",
      sorted(["new.jpg", os.path.join("Images", "Photos", "old.jpg")]) in groups, groups)
check("#88 groups of only sorted files are not reported", len(groups) == 2, groups)
check("#88 sorted copy listed first",
      all(os.path.dirname(os.path.relpath(g[0], d)) for g in r.duplicate_groups), r.duplicate_groups)
check("#88 note in the log", any("[DUPES]" in n for n in r.notes), r.notes)
check("#88 plans unchanged", sorted(p.source.name for p in r.plans if not p.skipped)
      == ["cv (1).pdf", "new.jpg", "other.pdf", "same_but_sorted_only.txt"],
      [p.source.name for p in r.plans])

# Rule target folders count as sorted too.
rules.save_rules([Rule("inv", True, "name_pattern", "invoice*", "Finance/Invoices")])
(d / "Finance" / "Invoices").mkdir(parents=True)
(d / "Finance" / "Invoices" / "invoice_1.pdf").write_text("invoice bytes")
(d / "invoice_1 (copy).pdf").write_text("invoice bytes")
r = organizer.scan_folder(d)
groups = [sorted(os.path.relpath(p, d) for p in g) for g in r.duplicate_groups]
check("#88 rule folder compared",
      sorted(["invoice_1 (copy).pdf", os.path.join("Finance", "Invoices", "invoice_1.pdf")]) in groups, groups)
rules.save_rules([])

# A recursive scan works as before (sorted folders are skipped).
r = organizer.scan_folder(d, recursive=True)
check("#88 recursive scan unchanged", not any("Documents" in str(p) for g in r.duplicate_groups for p in g),
      r.duplicate_groups)

# ---------- start at login ----------
args = autostart.command_args()
check("autostart command starts minimised", args[-1] == "--minimized" and Path(args[0]).name, args)
entry = autostart.desktop_entry()
check("desktop entry has Exec with main.py or launcher",
      "Exec=" in entry and ("main.py" in entry or "simple-organizer" in entry) and "--minimized" in entry, entry)
check("desktop entry quotes paths with spaces", autostart._desktop_exec(["/a b/py", "--minimized"])
      == '"/a b/py" --minimized')
if sys.platform.startswith("linux"):
    autostart.enable()
    check("linux: desktop file written", autostart.desktop_file().is_file() and autostart.is_enabled())
    autostart.desktop_file().write_text(entry + "Hidden=true\n")
    check("linux: Hidden=true counts as off", not autostart.is_enabled())
    autostart.disable()
    check("linux: desktop file removed", not autostart.desktop_file().exists() and not autostart.is_enabled())
elif sys.platform == "win32":
    # Use a test value name so a real entry of the user is never touched.
    autostart.APP_NAME = "Simple Organizer TEST " + str(os.getpid())
    try:
        autostart.enable()
        check("windows: Run value written", autostart.is_enabled())
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, autostart.APP_NAME)
        check("windows: command is quoted and minimised", value.startswith('"') and value.endswith("--minimized"), value)
        autostart.disable()
        check("windows: Run value removed", not autostart.is_enabled())
        autostart.disable()   # twice is fine
    finally:
        autostart.disable()

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
