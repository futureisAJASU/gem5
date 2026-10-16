#!/usr/bin/env python3
"""G0-A synchronized pair ROI verifier; no optimistic fallback to simTicks.

Distinct from the earlier full-process pilot. Requires two actual per-core
ready/finish events, one simulator start barrier, C++ retired IntDiv counts,
matching outputs, and prior effective-configuration gates. Not paper PPA.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path

PAIRS = ("heavy_sparse", "sparse_heavy", "heavy_heavy", "sparse_sparse")
MODES = ("private2", "shared1")
READY = re.compile(r"^G0_PAIR_ROI_READY core=([01]) ready_tick=(\d+)\s*$", re.M)
SYNC = re.compile(
    r"^G0_PAIR_ROI_SYNC start_tick=(\d+) ready0=(\d+) ready1=(\d+) "
    r"clock_period_ticks=(\d+) early_core_idle_policy=quiesce\s*$", re.M)
FINISH = re.compile(
    r"^G0_PAIR_ROI_FINISH core=([01]) finish_tick=(\d+) "
    r"pair_start_tick=(\d+) committed_insts=(\d+) "
    r"committed_intdivs=(\d+)\s*$", re.M)
SUMMARY = re.compile(
    r"^G0_PAIR_ROI_SUMMARY pair_start_tick=(\d+) finish0=(\d+) "
    r"finish1=(\d+) pair_makespan_ticks=(\d+) "
    r"clock_period_ticks=(\d+) first_finished_core=([01])\s*$", re.M)
RESULT = re.compile(
    r"G0_RESULT every=(\d+) iterations=(\d+) "
    r"div_ops_expected=(\d+) checksum=([0-9a-fA-F]+)"
)
EXIT = re.compile(r"SIMULATION_EXIT_CODE=(\d+)")


def strict_map(match_list, label):
    if len(match_list) != 2:
        raise RuntimeError(f"{label}: expected exactly two per-core records; got {match_list}")
    result = {}
    for match in match_list:
        idx = int(match[0])
        if idx in result:
            raise RuntimeError(f"{label}: duplicate core {idx}")
        result[idx] = tuple(int(x) for x in match[1:])
    if set(result) != {0, 1}:
        raise RuntimeError(f"{label}: nonmatching cores")
    return result


def read_run(out: Path, case: str, mode: str, n: int) -> dict:
    directory = out / case / mode
    log = (directory / "simulator.log").read_text(errors="replace")
    audit = json.loads((directory / "effective_config_audit.json").read_text())
    if audit.get("status") != "G0_A_CONFIG_AND_POWER_DISABLED_VERIFIED_NOT_PERFORMANCE":
        raise RuntimeError(f"{directory}: effective-config gate not passed")
    if audit.get("mode") != mode or audit.get("pair_div_physical_units") != (
        2 if mode == "private2" else 1
    ):
        raise RuntimeError(f"{directory}: unexpected actual DIV count or mode")
    exits = EXIT.findall(log)
    if len(exits) != 1 or exits[0] != "0":
        raise RuntimeError(f"{directory}: wrong/missing process exit")
    ready = strict_map(READY.findall(log), "READY")
    finish = strict_map(FINISH.findall(log), "FINISH")
    sync = SYNC.findall(log)
    summary = SUMMARY.findall(log)
    if len(sync) != 1 or len(summary) != 1:
        raise RuntimeError(f"{directory}: missing/duplicate ROI synchronization or summary")
    start, ready0, ready1, period = (int(x) for x in sync[0])
    summary_start, finish0, finish1, makespan, summary_period, first = (
        int(x) for x in summary[0]
    )
    if period <= 0 or start <= 0:
        raise RuntimeError(f"{directory}: invalid clock/start")
    if [ready0, ready1] != [ready[0][0], ready[1][0]]:
        raise RuntimeError(f"{directory}: ready/summary timestamps inconsistent")
    if max(ready0, ready1) != start or min(ready0, ready1) > start:
        raise RuntimeError(f"{directory}: common barrier not observed")
    # Same-tick arrivals are a legitimate common start. They do not
    # independently demonstrate that the first core stayed suspended.
    if summary_start != start or summary_period != period:
        raise RuntimeError(f"{directory}: clock/start mismatched between markers")
    if finish0 != finish[0][0] or finish1 != finish[1][0]:
        raise RuntimeError(f"{directory}: inconsistent per-core finish ticks")
    if min(finish0, finish1) < start or makespan != max(finish0, finish1) - start:
        raise RuntimeError(f"{directory}: invalid pair makespan")
    if first != (0 if finish0 <= finish1 else 1):
        raise RuntimeError(f"{directory}: wrong first-finisher classification")
    every = (1 if case.split("_")[0] == "heavy" else 16,
             1 if case.split("_")[1] == "heavy" else 16)
    results = RESULT.findall(log)
    if len(results) != 2:
        raise RuntimeError(f"{directory}: two guest checksums missing")
    actual_outputs = sorted((int(a), int(b), int(c), d.lower()) for a,b,c,d in results)
    expected_divs = []
    for core in (0,1):
        count = 2*((n + every[core]-1)//every[core])
        expected_divs.append(count)
        if finish[core][1] != start:
            raise RuntimeError(f"{directory}: incorrect ROI start on core {core}")
        committed_inst, committed_div = finish[core][2], finish[core][3]
        if committed_div != count:
            raise RuntimeError(
                f"{directory}: retired IntDiv count core{core}={committed_div}, "
                f"expected {count}; may indicate boundary/commit timing bug"
            )
        if committed_inst <= committed_div:
            raise RuntimeError(f"{directory}: impossibly few committed instructions")
    wanted = sorted(
        (every[i], n, expected_divs[i], next(
            (checksum for e,it,d,checksum in actual_outputs
             if (e,it,d)==(every[i],n,expected_divs[i])), ""
        )) for i in (0,1)
    )
    # A same-kind pair has duplicate matching tuples, so comparison of the
    # MULTISET (not just membership) is the required output identity check.
    if actual_outputs != wanted or any(not w[-1] for w in wanted):
        raise RuntimeError(f"{directory}: source workload/result mismatch")
    runtimes = [(finish[i][0]-start)/period for i in (0,1)]
    ipc = [finish[i][2] / runtimes[i] if runtimes[i] > 0 else 0 for i in (0,1)]
    if any(x <= 0 for x in runtimes+ipc):
        raise RuntimeError(f"{directory}: nonpositive runtime/IPC")
    return {
        "start": start, "ready": (ready0, ready1),
        "finish": (finish0, finish1), "pair_makespan_ticks": makespan,
        "period": period, "runtime_cycles": runtimes, "ipc": ipc,
        "committed_insts": (finish[0][2], finish[1][2]),
        "committed_div": (finish[0][3], finish[1][3]),
        "guest_results": actual_outputs,
        "early_core_quiesce_ticks": abs(finish0 - finish1),
        "ready_tick_skew": abs(ready0 - ready1),
        "arrival_barrier_quiesce_exercised": ready0 != ready1,
    }


def compare_pair(out: Path, case: str, n: int) -> dict:
    v = {mode: read_run(out, case, mode, n) for mode in MODES}
    a,b = v["private2"],v["shared1"]
    if a["guest_results"] != b["guest_results"]:
        raise RuntimeError(f"{case}: Private/Shared guest checksum multiset differs")
    if a["committed_div"] != b["committed_div"]:
        raise RuntimeError(f"{case}: retired dynamic DIV mismatch")
    row={"case":case, "iterations":n}
    for mode in MODES:
        x=v[mode]
        row.update({
            f"{mode}_pair_start_tick":x["start"],
            f"{mode}_core0_finish_tick":x["finish"][0],
            f"{mode}_core1_finish_tick":x["finish"][1],
            f"{mode}_pair_makespan_ticks":x["pair_makespan_ticks"],
            f"{mode}_pair_makespan_cycles_equiv":x["pair_makespan_ticks"]/x["period"],
            f"{mode}_core0_runtime_cycles_equiv":x["runtime_cycles"][0],
            f"{mode}_core1_runtime_cycles_equiv":x["runtime_cycles"][1],
            f"{mode}_core0_ipc":x["ipc"][0],
            f"{mode}_core1_ipc":x["ipc"][1],
            f"{mode}_core0_committed_insts":x["committed_insts"][0],
            f"{mode}_core1_committed_insts":x["committed_insts"][1],
            f"{mode}_core0_committed_div":x["committed_div"][0],
            f"{mode}_core1_committed_div":x["committed_div"][1],
            f"{mode}_early_core_quiesce_ticks":x["early_core_quiesce_ticks"],
            f"{mode}_ready_tick_skew":x["ready_tick_skew"],
            f"{mode}_arrival_barrier_quiesce_exercised":x["arrival_barrier_quiesce_exercised"],
        })
    row.update({
        "core0_shared_over_private_runtime":b["runtime_cycles"][0]/a["runtime_cycles"][0],
        "core1_shared_over_private_runtime":b["runtime_cycles"][1]/a["runtime_cycles"][1],
        "pair_shared_over_private_makespan":b["pair_makespan_ticks"]/a["pair_makespan_ticks"],
        "weighted_speedup": "OPEN_NO_SOLO_BASELINES",
        "power_energy": "OPEN",
        "status": "SYNCED_ROI_DIRECTED_PILOT_NOT_REPRESENTATIVE_PAPER_RESULT",
    })
    return row


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--cases", nargs="+", choices=PAIRS, default=list(PAIRS))
    ap.add_argument("--csv", type=Path, required=True)
    args=ap.parse_args()
    if args.iterations <= 0:
        raise SystemExit("--iterations must be positive")
    if len(set(args.cases)) != len(args.cases):
        raise RuntimeError("duplicate G0 ROI case")
    rows=[compare_pair(args.root, case, args.iterations) for case in args.cases]
    if args.csv.exists():
        raise RuntimeError(f"refusing overwrite: {args.csv}")
    with args.csv.open("x", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(
            "G0_PAIR_ROI_PILOT",
            r["case"],
            "makespan_private_ticks="+str(r["private2_pair_makespan_ticks"]),
            "makespan_shared_ticks="+str(r["shared1_pair_makespan_ticks"]),
            "shared/private="+f'{r["pair_shared_over_private_makespan"]:.9f}',
        )
    print("G0_ROI_GATE_PASSED_WITH_LIMITS: no solo baselines, energy, RTL equivalence or full FIXED24 A5")


if __name__=="__main__":
    main()
