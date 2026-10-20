"""Regression test for #100: a file named like its category folder must not be left as "<name>.organizing"."""
import os, sys, tempfile, shutil
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so_issue100_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import organizer

d = APPDATA.joinpath("w")
d.mkdir(parents=True)
d = d.resolve()
(d / "Others").write_text("file named like its category folder")

r = organizer.scan_folder(d)
check("#100 scan finds the file", len(r.plans) == 1 and not r.errors, r.errors)

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
check("#100 file is back under its own name", (d / "Others").is_file(), names)
check("#100 no folder left in the way", not (d / "Others").is_dir(), names)
check("#100 no .organizing leftover", not any(n.endswith(".organizing") for n in names), names)
check("#100 failure is reported", bool(errors) or any("Others" in m for m in logged), (errors, logged))

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
