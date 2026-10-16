"""Core tests for v3.5.1: fixes for #81, #83, #84, #85, #86 (#82 is in test_gui_v351.py)."""
import json, os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so351_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import organizer, rules, utils
from rules import Rule

def fresh(name):
    d = APPDATA / name
    d.mkdir()
    return d.resolve()

def plans_by_name(result):
    return {p.source.name: p for p in result.plans}

# ---------- #83 atomic_write_text flushes the data ----------
synced = []
real_fsync = os.fsync
os.fsync = lambda fd: (synced.append(fd), real_fsync(fd))[1]
target = APPDATA / "x.json"
utils.atomic_write_text(target, "hello")
os.fsync = real_fsync
check("#83 file written", target.read_text(encoding="utf-8") == "hello")
check("#83 fsync called before the rename", len(synced) >= 1, synced)
check("#83 no .tmp left", not (APPDATA / "x.json.tmp").exists())

# ---------- #86 kept copy changed with the same size ----------
d = fresh("dups")
keep, dup = d / "keep.txt", d / "dup.txt"
keep.write_text("aaaa"); dup.write_text("aaaa")
check("#86 identical copy remains", organizer._copy_remains(dup, [keep]))
keep.write_text("bbbb")
check("#86 same size but other content is not a copy", not organizer._copy_remains(dup, [keep]))
errors, trashed = organizer.trash_files([dup], keep={dup: [keep]})
check("#86 duplicate left in place", dup.exists() and trashed == 0 and errors, errors)
link = d / "link.txt"
try:
    os.link(dup, link)
    check("#86 a hard link is not a second copy", not organizer._copy_remains(dup, [link]))
except OSError:
    pass

# ---------- #81 file named like a category folder ----------
d = fresh("blocker")
(d / "Others").write_text("no extension 1")
(d / "README").write_text("no extension 2")
r = organizer.scan_folder(d)
by = plans_by_name(r)
check("#81 no blocking error", not r.errors, r.errors)
check("#81 both files planned", set(by) == {"Others", "README"}, list(by))
errors = organizer.organise_files(r.plans)
check("#81 organise without errors", not errors, errors)
check("#81 files in Others/", (d / "Others" / "Others").is_file() and (d / "Others" / "README").is_file(),
      os.listdir(d))
organizer.undo_last_run()
check("#81 undo restores the file names", (d / "Others").is_file() and (d / "README").is_file(),
      os.listdir(d))

d = fresh("blocker2")
(d / "Documents").write_text("no extension")
(d / "a.pdf").write_text("pdf")
r = organizer.scan_folder(d)
check("#81 'Documents' file does not block PDFs", not r.errors and len(r.plans) == 2, r.errors)
errors = organizer.organise_files(r.plans)
check("#81 PDF and blocker moved", not errors and (d / "Documents" / "a.pdf").is_file()
      and (d / "Others" / "Documents").is_file(), errors)
organizer.undo_last_run()
check("#81 undo puts the 'Documents' file back", (d / "Documents").is_file() and (d / "a.pdf").is_file(),
      os.listdir(d))

d = fresh("blocker3")
(d / "Documents").write_text("no extension")
(d / "a.pdf").write_text("pdf")
(d / "x.part").write_text("download in progress")   # left alone, so it really blocks
rules.save_rules([Rule("Keep", True, "name_pattern", "Documents", "x.part")])
r = organizer.scan_folder(d)
rules.save_rules([])
check("#81 a blocker that cannot move away still blocks", any("blocks the folder" in e for e in r.errors)
      and "a.pdf" not in plans_by_name(r), r.errors)

# ---------- #84 scanned folder named like a category ----------
d = fresh("Images")
(d / "a.jpg").write_text("jpg")
(d / "b.pdf").write_text("pdf")
r = organizer.scan_folder(d)
by = plans_by_name(r)
check("#84 jpg already in place", by["a.jpg"].skipped and by["a.jpg"].destination == d / "a.jpg",
      by["a.jpg"].destination)
check("#84 other categories still sorted", by["b.pdf"].destination == d / "Documents" / "b.pdf")
r = organizer.scan_folder(d, use_subcategories=True)
dest = plans_by_name(r)["a.jpg"].destination
check("#84 sub-category below the folder, not Images/Images", "Images" not in dest.relative_to(d).parts, dest)

# ---------- #85 recursive scans skip rule target folders ----------
d = fresh("rulefolders")
(d / "New").mkdir()
old = d / "New" / "old.txt"
old.write_text("old")
t = time.time() - 30 * 86400
os.utime(old, (t, t))
(d / "Sub").mkdir()
(d / "Sub" / "x.txt").write_text("x")
rules.save_rules([Rule("New", True, "newer_than_days", "7", "New")])
r = organizer.scan_folder(d, recursive=True)
names = {p.source.name for p in r.plans}
check("#85 file in rule folder not re-sorted", "old.txt" not in names, names)
check("#85 other sub-folders still scanned", "x.txt" in names, names)
rules.save_rules([Rule("New", False, "newer_than_days", "7", "New")])
r = organizer.scan_folder(d, recursive=True)
check("#85 disabled rule: folder scanned again", "old.txt" in {p.source.name for p in r.plans})
rules.save_rules([])

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
