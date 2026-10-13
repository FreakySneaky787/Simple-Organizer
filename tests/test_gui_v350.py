"""GUI tests for v3.5.0. Drives the real app; dialogs are answered by patching or timers."""
import csv, json, os, shutil, sys, tempfile, time
from pathlib import Path

APPDATA = Path(tempfile.mkdtemp(prefix="so350_gui_"))
os.environ["APPDATA"] = str(APPDATA)
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])   # the repository folder
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

# ---------- #65 unreachable saved folder is kept ----------
missing = r"Q:\Unplugged\Photos"
(DATA / "settings.json").write_text(json.dumps({"last_folder": missing, "schedule_enabled": True}))
t0 = time.perf_counter()
import main, organizer, rules
from rules import Rule
app = main.SimpleOrganizerApp()
app.update()
startup = time.perf_counter() - t0
check("title shows v3.5.0", app.title().endswith("v3.5.0"))
check("#72 start (import + window) under 5 s", startup < 5, f"{startup:.2f}s")
check("#65 saved folder kept although missing", str(app._folder) == missing, app._folder)
check("#65 schedule shows paused", app._schedule_status_var.get().startswith("Paused: the folder was not found"),
      app._schedule_status_var.get())
check("#65 log mentions the missing folder", "not available" in app._log_box.get("1.0", "end"))
app._save_settings()
check("#65 last_folder not overwritten", json.loads((DATA / "settings.json").read_text())["last_folder"] == missing)
app._schedule_enabled.set(False); app._on_schedule_toggle()

# ---------- #68 texts ----------
check("#68 status bar mentions tab shortcuts", any("Ctrl+1-4" in str(w.cget("text"))
      for w in app.winfo_children()[-1].winfo_children() if w.winfo_class() == "TLabel"))

# ---------- scan a demo folder ----------
folder = APPDATA / "work"; folder.mkdir()
for name in ("a.pdf", "b.pdf", "c.jpg", "song.mp3", "z.zip"):
    (folder / name).write_text(name)
def scan():
    app._start_scan(confirmed=True)
    pump(app, 30, lambda: app._scan_result is not None and not app._busy_flag)
    pump(app, 0.5)
app._set_folder(folder)
scan()
check("preview filled", len(app._preview_items) == 5, len(app._preview_items))

# ---------- #78 filter and sort ----------
app._filter_var.set("pdf"); pump(app, 0.5)
names = [app._preview_tree.item(i, "values")[0] for i in app._preview_tree.get_children()]
check("#78 filter shows matching rows only", sorted(names) == ["a.pdf", "b.pdf"], names)
check("#78 filter info", app._filter_info_var.get() == "2 of 5 shown", app._filter_info_var.get())
check("#78 filter does not change what is organised", len(app._actionable_plans()) == 5)
app._on_filter_escape(); pump(app, 0.5)
check("#78 Esc clears the filter", len(app._preview_tree.get_children()) == 5)
app._sort_preview("file"); pump(app, 0.3)
names = [app._preview_tree.item(i, "values")[0] for i in app._preview_tree.get_children()]
check("#78 sort ascending", names == sorted(names, key=str.lower), names)
app._sort_preview("file"); pump(app, 0.3)
names = [app._preview_tree.item(i, "values")[0] for i in app._preview_tree.get_children()]
check("#78 sort descending", names == sorted(names, key=str.lower, reverse=True), names)
check("#78 heading shows the direction", "▼" in app._preview_tree.heading("file", "text"))

# ---------- #77 Don't move ----------
by_name = {app._preview_tree.item(i, "values")[0]: i for i in app._preview_tree.get_children()}
app._preview_tree.selection_set([by_name["a.pdf"], by_name["c.jpg"]])
app._toggle_excluded()
check("#77 excluded rows greyed and marked", all("excluded" in app._preview_tree.item(by_name[n], "tags")
      and "not moved" in app._preview_tree.item(by_name[n], "values")[2] for n in ("a.pdf", "c.jpg")))
check("#77 counts follow", len(app._actionable_plans()) == 3 and "2 not moved" in app._summary_var.get(),
      app._summary_var.get())
