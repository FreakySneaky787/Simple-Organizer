"""Core tests for v3.5.3: fixes for #90, #102 and #104."""
import json, os, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so353_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import organizer, rules
from rules import Rule

def fresh(*parts):
    d = APPDATA.joinpath("w", *parts)
    d.mkdir(parents=True)
    return d.resolve()

# ---------- #104 file named like a nested rule target ----------
d = fresh("nested")
(d / "Work").write_text("file named like the first folder of its rule target")
rules.save_rules([Rule("work", True, "name_pattern", "Work", "Work/Archive")])
r = organizer.scan_folder(d)
plans = [p for p in r.plans if not p.skipped]
check("#104 scan plans the file into Work/Archive",
      len(plans) == 1 and plans[0].destination.parent == d / "Work" / "Archive",
      [(p.source, p.destination) for p in r.plans])

real_move = organizer.safe_move
def failing_move(src, dst):
    raise PermissionError(13, "locked by another program")
organizer.safe_move = failing_move
logged: list[str] = []
try:
    errors = organizer.organise_files(r.plans, log_callback=logged.append)
finally:
    organizer.safe_move = real_move
names = sorted(os.listdir(d))
check("#104 file is back under its own name", (d / "Work").is_file(), names)
check("#104 no .organizing leftover", not any(n.endswith(".organizing") for n in names), names)
check("#104 no folder left behind", names == ["Work"], names)
check("#104 failure is reported", bool(errors), (errors, logged))

# The move itself still works.
r = organizer.scan_folder(d)
errors = organizer.organise_files(r.plans)
check("#104 normal move works", not errors and (d / "Work" / "Archive" / "Work").is_file(),
      sorted(str(p.relative_to(d)) for p in d.rglob("*")))
check("#104 undo restores it", not organizer.undo_last_run() and (d / "Work").is_file()
      and sorted(os.listdir(d)) == ["Work"], sorted(os.listdir(d)))
rules.save_rules([])

# ---------- #102 undo of a file named like a category folder in other case ----------
for name, other in (("others", "z.zzz"), ("documents", "a.pdf"), ("Others", "y.zzz")):
    d = fresh("case_" + name + "_" + other.replace(".", "_"))
    (d / name).write_text(name)
    (d / other).write_text(other)
    r = organizer.scan_folder(d)
    errors = organizer.organise_files(r.plans)
    check(f"#102 {name} organised", not errors and not (d / name).is_file(), errors)
    logged = []
    errors = organizer.undo_last_run(log_callback=logged.append)
    names = sorted(os.listdir(d))
    check(f"#102 undo gives {name} its own name back", not errors and names == sorted([name, other]),
          (names, logged))

# ---------- #90 the history shows the year of older runs ----------
for f in organizer.HISTORY_DIR.glob("*.json"):
    f.unlink()
d = fresh("history")
(d / "a.pdf").write_text("a")
organizer.organise_files(organizer.scan_folder(d).plans)
entry = organizer.list_undo_history(limit=1)[0]
year = str(datetime.now().year)
check("#90 this year's run has no year", year not in entry["label"], entry["label"])
run = next(organizer.HISTORY_DIR.glob("*.json"))
data = json.loads(run.read_text(encoding="utf-8"))
old = datetime.now(timezone.utc) - timedelta(days=400)
data["timestamp"] = old.isoformat()
run.write_text(json.dumps(data), encoding="utf-8")
entry = organizer.list_undo_history(limit=1)[0]
check("#90 an older run shows its year", str(old.astimezone().year) in entry["label"], entry["label"])

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
