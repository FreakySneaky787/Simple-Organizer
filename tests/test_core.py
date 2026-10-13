"""Self-test for the organizer core. Runs against temp folders only."""
import os, sys, tempfile, shutil, subprocess, json, time, threading
from pathlib import Path

BASE = Path(tempfile.mkdtemp(prefix="so_test_"))
os.environ["APPDATA"] = str(BASE / "appdata")
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
sys.path.insert(0, ROOT)

import organizer, rules, config, utils, scheduler
from organizer import scan_folder, organise_files, undo_last_run, list_undo_history, \
    commit_staging, revert_staging, has_staging, find_duplicates
from rules import Rule, save_rules, load_rules, is_safe_target_folder, match_rule, RulesReadError

fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)

assert str(organizer.DATA_DIR).startswith(str(BASE)), organizer.DATA_DIR

# ---------- setup folder ----------
root = BASE / "dl"
root.mkdir()
(root / "photo.jpg").write_bytes(b"A" * 100)
(root / "copy_of_photo.jpg").write_bytes(b"A" * 100)
(root / "report.pdf").write_bytes(b"pdf")
(root / "empty1.txt").write_bytes(b"")
(root / "empty2.txt").write_bytes(b"")
(root / "movie.mp4.crdownload").write_bytes(b"x")
(root / "~$letter.docx").write_bytes(b"x")
(root / "desktop.ini").write_text("[.ShellClassInfo]")
(root / "hiddenattr.txt").write_text("h")
subprocess.run(["attrib", "+h", str(root / "hiddenattr.txt")], check=True)
(root / "archive.tar.gz").write_bytes(b"tgz")
(root / "2024").write_bytes(b"numeric name")
(root / "Images").mkdir()
(root / "Images" / "already.jpg").write_bytes(b"B")

r = scan_folder(root)
names = sorted(p.source.name for p in r.plans)
check("transient/system/hidden files left alone",
      "movie.mp4.crdownload" not in names and "~$letter.docx" not in names
      and "desktop.ini" not in names and "hiddenattr.txt" not in names, names)
check("note about left-alone files", any("left alone" in n for n in r.notes), r.notes)
check("normal files planned", {"photo.jpg", "report.pdf", "archive.tar.gz", "2024"} <= set(names), names)
dup_names = [sorted(p.name for p in g) for g in r.duplicate_groups]
check("real duplicate found", ["copy_of_photo.jpg", "photo.jpg"] in dup_names, dup_names)
check("empty files not duplicates", not any("empty1.txt" in g for g in dup_names), dup_names)
check("total_bytes", r.total_bytes == sum(p.size for p in r.plans if not p.skipped))

# ---------- rules ----------
save_rules([Rule("tgz", True, "extension", "tar.gz", "Backups/Tar"),
            Rule("bad", True, "name_pattern", "report*", "x*y")])
check("rules saved atomically, no .tmp left", not list(rules.RULES_FILE.parent.glob("*.tmp")))
r = scan_folder(root)
plan = {p.source.name: p for p in r.plans}
check("tar.gz rule matches", plan["archive.tar.gz"].category == "Backups/Tar", plan["archive.tar.gz"].category)
check("invalid rule target ignored + warned",
      plan["report.pdf"].category == "Documents" and any("x*y" in e for e in r.errors), r.errors)
for t, ok in [("Work/Reports", True), ("x*y", False), ("CON", False), ("con.txt", False),
              ("name.", False), ("a/../b", False), ("C:\\x", False), ("Console", True)]:
    check(f"is_safe_target_folder({t!r}) == {ok}", is_safe_target_folder(t) == ok)

# RulesReadError: make rules.json unreadable (a directory with that name)
real = rules.RULES_FILE
rules.RULES_FILE = BASE / "rules_dir.json"
rules.RULES_FILE.mkdir()
try:
    load_rules(); check("unreadable rules raise RulesReadError", False)
except RulesReadError:
    check("unreadable rules raise RulesReadError", True)
check("unreadable rules file not moved away", rules.RULES_FILE.exists())
r_err = scan_folder(root)
check("scan stops when rules unreadable", not r_err.plans and r_err.errors, r_err.errors)
rules.RULES_FILE = real
# corrupt JSON -> backup, no overwrite of older backups
real.write_text("{not json")
check("corrupt rules -> []", load_rules() == [])
real.write_text("{not json either")
load_rules()
check("two corrupt backups kept", len(list(real.parent.glob("rules_corrupt_*.json"))) == 2)
save_rules([Rule("tgz", True, "extension", "tar.gz", "Backups/Tar")])

# ---------- organise + undo with created dirs ----------
r = scan_folder(root)
errs = organise_files(r.plans)
check("organise ok", not errs, errs)
check("files moved", (root / "Images" / "photo.jpg").exists() and (root / "Backups" / "Tar" / "archive.tar.gz").exists())
hist = list_undo_history()
run = json.loads(hist[0]["file_path"].read_text())
check("created_dirs recorded", any(d.endswith("Backups") for d in run["created_dirs"]), run.get("created_dirs"))
check("Images (pre-existing) not in created_dirs", not any(d.endswith("Images") for d in run["created_dirs"]))
check("history label is local time", hist[0]["label"][:3].isalpha())

# undo with one failure -> entry kept
real_move = organizer.safe_move
def flaky_move(src, dst):
    if str(src).endswith("report.pdf"):
        raise PermissionError("locked (test)")
    return real_move(src, dst)
