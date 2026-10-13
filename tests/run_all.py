"""Run every test script in this folder. Exit code 1 if one of them fails.

    python tests/run_all.py            all suites
    python tests/run_all.py gui_v350   only the suites whose name contains "gui_v350"

The suites use temporary folders and a temporary APPDATA only; nothing on
the computer is moved. They are written for Windows (Recycle Bin, junctions,
read-only attributes); the GUI suites open the app window for a moment.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    wanted = sys.argv[1:]
    scripts = [s for s in sorted(HERE.glob("test_*.py"))
               if not wanted or any(w in s.stem for w in wanted)]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    failed: list[str] = []
    for script in scripts:
        start = time.monotonic()
        run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env, cwd=HERE.parent)
        ok = run.returncode == 0 and "ALL PASSED" in run.stdout
        print(f"{'ok  ' if ok else 'FAIL'}  {script.name:<22} {time.monotonic() - start:5.1f}s", flush=True)
        if not ok:
            failed.append(script.name)
            print("\n".join(line for line in run.stdout.splitlines() if not line.startswith("PASS ")))
            print(run.stderr[-4000:])
    print(f"\n{len(scripts) - len(failed)} of {len(scripts)} suites passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
