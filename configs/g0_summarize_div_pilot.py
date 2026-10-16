#!/usr/bin/env python3
"""G0-A pilot-only full-process tick comparison.

NOT an accepted Little v0.52 ROI or exact per-core makespan measurement.
Rejects missing evidence; never creates a PASS from source-only markers.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

CASES = ("heavy_sparse", "sparse_heavy", "heavy_heavy", "sparse_sparse")
MODES = ("private2", "shared1")
STRUCTURE = re.compile(r"G0_DIV_STRUCTURE_ASSERT: mode=(private2|shared1)")
SIM_TICKS = re.compile(r"^simTicks\s+(\d+)\s", re.MULTILINE)
EXIT = re.compile(r"SIMULATION_EXIT_CODE=(\d+)")
RESULT = re.compile(r"^.*?G0_RESULT every=\d+ iterations=\d+ div_ops_expected=\d+ checksum=[a-fA-F0-9]+.*$", re.MULTILINE)
CORE_NUM_CYCLES = re.compile(r"^(\S*(?:cores|cpu)([01])\S*\.numCycles)\s+(\d+)\b", re.MULTILINE)


def load_one(root: Path, case: str, mode: str) -> dict:
    path = root / case / mode
    stats_file, sim_log, config = (path / "stats.txt", path / "simulator.log", path / "config.ini")
    for entry in (stats_file, sim_log, config):
        if not entry.is_file() or entry.stat().st_size == 0:
            raise RuntimeError(f"missing nonempty evidence: {entry}")
    stats = stats_file.read_text(encoding="utf-8", errors="replace")
    log = sim_log.read_text(encoding="utf-8", errors="replace")
    if f"G0_DIV_STRUCTURE_ASSERT: mode={mode}" not in log:
        raise RuntimeError(f"missing mode assertion: {path}")
    codes = EXIT.findall(log)
    if not codes or codes[-1] != "0":
        raise RuntimeError(f"missing successful gem5 exit: {path}")
    values = [int(x) for x in SIM_TICKS.findall(stats)]
    if not values:
        raise RuntimeError(f"missing simTicks: {stats_file}")
    # In the absence of an explicit dual-core synchronized ROI, these
    # full-process simTicks include setup, libc, simulation drain and exit.
    results = sorted(x.strip() for x in RESULT.findall(log))
    if len(results) != 2:
        raise RuntimeError(f"expected two deterministic result lines: {sim_log}")
    core_cycles = {}
    for full_key, cpu_id, cycles in CORE_NUM_CYCLES.findall(stats):
        core_cycles[cpu_id] = cycles
    return {"simTicks": values[-1], "results": results, "core_cycles": core_cycles}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path, help="output directory from g0_run_div_pilot.sh")
    p.add_argument("--csv", type=Path, default=None, help="optional new CSV path")
    args = p.parse_args()
    rows = []
    for case in CASES:
        vals = {m: load_one(args.root, case, m) for m in MODES}
        if vals["private2"]["results"] != vals["shared1"]["results"]:
            raise RuntimeError(f"work/output mismatch: {case}")
        private = vals["private2"]["simTicks"]
        shared = vals["shared1"]["simTicks"]
        if private <= 0 or shared <= 0:
            raise RuntimeError(f"invalid ticks for {case}: {private}, {shared}")
        rows.append({
            "case": case,
            "private_full_process_simTicks": private,
            "shared_full_process_simTicks": shared,
            "shared_over_private_ticks": f"{shared / private:.9f}",
            "shared_tick_delta_pct": f"{100 * (shared / private - 1):+.6f}",
            "private_core0_numCycles_UNVERIFIED_ROI": vals["private2"]["core_cycles"].get("0", ""),
            "private_core1_numCycles_UNVERIFIED_ROI": vals["private2"]["core_cycles"].get("1", ""),
            "shared_core0_numCycles_UNVERIFIED_ROI": vals["shared1"]["core_cycles"].get("0", ""),
            "shared_core1_numCycles_UNVERIFIED_ROI": vals["shared1"]["core_cycles"].get("1", ""),
            "status": "PILOT_ONLY_NOT_PAPER_PERFORMANCE",
        })
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    if args.csv is not None:
        if args.csv.exists():
            raise RuntimeError(f"refusing to overwrite existing CSV: {args.csv}")
        with args.csv.open("x", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(
        "WARNING: full-process ticks, not synchronized ROI/per-core pair makespan; "
        "not G0-A quantitative closure",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
