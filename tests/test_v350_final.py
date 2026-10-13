"""Core tests for the last review before v3.5.0: rules.json stays readable for older versions."""
import json, os, shutil, sys, tempfile
from dataclasses import dataclass
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so350f_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

fails: list[str] = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

import rules
from rules import Rule

simple = Rule("Logs", True, "extension", "log", "Logs")
double = Rule("Old PDFs", True, "extension", "pdf", "Archive",
              more_conditions=[{"type": "older_than_days", "value": "365"}])

rules.save_rules([simple])
raw = json.loads(rules.RULES_FILE.read_text(encoding="utf-8"))
check("single-condition rule is saved without more_conditions", "more_conditions" not in raw[0], raw[0])

# How v3.4.0 and older read rules.json: Rule(**entry) -- an unknown key loses every rule.
@dataclass
class OldRule:
    name: str
    enabled: bool
    condition_type: str
    condition_value: str
    target_folder: str
try:
    old = [OldRule(**r) for r in raw]
except TypeError:
    old = []
check("v3.4.0 still reads the rules of 3.5.0", len(old) == 1 and old[0].target_folder == "Logs")

rules.save_rules([simple, double])
raw = json.loads(rules.RULES_FILE.read_text(encoding="utf-8"))
check("several conditions are still saved", "more_conditions" not in raw[0]
      and raw[1]["more_conditions"] == [{"type": "older_than_days", "value": "365"}], raw)
check("round trip", rules.load_rules() == [simple, double])

shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