app._filter_var.set("a.pdf"); pump(app, 0.5); app._filter_var.set(""); pump(app, 0.5)
check("#77 exclusion survives filtering", len(app._actionable_plans()) == 3)
by_name = {app._preview_tree.item(i, "values")[0]: i for i in app._preview_tree.get_children()}
app._preview_tree.selection_set([by_name["c.jpg"]]); app._toggle_excluded()
check("#77 move again", len(app._actionable_plans()) == 4)
asked = {}
real_ask = main._askyesno
def ask(**k):
    asked.update(k); return True
main._askyesno = ask
app._confirm_and_organize()
pump(app, 10, lambda: not app._busy_flag); pump(app, 0.5)
check("#77 confirmation counts only moved files", "Move 4 file(s)" in asked.get("message", ""), asked.get("message"))
check("#77 excluded file stays", (folder / "a.pdf").exists() and (folder / "Documents" / "b.pdf").exists())

# ---------- #74 undo names the run and folder ----------
asked.clear()
app._confirm_and_undo()
pump(app, 10, lambda: not app._busy_flag); pump(app, 0.5)
check("#74 undo question names the folder", f"Folder: {folder.resolve()}" in asked.get("message", ""),
      asked.get("message"))
check("#74 undo restored the files", (folder / "b.pdf").exists())
dlg = main._HistoryDialog(app); pump(app, 0.3)
check("#74 history dialog shows folders", not dlg._entries or dlg._tree.item("0", "values")[2] != "", )
dlg.destroy()
main._askyesno = real_ask

# ---------- #75 offer to pause Auto-organize after an undo ----------
scan()
main._askyesno = lambda **k: True
app._confirm_and_organize(); pump(app, 10, lambda: not app._busy_flag)
app._schedule_enabled.set(True); app._on_schedule_toggle()
questions = []
def ask2(**k):
    questions.append(k.get("title")); return True
main._askyesno = ask2
app._confirm_and_undo()
pump(app, 10, lambda: not app._busy_flag); pump(app, 1)
check("#75 pause offered after undo", "Pause Auto-organize?" in questions, questions)
check("#75 Auto-organize paused", not app._schedule_enabled.get() and not app._scheduler.enabled)
main._askyesno = real_ask

# ---------- #73 changed options invalidate the plan ----------
scan()
check("plan present", app._scan_result is not None)
app._use_subcats.set(True); app._on_subcats_toggle()
check("#73 sub-categories toggle clears the plan", app._scan_result is None and not app._actionable_plans())
check("#73 status asks for a new scan", "press Scan" in app._status_var.get())
scan()
app._persist_rules([Rule("x", True, "extension", "zip", "Zips")])
check("#73 rule change clears the plan", app._scan_result is None)
rules.RULES_FILE.unlink()
scan()
app._max_depth.set(3); app._max_depth_spin._nudge(0)
check("#73 limits do not matter without recursion", app._scan_result is not None)
app._recursive.set(True); app._on_scan_option_changed()
check("#73 recursion toggle clears the plan", app._scan_result is None)
app._recursive.set(False); app._on_scan_option_changed()
app._use_subcats.set(False); app._on_subcats_toggle()

# ---------- #76 shortcuts ----------
app.focus_force(); pump(app, 0.2)
for n, idx in ((2, app._dup_tab_idx), (3, app._log_tab_idx), (1, app._preview_tab_idx)):
    app._preview_tree.event_generate(f"<Control-Key-{n}>"); pump(app, 0.1)
    check(f"#76 Ctrl+{n} selects its tab", app._notebook.index("current") == idx, app._notebook.index("current"))
app._preview_tree.event_generate("<Control-f>"); pump(app, 0.1)
check("#76 Ctrl+F focuses the filter", app.focus_get() is app._filter_entry)
started = []
real_scan = app._start_scan
app._start_scan = lambda *a, **k: started.append(1)
app._bind_shortcuts()
app._preview_tree.event_generate("<F5>"); pump(app, 0.1)
app._start_scan = real_scan
app._bind_shortcuts()
check("#76 F5 scans", started == [1], started)

# ---------- #67 context menu ----------
scan()
popped = {}
class FakeMenu:
    def __init__(self): self.labels = []
    def add_command(self, label, command=None): self.labels.append(label)
    def add_separator(self): pass
    def entryconfigure(self, *a, **k): pass
    def tk_popup(self, *a): popped["labels"] = self.labels
    def grab_release(self): pass
