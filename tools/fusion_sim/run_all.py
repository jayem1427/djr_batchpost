#!/usr/bin/env python3
"""
Run the add-in end to end against a behavioural fake of Fusion's API.

    python tools/fusion_sim/run_all.py

Builds the release zip, unzips it into a fresh temp folder for each
simulation (they write settings / remembered-post files next to the code),
and runs them in isolated interpreters (-I) so nothing from the repo leaks in.
These complement the unit tests: they exercise start/stop, toolbar and
right-click wiring, NC Program creation, posting and file output.
"""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> int:
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "build_release.py")],
                         capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
    failed = 0
    for sim in ("sim_core.py", "sim_one_click.py"):
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(out).extractall(tmp)
            r = subprocess.run([sys.executable, "-I", str(HERE / sim), str(Path(tmp) / "djr_batchpost")],
                               capture_output=True, text=True)
            last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
            ok = r.returncode == 0 and "PASSED" in last
            print(f"{'ok  ' if ok else 'FAIL'} {sim}: {last}")
            if not ok:
                failed += 1
                print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
