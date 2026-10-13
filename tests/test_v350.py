"""Tests for v3.5.0 (issues #65 - #80), core logic. Temp folders and a temp APPDATA only."""
import csv, json, os, shutil, sys, tempfile, time
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="so350_"))
os.environ["APPDATA"] = str(BASE / "appdata")
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

import utils, organizer, rules
from organizer import scan_folder, organise_files, commit_staging
from rules import Rule

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

def fresh(name: str) -> Path:
    d = BASE / name
    d.mkdir()
    return d

# ---------- #66 file gone after the scan ----------
d = fresh("x66")
(d / "report.pdf").write_text("x")
plans = scan_folder(d).plans
(d / "report.pdf").unlink()
logs: list[str] = []
errs = organise_files(plans, log_callback=logs.append)
check("#66 missing file is not an error", errs == [], errs)
check("#66 missing file is logged as skipped", any(l.startswith("[SKIP]") and "no longer exists" in l for l in logs), logs)
check("#66 no empty category folder left", not (d / "Documents").exists())
check("#66 no history run for a run that moved nothing", not organizer.has_last_run())

d = fresh("x66b")
(d / "a.pdf").write_text("x"); (d / "b.mp3").write_text("y")
plans = scan_folder(d).plans
real_move = organizer.safe_move
def fail_pdf(src, dst):
    if src.suffix == ".pdf":
        raise PermissionError(13, "Access is denied", str(src), None, str(dst))
    return real_move(src, dst)
organizer.safe_move = fail_pdf
try:
    errs = organise_files(plans)
finally:
    organizer.safe_move = real_move
check("#66 empty folder of a failed move removed", not (d / "Documents").exists() and (d / "Music" / "b.mp3").exists())
check("#66 error text without doubled paths", len(errs) == 1 and "\\\\" not in errs[0] and "Access is denied" in errs[0], errs)
run = json.loads(organizer._newest_run_file().read_text(encoding="utf-8"))
check("#66 history lists only folders that exist", all("Documents" not in c for c in run["created_dirs"]), run["created_dirs"])

# ---------- #74 folder of every run ----------
check("#74 run records its folder", run.get("folders") == [str(d.resolve())], run.get("folders"))
entry = organizer.list_undo_history()[0]
check("#74 history entry has the folder", entry["folder"] == str(d.resolve()), entry["folder"])
legacy = {"timestamp": "2026-01-01T00:00:00+00:00",
          "moves": [{"src": str(d / "x.txt"), "dst": str(d / "Documents" / "x.txt")},
                    {"src": str(d / "y.txt"), "dst": str(d / "Documents" / "y.txt")}]}
check("#74 folder derived for old runs", organizer._run_folder(legacy) == str(d), organizer._run_folder(legacy))
d2 = fresh("x74s")
(d2 / "s.zip").write_text("z")
organise_files(scan_folder(d2).plans, staging=True)
commit_staging()
check("#74 committed run records its folder", organizer.list_undo_history()[0]["folder"] == str(d2.resolve()))

# ---------- #77 excluded plans are not moved ----------
d = fresh("x77")
(d / "keep.pdf").write_text("k"); (d / "move.pdf").write_text("m")
plans = scan_folder(d).plans
for p in plans:
    p.excluded = p.source.name == "keep.pdf"
organise_files(plans)
check("#77 excluded file stays", (d / "keep.pdf").exists())
check("#77 other file moved", (d / "Documents" / "move.pdf").exists())

# ---------- #79 rules with several conditions ----------
old = d / "old.pdf"; old.write_text("o")
past = time.time() - 400 * 86400
os.utime(old, (past, past))
new = d / "new.pdf"; new.write_text("n")
r = Rule("Old PDFs", True, "extension", "pdf", "Archive",
         more_conditions=[{"type": "older_than_days", "value": "365"}])
check("#79 all conditions match", rules.match_rule(old, r))
check("#79 one condition fails -> no match", not rules.match_rule(new, r))
check("#79 describe", r.describe() == "extension pdf  +  older_than_days 365", r.describe())
rules.RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
rules.save_rules([r, Rule("Logs", True, "extension", "log", "Logs")])
raw = json.loads(rules.RULES_FILE.read_text(encoding="utf-8"))
check("#79 first condition keeps the old fields", raw[0]["condition_type"] == "extension"
      and raw[0]["condition_value"] == "pdf" and raw[0]["more_conditions"][0]["value"] == "365")
loaded = rules.load_rules()
check("#79 round trip", loaded[0] == r and loaded[1].more_conditions == [])
raw[0]["more_conditions"] = [{"type": "older_than_days"}]   # damaged entry
rules.RULES_FILE.write_text(json.dumps(raw), encoding="utf-8")
check("#79 damaged extra condition drops the rule instead of widening it",
      [x.name for x in rules.load_rules()] == ["Logs"])
raw[0].pop("more_conditions")   # rules.json of v3.4.x
rules.RULES_FILE.write_text(json.dumps(raw), encoding="utf-8")
check("#79 rules.json of older versions still loads", rules.load_rules()[0].more_conditions == [])
check("#79 condition_problem", rules.condition_problem("extension", "pdf, docx") and
      rules.condition_problem("min_size_mb", "-1") and rules.condition_problem("min_size_mb", "inf")
      and rules.condition_problem("name_pattern", "  ") and rules.condition_problem("bogus", "1")
      and rules.condition_problem("older_than_days", "365") is None)
check("#79 normalize", rules.normalize_condition_value("extension", " *.PDF") == "pdf"
      and rules.normalize_condition_value("name_pattern", " *Invoice* ") == "*Invoice*")
d = fresh("x79")
(d / "old.pdf").write_text("o"); os.utime(d / "old.pdf", (past, past)); (d / "new.pdf").write_text("n")
rules.save_rules([r])
dest = {p.source.name: p.category for p in scan_folder(d).plans}
check("#79 scan uses all conditions", dest == {"old.pdf": "Archive", "new.pdf": "Documents"}, dest)
rules.RULES_FILE.unlink()

# ---------- pass 2: commit leaves no empty folder, newest entry only ----------
d = fresh("x66c")
(d / "c.pdf").write_text("c")
organise_files(scan_folder(d).plans, staging=True)
real_move = organizer.safe_move
def fail_commit(src, dst):
    if "staging" in str(src):
        raise PermissionError(13, "Access is denied")
    return real_move(src, dst)
organizer.safe_move = fail_commit
try:
    errs = commit_staging()
finally:
    organizer.safe_move = real_move
check("pass2 failed commit leaves no empty folder", errs and not (d / "Documents").exists())
check("pass2 failed commit keeps the file staged", organizer.has_staging())
organizer.revert_staging()
check("pass2 list_undo_history(limit=1)", len(organizer.list_undo_history(limit=1)) == 1
      and organizer.list_undo_history(limit=1)[0]["id"] == organizer.list_undo_history()[0]["id"])

# ---------- #80 CSV delimiter ----------
sep = utils.csv_delimiter()
check("#80 delimiter is one character", isinstance(sep, str) and len(sep) == 1, sep)

shutil.rmtree(BASE, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
