"""Core tests for v3.5.2: fixes for #91 - #99."""
import csv, io, os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so352_"))
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

def fresh(*parts):
    d = APPDATA.joinpath("w", *parts)
    d.mkdir(parents=True)
    return d.resolve()

def plans_by_name(result):
    return {p.source.name: p for p in result.plans}

# ---------- #91 two files named like category folders ----------
d = fresh("blockers")
for name in ("Documents", "Others", "a.pdf"):
    (d / name).write_text(name)
r = organizer.scan_folder(d)
check("#91 scan without problems", not r.errors and len(r.plans) == 3, r.errors)
errors = organizer.organise_files(r.plans)
check("#91 organise without errors", not errors, errors)
check("#91 every file in place", (d / "Others" / "Others").is_file() and (d / "Others" / "Documents").is_file()
      and (d / "Documents" / "a.pdf").is_file(), sorted(os.listdir(d)))
check("#91 undo restores all three", not organizer.undo_last_run()
      and all((d / n).is_file() for n in ("Documents", "Others", "a.pdf")), sorted(os.listdir(d)))

# ---------- #92 blocker set to "Don't move" ----------
d = fresh("excluded")
(d / "Documents").write_text("x"); (d / "a.pdf").write_text("a"); (d / "b.pdf").write_text("b")
(d / "c.jpg").write_bytes(b"c")
r = organizer.scan_folder(d)
plans_by_name(r)["Documents"].excluded = True
logged = []
errors = organizer.organise_files(r.plans, log_callback=logged.append)
check("#92 one clear error for the folder", len(errors) == 1 and "2 files not moved" in errors[0]
      and "'Documents' blocks the folder 'Documents'" in errors[0], errors)
check("#92 no raw OS error", not any("Could not move" in m for m in logged), logged)
check("#92 other categories still organised", (d / "Images" / "c.jpg").is_file())
check("#92 PDFs and blocker untouched", all((d / n).is_file() for n in ("Documents", "a.pdf", "b.pdf")))

d = fresh("excluded_staging")
(d / "a.pdf").write_text("a")
r = organizer.scan_folder(d)
organizer.organise_files(r.plans, staging=True)
(d / "Documents").write_text("appeared while staged")
errors = organizer.commit_staging()
check("#92 commit: clear error, file stays staged", len(errors) == 1 and "blocks the folder" in errors[0]
      and organizer.has_staging(), errors)
(d / "Documents").unlink()
check("#92 commit works once the file is gone", not organizer.commit_staging()
      and (d / "Documents" / "a.pdf").is_file())

# ---------- #93 scanned folder named like a rule target ----------
d = fresh("p93", "New")
(d / "x.txt").write_text("x")
rules.save_rules([Rule("new", True, "newer_than_days", "7", "New")])
r = organizer.scan_folder(d)
p = plans_by_name(r)["x.txt"]
check("#93 file already in place", p.skipped and p.destination == d / "x.txt", p.destination)
d = fresh("p93", "Archive", "Old")
(d / "o.pdf").write_text("o")
rules.save_rules([Rule("old", True, "extension", "pdf", "Archive/Old")])
p = plans_by_name(organizer.scan_folder(d))["o.pdf"]
check("#93 nested rule target", p.skipped, p.destination)
d = fresh("p93", "Other")
(d / "x.txt").write_text("x")
rules.save_rules([Rule("new", True, "newer_than_days", "7", "New")])
p = plans_by_name(organizer.scan_folder(d))["x.txt"]
check("#93 other folders still use the rule", p.destination == d / "New" / "x.txt", p.destination)
rules.save_rules([])

# ---------- #94 category folder in other case ----------
d = fresh("p94")
(d / "images").mkdir()
(d / "images" / "a.jpg").write_text("j"); (d / "images" / "b.pdf").write_text("p")
names = {p.source.name for p in organizer.scan_folder(d, recursive=True).plans}
if sys.platform == "win32":
    check("#94 'images' skipped like 'Images' on Windows", "b.pdf" not in names, names)
