#!/usr/bin/env python3
"""
Sweep aes_sky130hd.tcl (via flow.tcl) across scan chain max lengths.
For each length, four runs are performed:
  - baseline:               no scan_opt
  - scan_opt_no_cluster:    scan_opt without spatial pre-clustering
  - scan_opt_cluster_only:  Stage A only (k-means clustering, no per-chain
                            local search) — for evaluating clustering
                            quality in isolation
  - scan_opt_with_cluster:  full pipeline (Stage A + Stage B)

MAX_LENGTH sets the scan chain max length passed to set_dft_config.

Each run also emits CSV-formatted chain metrics (HPWL, MST, sum_pairwise)
between the markers '=== chain_metrics ===' and '=== end chain_metrics ===',
collected by flow.tcl via report_chain_metrics.

Usage (from the test/ directory):
    python3 run_scan_opt_sweep.py [--lengths 50 100 200] \\
                                  [--output-dir sweep_results]

Outputs are organised as:
    <output-dir>/length_<n>/baseline/run.log
    <output-dir>/length_<n>/scan_opt_no_cluster/run.log
    <output-dir>/length_<n>/scan_opt_cluster_only/run.log
    <output-dir>/length_<n>/scan_opt_with_cluster/run.log
    <output-dir>/length_<n>/<scenario>/chain_metrics.csv  (extracted)

Scan chain wirelength is printed in each run.log (TOTAL_WIRE_LENGTH=1).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# --- Configuration -----------------------------------------------------------
OPENROAD_BIN = Path("../../install/OpenROAD/bin/openroad")
TCL_SCRIPT = Path("aes_sky130hd.tcl")
DEFAULT_LENGTH = [50]
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
    ("baseline", {
        "TOTAL_WIRE_LENGTH": "1", # doesn't run scan opt at all
        "USE_SCAN_OPT": "0",
        "SPATIAL_CLUSTER": "0",
        "CLUSTER_ONLY": "0",
    }),
    ("scan_opt_no_cluster", { # This runs scan opt with 2-opt/3-opt only
        "TOTAL_WIRE_LENGTH": "1",
        "USE_SCAN_OPT": "1",
        "SPATIAL_CLUSTER": "0",
        "CLUSTER_ONLY": "0",
    }),
    # ("scan_opt_cluster_only", { # This runs scan op with clustering only
    #     "TOTAL_WIRE_LENGTH": "1",
    #     "USE_SCAN_OPT": "1",
    #     "SPATIAL_CLUSTER": "1",
    #     "CLUSTER_ONLY": "1",
    # }),
    # ("scan_opt_with_cluster", { #This runs scan opt clusatering + 2-opt/3-opt
    #     "TOTAL_WIRE_LENGTH": "1",
    #     "USE_SCAN_OPT": "1",
    #     "SPATIAL_CLUSTER": "1",
    #     "CLUSTER_ONLY": "0",
    # }),
]


def extract_chain_metrics(log_path: Path, csv_path: Path) -> int:
    """Extract the CSV chain-metrics section from a run log.

    Looks for the block delimited by '=== chain_metrics ===' / '=== end
    chain_metrics ===' that flow.tcl emits via report_chain_metrics.
    Writes the inner CSV (header + per-chain rows) to csv_path.

    Returns the number of chain rows written (0 on failure).
    """
    try:
        with open(log_path) as fh:
            text = fh.read()
    except OSError:
        return 0

    start = text.find("=== chain_metrics ===")
    end = text.find("=== end chain_metrics ===")
    if start == -1 or end == -1 or end <= start:
        return 0

    block = text[start:end].splitlines()[1:]   # drop the start marker
    rows = []
    for line in block:
        line = line.strip()
        # Strip OpenROAD log prefixes if present (e.g. "[INFO]  ...").
        if line.startswith("[") or not line:
            continue
        if line.startswith("chain_name") or "," in line:
            rows.append(line)

    if not rows:
        return 0

    with open(csv_path, "w") as out:
        for row in rows:
            out.write(row + "\n")
    # Subtract 1 if header is present.
    return max(0, len(rows) - (1 if rows[0].startswith("chain_name") else 0))


def main():
    parser = argparse.ArgumentParser(description="Sweep scan_opt and floorplan areas")
    parser.add_argument(
        "--lengths",
        type=int,
        nargs="+",
        default=DEFAULT_LENGTH,
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
    for length in args.lengths:
        for label, env in SCENARIOS:
            full_label = f"length_{length}/{label}"
            print(f"{'='*60}")
            print(f"Run: {full_label}")
            run_dir = output_root / f"length_{length}" / label
            log_path = run_dir / "run.log"

            run_env = dict(env)
            run_env["MAX_LENGTH"] = str(length)

            rc = run_openroad(run_env, run_dir, log_path)

            odb_path = run_dir / "aes_sky130hd_fill-tcl.db"
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"

            csv_path = run_dir / "chain_metrics.csv"
            num_chains = extract_chain_metrics(log_path, csv_path)

            results.append(
                {
                    "label": full_label,
                    "status": status,
                    "odb": str(odb_path) if odb_path.exists() else "NOT FOUND",
                    "log": str(log_path),
                    "metrics": str(csv_path) if num_chains > 0 else "NOT FOUND",
                    "num_chains": num_chains,
                }
            )
            print(f"  status : {status}")
            print(f"  odb    : {results[-1]['odb']}")
            print(f"  metrics: {results[-1]['metrics']}  (chains={num_chains})")
            print()

    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    col = max(len(r["label"]) for r in results)
    for r in results:
        print(
            f"  {r['label']:<{col}}  {r['status']:<20}  "
            f"chains={r['num_chains']:<5}  {r['metrics']}"
        )


if __name__ == "__main__":
    main()
