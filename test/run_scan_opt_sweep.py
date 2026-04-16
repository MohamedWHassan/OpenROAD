#!/usr/bin/env python3
"""
Sweep aes_sky130hd.tcl (via flow.tcl) across floorplan areas. For each area,
two runs are performed:
  - baseline:  no scan_opt
  - scan_opt:  with scan_opt enabled

The die is always square; DIE_SIZE sets the side length in um. Core margins are
fixed at 30um (left/bottom) and 230um (right/top), matching the aes defaults.

Usage (from the test/ directory):
    python3 run_scan_opt_sweep.py [--areas 1800 2000 2200] \\
                                  [--output-dir sweep_results]

Outputs are organised as:
    <output-dir>/area_<size>/baseline/run.log
    <output-dir>/area_<size>/scan_opt/run.log

Scan chain wirelength is printed in each run.log (TOTAL_WIRE_LENGTH=1).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# --- Configuration -----------------------------------------------------------
OPENROAD_BIN = Path("../../install/OpenROAD/bin/openroad")
TCL_SCRIPT = Path("aes_sky130hd.tcl")
DEFAULT_AREAS = [2000]  # die side in um; extend with e.g. [1800, 2000, 2200]
# -----------------------------------------------------------------------------


def run_openroad(env: dict, results_dir: Path, log_path: Path) -> int:
    results_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(OPENROAD_BIN), "-no_init", "-exit", str(TCL_SCRIPT)]
    run_env = os.environ.copy()
    run_env.update(env)
    run_env["RESULTS_DIR"] = str(results_dir)

    print(f"  cmd : {' '.join(cmd)}")
    print(f"  env : {env}")
    print(f"  logs: {log_path}")

    with open(log_path, "w") as log_fh:
        proc = subprocess.run(
            cmd,
            env=run_env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    return proc.returncode


SCENARIOS: list[tuple[str, dict]] = [
    ("baseline", {"TOTAL_WIRE_LENGTH": "1", "USE_SCAN_OPT": "0"}),
    ("scan_opt", {"TOTAL_WIRE_LENGTH": "1", "USE_SCAN_OPT": "1"}),
]


def main():
    parser = argparse.ArgumentParser(description="Sweep scan_opt and floorplan areas")
    parser.add_argument(
        "--areas",
        type=int,
        nargs="+",
        default=DEFAULT_AREAS,
        metavar="UM",
        help="Die side lengths in um to sweep (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("sweep_results"),
        help="Root directory for all run outputs (default: %(default)s)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    if not OPENROAD_BIN.exists():
        sys.exit(f"ERROR: OpenROAD binary not found at {OPENROAD_BIN.resolve()}")
    if not TCL_SCRIPT.exists():
        sys.exit(f"ERROR: TCL script not found at {TCL_SCRIPT.resolve()}")

    output_root = args.output_dir
    print(f"Output root: {output_root.resolve()}\n")

    results = []
    for area in args.areas:
        for label, env in SCENARIOS:
            full_label = f"area_{area}/{label}"
            print(f"{'='*60}")
            print(f"Run: {full_label}")
            run_dir = output_root / f"area_{area}" / label
            log_path = run_dir / "run.log"

            run_env = dict(env)
            run_env["DIE_SIZE"] = str(area)

            rc = run_openroad(run_env, run_dir, log_path)

            odb_path = run_dir / "aes_sky130hd_fill-tcl.db"
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"

            results.append(
                {
                    "label": full_label,
                    "status": status,
                    "odb": str(odb_path) if odb_path.exists() else "NOT FOUND",
                    "log": str(log_path),
                }
            )
            print(f"  status: {status}")
            print(f"  odb   : {results[-1]['odb']}")
            print()

    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    col = max(len(r["label"]) for r in results)
    for r in results:
        print(f"  {r['label']:<{col}}  {r['status']:<20}  {r['odb']}")


if __name__ == "__main__":
    main()