real_menu = app._menu
app._menu = FakeMenu
first = app._preview_tree.get_children()[0]
app._preview_tree.update_idletasks()
x, y, w, h = app._preview_tree.bbox(first)
class Ev: pass
ev = Ev(); ev.x, ev.y, ev.x_root, ev.y_root = x + 5, y + 5, 0, 0
app._on_preview_context(ev)
app._menu = real_menu
labels = popped.get("labels", [])
check("#67 no 'Open destination folder' before the folder exists", "Open destination folder" not in labels, labels)
check("#77 context menu offers Don't move", "Don't move" in labels, labels)

# ---------- #80 export ----------
target = APPDATA / "export.csv"
real_save = main.filedialog.asksaveasfilename
main.filedialog.asksaveasfilename = lambda **k: str(target)
app._toggle_excluded()          # first row: don't move
app._export_csv()
main.filedialog.asksaveasfilename = real_save
raw = target.read_bytes()
sep = main.csv_delimiter()
rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=sep))
check("#80 file starts with a BOM", raw.startswith(b"\xef\xbb\xbf"))
check("#80 header", rows[0] == ["Status", "File", "Category", "Source folder", "Destination folder", "Size (bytes)"], rows[0])
check("#80 one row per planned file", len(rows) - 1 == len(app._scan_result.plans), len(rows))
check("#80 status values", {r[0] for r in rows[1:]} == {"move", "don't move"}, {r[0] for r in rows[1:]})

# ---------- pass 2: rules changed during a scan, all files excluded ----------
app._start_scan(confirmed=True)
app._persist_rules([Rule("y", True, "extension", "mp3", "Audio")])
pump(app, 30, lambda: not app._busy_flag); pump(app, 0.3)
check("pass2 scan result discarded when rules changed meanwhile", app._scan_result is None
      and "rules changed during the scan" in app._status_var.get(), app._status_var.get())
rules.RULES_FILE.unlink()
scan()
for p in app._scan_result.plans:
    p.excluded = True
infos = []
real_info = main._showinfo
main._showinfo = lambda title, message, parent: infos.append(message)
app._confirm_and_organize()
main._showinfo = real_info
check("pass2 all excluded: clear message", infos and "Don't move" in infos[0], infos)
for p in app._scan_result.plans:
    p.excluded = False

# ---------- #79 rule dialog with several conditions ----------
dlg = main._RuleDialog(app)
dlg._name_var.set("Old PDFs"); dlg._folder_var.set("Archive")
dlg._rows[0]["type"].set("extension"); dlg._rows[0]["value"].set("*.PDF")
dlg._add_condition()
dlg._rows[1]["type"].set("older_than_days"); dlg._rows[1]["value"].set("365")
dlg._ok(); app.update()
res = dlg.result
check("#79 dialog builds a rule with two conditions", res is not None and res.conditions() ==
      [("extension", "pdf"), ("older_than_days", "365")], res)
dlg = main._RuleDialog(app, res); app.update()
check("#79 editing shows both conditions", len(dlg._rows) == 2)
dlg._remove_row(dlg._rows[1]); app.update()
check("#79 a condition can be removed", len(dlg._rows) == 1)
for _ in range(10):
    dlg._add_condition()
check("#79 at most 5 conditions", len(dlg._rows) == 5 and str(dlg._add_btn.cget("state")) == "disabled")
dlg._rows[4]["value"].set("abc"); dlg._rows[4]["type"].set("min_size_mb")
for r in dlg._rows[1:4]:
    r["value"].set("1")
app.after(300, lambda: [o for o in app._overlays if o is not dlg][0]._accept())
dlg._ok(); app.update()
check("#79 invalid extra condition is refused", dlg.result is None and dlg.winfo_exists())
dlg.destroy()
app._persist_rules([res])
app._refresh_rules_tree()
row = app._rules_tree.item(app._rules_tree.get_children()[0], "values")
check("#79 Rules tab shows all conditions", "extension pdf" in row[2] and "older_than_days 365" in row[2], row)
rules.RULES_FILE.unlink()

app.destroy()
shutil.rmtree(APPDATA, ignore_errors=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