else:
    check("#94 'images' is an ordinary folder on Linux", "b.pdf" in names, names)

# ---------- #95 conflict names keep .tar.gz ----------
d = fresh("p95")
(d / "backup.tar.gz").write_text("x"); (d / "notes.txt").write_text("x"); (d / ".bashrc").write_text("x")
check("#95 .tar.gz", utils.resolve_conflict(d / "backup.tar.gz").name == "backup_1.tar.gz")
check("#95 plain extension unchanged", utils.resolve_conflict(d / "notes.txt").name == "notes_1.txt")
check("#95 dot file", utils.resolve_conflict(d / ".bashrc").name == ".bashrc_1")
check("#95 split_name", utils.split_name("a.TAR.XZ") == ("a", ".TAR.XZ") and utils.split_name(".tar.gz") == (".tar", ".gz"),
      (utils.split_name("a.TAR.XZ"), utils.split_name(".tar.gz")))

# ---------- #96 filename patterns ----------
m = rules.name_pattern_matches
check("#96 brackets match themselves", m("[Draft] report.docx", "[draft]*"))
check("#96 no character sets", not m("d.txt", "[draft]*"))
check("#96 * and ? still work", m("report.LOG", "*.log") and m("a1.txt", "a?.txt") and not m("a12.txt", "a?.txt"))
check("#96 other regex characters are literal", m("a+b (1).txt", "a+b (1).txt") and not m("aab (1).txt", "a+b (1).txt"))

# ---------- #97 CSV cells for names that are not valid UTF-8 ----------
import main
bad = "caf\udce9.txt"
cell = main._csv_text(bad)
buf = io.StringIO()
csv.writer(buf).writerow([cell])
check("#97 cell can be written as UTF-8", buf.getvalue().encode("utf-8") and cell == "caf�.txt", repr(cell))
check("#97 lone UTF-16 surrogate", main._csv_text("x\ud800.txt").encode("utf-8") is not None)
check("#97 normal names unchanged", main._csv_text("Grüße.txt") == "Grüße.txt" and main._csv_text("=1.txt") == "'=1.txt")

# ---------- #98 trashinfo path ----------
try:
    path = organizer._trash_path("/home/u/" + bad)
    ok = path == "/home/u/caf%E9.txt" if os.name != "nt" else "%" in path
except UnicodeEncodeError:
    ok = False
check("#98 trashinfo Path for a name that is not valid UTF-8", ok)
check("#98 normal path", organizer._trash_path("/home/u/my file ä.txt") == "/home/u/my%20file%20%C3%A4.txt")
trash = APPDATA / "Trash"
d = fresh("p98")
(d / "a.tar.gz").write_text("1")
(trash / "files").mkdir(parents=True); (trash / "info").mkdir()
(trash / "files" / "a.tar.gz").write_text("old")
organizer._trash_into(d / "a.tar.gz", trash, "a.tar.gz")
check("#95 trash name keeps .tar.gz", (trash / "files" / "a_1.tar.gz").is_file(), os.listdir(trash / "files"))

# ---------- #99 undo keeps track of a parked file ----------
d = fresh("p99")
(d / "Others").write_text("o")
organizer.organise_files(organizer.scan_folder(d).plans)
real_move = organizer.safe_move
def failing_move(src, dst):
    if src.name.endswith(".organizing"):
        raise PermissionError(13, "locked by another program")
    return real_move(src, dst)
organizer.safe_move = failing_move
errors = organizer.undo_last_run()
organizer.safe_move = real_move
check("#99 undo reports the error", len(errors) == 1, errors)
check("#99 file back where the history expects it", (d / "Others" / "Others").is_file()
      and not list(d.glob("*.organizing")), sorted(os.listdir(d)))
check("#99 second undo restores it", not organizer.undo_last_run() and (d / "Others").is_file(),
      sorted(os.listdir(d)))

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