organizer.safe_move = flaky_move
errs = undo_last_run()
organizer.safe_move = real_move
check("undo reports failure", len(errs) == 1, errs)
hist2 = list_undo_history()
check("failed move stays in history", len(hist2) == 1 and hist2[0]["move_count"] == 1, hist2)
check("photo restored", (root / "photo.jpg").exists())
check("created empty dirs removed", not (root / "Backups").exists())
check("Images kept (still has files)", (root / "Images").exists())
errs = undo_last_run()
check("retry undo ok", not errs and (root / "report.pdf").exists(), errs)
check("history empty after full undo", list_undo_history() == [])
check("Documents dir removed after retry", not (root / "Documents").exists())

# ---------- staging ----------
r = scan_folder(root)
organise_files(r.plans, staging=True)
check("has_staging true", has_staging())
errs = commit_staging()
check("commit ok", not errs and (root / "Documents" / "report.pdf").exists(), errs)
check("has_staging false after commit", not has_staging())
check("commit wrote history", len(list_undo_history()) == 1)
undo_last_run()
r = scan_folder(root)
organise_files(r.plans, staging=True)
# stale manifest: delete one staged file -> has_staging still true for others
errs = revert_staging()
check("revert ok", not errs and (root / "report.pdf").exists(), errs)
check("manifest removed", not organizer.STAGING_MANIFEST_FILE.exists())
# manifest with only missing files -> has_staging False
organizer._write_staging_manifest("t", [{"src": "a", "dst": str(BASE / "gone"), "final_dst": "b"}])
check("has_staging false for stale manifest", not has_staging())
organizer.STAGING_MANIFEST_FILE.unlink()

# ---------- recursive ----------
rec = BASE / "rec"
(rec / "Projects" / "Images").mkdir(parents=True)
(rec / "Projects" / "Images" / "nested.jpg").write_bytes(b"n")
(rec / "Images").mkdir()
(rec / "Images" / "top.jpg").write_bytes(b"t")
(rec / "repo" / ".git").mkdir(parents=True)
(rec / "repo" / "main.py").write_text("x")
(rec / "proc").mkdir()
(rec / "proc" / "data.csv").write_text("x")
subprocess.run(["cmd", "/c", "mklink", "/J", str(rec / "Projects" / "loop"), str(rec)],
               check=True, capture_output=True)
deep = rec
for i in range(8):
    deep = deep / f"d{i}"
deep.mkdir(parents=True)
(deep / "deep.txt").write_text("d")
r = scan_folder(rec, recursive=True, max_depth=5)
srcs = sorted(str(p.source.relative_to(rec.resolve())) for p in r.plans)
check("nested Images folder is scanned", any("nested.jpg" in s for s in srcs), srcs)
check("top-level Images excluded", not any("top.jpg" in s for s in srcs), srcs)
check("git repo left alone", not any("main.py" in s for s in srcs), srcs)
check("folder named proc scanned", any("data.csv" in s for s in srcs), srcs)
check("junction not followed (no duplicates)", len(srcs) == len(set(p.source.name for p in r.plans)), srcs)
check("depth summary note", any(n.startswith("[DEPTH]") for n in r.notes), r.notes)
check("git note", any("Git repositor" in n for n in r.notes), r.notes)

# protected dir
r = scan_folder(organizer.DATA_DIR)
check("data dir refused", r.errors and "belongs to Simple Organizer" in r.errors[0], r.errors)

# ---------- config ----------
cfg = config.get_settings_path()
cfg.write_text(json.dumps({"max_depth": "x", "dark_mode": "false", "scan_timeout": 12,
                           "window_width": None, "custom": 1}))
s = config.load_settings()
check("config coercion", s["max_depth"] == 5 and s["dark_mode"] is False and
      s["scan_timeout"] == 12.0 and s["window_width"] == 980 and s["custom"] == 1, s)

# ---------- risky folders ----------
check("drive root risky", utils.risky_folder_reason(Path("C:\\")) is not None)
check("Windows dir risky", utils.risky_folder_reason(Path(os.environ["SystemRoot"])) is not None)
check("home risky", utils.risky_folder_reason(Path.home()) is not None)
check("Downloads safe", utils.risky_folder_reason(Path.home() / "Downloads") is None)
check("git repo risky", utils.risky_folder_reason(rec / "repo") is not None)

# ---------- scheduler ----------
calls = []
sch = scheduler.OrganizerScheduler(lambda: calls.append(1))
sch._interval = 1
sch._enabled = True
gen_before = sch._generation
sch.configure(1, True)                    # live timer, new generation
old_gen = sch._generation - 1             # a timer from before configure()
sch._fire(old_gen)                        # stale timer fires
check("stale timer does not run callback", calls == [])
t_before = sch._timer
sch._fire(sch._generation)
check("current timer fires", calls == [1])
check("only one live timer after fire", sch._timer is not t_before and threading.active_count() <= 4)
sch._next_fire = time.monotonic() - 10 * 60   # pretend 10 slots were missed
sch._cancel(); sch._generation -= 1           # keep generation for the test
sch._arm_drift_corrected()
check("missed slots skipped", sch._next_fire > time.monotonic())
sch.stop()

# ---------- trash XDG helper (pure file operations) ----------
os.environ["XDG_DATA_HOME"] = str(BASE / "xdg")
f = BASE / "trash me ä.txt"
f.write_text("t")
organizer._trash_xdg(f.resolve())
info = list((BASE / "xdg" / "Trash" / "info").glob("*.trashinfo"))
check("xdg trashinfo percent-encoded",
      info and "%20" in info[0].read_text() and "%C3%A4" in info[0].read_text())
f.write_text("t2")
organizer._trash_xdg(f.resolve())
check("xdg second file renamed", len(list((BASE / "xdg" / "Trash" / "files").iterdir())) == 2)

subprocess.run(["cmd", "/c", "rmdir", str(rec / "Projects" / "loop")])
shutil.rmtree(BASE, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
