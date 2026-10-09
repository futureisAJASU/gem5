#!/usr/bin/env python3
"""BPU-7 C3 PC-only failure diagnosis; NOT new predictor or M1 experiment.

Runs matching untraced and TageC3Diag-traced P1 E256 on four predeclared
Embench workloads. Verifies equal first-ROI committed behavior, then
summarizes FULL-EXECUTION committed debug events by PC and 16-bit prediction-
time GHR. Debug events may include activity outside the first ROI; never
silently equate event totals to first-ROI counters or real M1 performance.
"""
import argparse
import csv
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import bpu_b7_c3_p0_p1_full19 as base

ROOT = Path(__file__).resolve().parents[1]
FOCUS = ("huffbench", "qrduino", "sglib-combined", "cubic")
BP = "tage5-c3-pcchooser-shadow-e256"
TRACE_FIELDS = (
    "pc", "ghr16", "g5", "c3", "actual", "conf", "strength",
    "provider", "bank", "idx", "tag", "hit", "strong", "disagree",
    "dircnt", "choosecnt", "override", "fix", "break",
    "rowwrite", "dirupd", "chooseupd", "alloc",
    "evict", "blocked", "stale",
)
STAT_FIELDS = (
    "simTicks", "simInsts", "committedConditionalPredictions",
    "committedConditionalWrong", "finalConditionalWrong",
    "c3PcChooserStorageBits", "storageBits",
    "c3PcChooserReads", "c3PcChooserEligibleCommitted",
    "c3PcChooserTagHits", "c3PcChooserDisagreements",
    "c3PcChooserWouldOverride", "c3PcChooserWouldFix",
    "c3PcChooserWouldBreak", "c3PcChooserRowWrites",
    "c3PcChooserDirectionUpdates", "c3PcChooserChooserUpdates",
    "c3PcChooserAllocations", "c3PcChooserEvictions",
    "c3PcChooserCollisionBlocked", "c3PcChooserStalePredictions",
)
TRACE_PATTERN = re.compile(r"\bC3DIAG\s+(.+)$")
STATS_HEADING = "C3 P1 E256: PC AND PREDICTION-TIME GHR16 DIAGNOSTIC"
CSV_FIELDS = (
    "workload", "pc", "events", "hits", "disagreements", "overrides",
    "fixes", "breaks", "net", "chooser_updates", "allocations",
    "collision_blocked", "stale", "unique_ghr16",
    "ghr16_with_both_outcomes", "override_pct", "fix_pct",
)


def parse_event(line):
    m = TRACE_PATTERN.search(line)
    if m is None:
        return None
    values = {}
    for token in m.group(1).split():
        if "=" not in token:
            raise ValueError("malformed C3 trace token: " + token)
        key, value = token.split("=", 1)
        if key in values or key not in TRACE_FIELDS:
            raise ValueError("unexpected or duplicate C3 trace key: " + key)
        values[key] = int(value, 16 if value.lower().startswith("0x") else 10)
    if set(values) != set(TRACE_FIELDS):
        raise ValueError(
            "C3 trace missing/extra fields: " +
            repr(sorted(set(TRACE_FIELDS) - set(values)))
        )
    b = values
    if b["pc"] & 1 or not 0 <= b["ghr16"] <= 65535:
        raise ValueError("impossible RVC PC alignment or 16-bit GHR")
    for f in (
        "g5", "c3", "actual", "hit", "strong", "disagree",
        "override", "fix", "break", "rowwrite", "dirupd",
        "chooseupd", "alloc", "evict", "blocked", "stale",
    ):
        if b[f] not in (0, 1):
            raise ValueError(f"{f} is not a boolean: {b[f]}")
    if b["override"] != b["fix"] + b["break"]:
        raise ValueError("override vs fix/break mismatch")
    if b["fix"] and (b["c3"] != b["actual"] or b["g5"] == b["actual"]):
        raise ValueError("invalid hypothetical fix")
    if b["break"] and (b["c3"] == b["actual"] or b["g5"] != b["actual"]):
        raise ValueError("invalid hypothetical break")
    if b["hit"] and b["disagree"] != (b["g5"] != b["c3"]):
        raise ValueError("tagged disagreement does not match prediction-time directions")
    if b["override"] and not (
        b["hit"] and b["strong"] and b["disagree"] and
        b["choosecnt"] == 3 and b["dircnt"] in (0, 3)
    ):
        raise ValueError("P1 override violated chooser threshold")
    if b["chooseupd"] and not (b["hit"] and b["strong"] and b["disagree"]):
        raise ValueError("chooser updated without a strong tagged disagreement")
    if b["dirupd"] + b["alloc"] + b["blocked"] != 1 or b["rowwrite"] != 1:
        raise ValueError("eligible P1 commit transition accounting mismatch")
    return b


def record_for():
    return {
        "events": 0, "hits": 0, "disagreements": 0, "overrides": 0,
        "fixes": 0, "breaks": 0, "chooser_updates": 0,
        "allocations": 0, "collision_blocked": 0, "stale": 0,
        "actual_taken": 0, "actual_not_taken": 0,
    }


def collect_trace(path, workload):
    pcs = defaultdict(record_for)
    contexts = defaultdict(record_for)
    seen = 0
    with path.open("r", errors="replace") as log:
        for line in log:
            x = parse_event(line)
            if x is None:
                continue
            seen += 1
            if seen > 50000000:
                raise ValueError("C3 trace safety cap of 50M events exceeded")
            for row in (pcs[x["pc"]], contexts[(x["pc"], x["ghr16"])]):
                row["events"] += 1
                row["hits"] += x["hit"]
                row["disagreements"] += x["disagree"]
                row["overrides"] += x["override"]
                row["fixes"] += x["fix"]
                row["breaks"] += x["break"]
                row["chooser_updates"] += x["chooseupd"]
                row["allocations"] += x["alloc"]
                row["collision_blocked"] += x["blocked"]
                row["stale"] += x["stale"]
                row["actual_taken"] += x["actual"]
                row["actual_not_taken"] += 1 - x["actual"]
    if seen == 0:
        raise ValueError(f"no committed C3DIAG trace records in {path}")
    if sum(v["events"] for v in pcs.values()) != seen:
        raise ValueError("per-PC event accounting mismatch")
    return pcs, contexts, seen


def format_records(pcs, contexts, workload):
    per_pc_context = defaultdict(list)
    for (pc, ghr), rec in contexts.items():
        per_pc_context[pc].append(rec)
    out = []
    for pc, r in pcs.items():
        c = per_pc_context[pc]
        two_outcomes = sum(
            v["actual_taken"] > 0 and v["actual_not_taken"] > 0
            for v in c
        )
        out.append({
            "workload": workload, "pc": hex(pc),
            "events": r["events"], "hits": r["hits"],
            "disagreements": r["disagreements"],
            "overrides": r["overrides"], "fixes": r["fixes"],
            "breaks": r["breaks"], "net": r["fixes"] - r["breaks"],
            "chooser_updates": r["chooser_updates"],
            "allocations": r["allocations"],
            "collision_blocked": r["collision_blocked"],
            "stale": r["stale"],
            "unique_ghr16": len(c),
            "ghr16_with_both_outcomes": two_outcomes,
            "override_pct": round(100 * r["overrides"] / r["events"], 4),
            "fix_pct": round(100 * r["fixes"] / r["overrides"], 4) if r["overrides"] else 0,
        })
    return sorted(out, key=lambda x: (x["net"], -x["overrides"], x["pc"]))


def write_csv(path, fields, rows):
    with path.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields)
        wr.writeheader()
        wr.writerows(rows)


def run_one(gem5, cfg, bench, folder, tracing):
    folder.mkdir(parents=True, exist_ok=False)
    cmd = [str(gem5), f"--outdir={folder}"]
    if tracing:
        cmd += ["--debug-flags=TageC3Diag", "--debug-file=c3_diag.trace"]
    cmd += [
        str(cfg), "--binary", str(bench), "--bp-type", BP,
        "--bp-inst-shift", "1", "--bp-cond-shift", "1",
        "--bp-btb-shift", "2", "--bp-indirect-shift", "1",
        "--btb-entries", "4096",
    ]
    (folder / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    with (folder / "stdout.txt").open("x") as fo, (folder / "stderr.txt").open("x") as fe:
        p = subprocess.run(cmd, cwd=ROOT, stdout=fo, stderr=fe)
    if p.returncode != 0:
        raise RuntimeError(f"gem5 failed rc={p.returncode}: {folder}")
    if "SIMULATION_EXIT_CODE=0" not in (folder / "stdout.txt").read_text():
        raise RuntimeError(f"benchmark verification marker absent: {folder}")
    stats, roi = base.parse_first_roi(folder / "stats.txt")
    (folder / "roi.stats").write_text(roi)
    results = {k: base.unique_int(stats, k) for k in STAT_FIELDS}
    if results["storageBits"] != 50088 or results["c3PcChooserStorageBits"] != 4352:
        raise RuntimeError(f"wrong P1 E256 persistent bits: {folder}")
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--no-build", action="store_true",
                    help="Reuse a previously built P2 gem5 binary")
    ap.add_argument("--bench-build", type=Path,
                    default=ROOT / "benchmarks/external/embench-iot/bd-rv64-gem5")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workloads", nargs="+", choices=FOCUS, default=FOCUS)
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error("--jobs must be >= 1")
    if len(set(args.workloads)) != len(args.workloads):
        ap.error("duplicate workload")
    out = args.out.resolve()
    if out.exists():
        raise RuntimeError("Output directory already exists; never overwrite raw evidence")
    if not args.no_build:
        subprocess.run(
            ["scons", "build/RISCV/gem5.opt", "--ignore-style",
             f"-j{args.jobs}"], cwd=ROOT, check=True
        )
    gem5 = ROOT / "build/RISCV/gem5.opt"
    if not gem5.exists():
        raise RuntimeError("P2 gem5 binary absent")
    binaries = {
        w: args.bench_build.resolve() / "src" / w / w for w in args.workloads
    }
    if any(not p.is_file() for p in binaries.values()):
        raise RuntimeError("missing cross-built pinned Embench binaries")
    cfg = ROOT / "configs/02_little_v052_rv64_proxy.py"
    out.mkdir(parents=True)
    manifest = {
        "study": "C3_P1_PC_CAUSAL_DIAGNOSTIC_P2",
        "mode": "FULL_EXECUTION_DEBUG_TRACE_NOT_ROI_ALIGNED",
        "not_a_frozen_21_profile_matrix": True,
        "not_a_hist_tag_predictor": True,
        "not_M1": True,
        "branch": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "gem5_sha256": base.sha(gem5),
        "config_sha256": base.sha(cfg),
        "runner_sha256": base.sha(Path(__file__)),
        "binaries": {w: base.sha(p) for w, p in binaries.items()},
        "workloads": list(args.workloads),
        "first_roi_stat_keys": STAT_FIELDS,
        "trace_note": "C3DIAG is written at commit for all G0-eligible branches "
                      "during whole gem5 invocation. May include execution "
                      "outside first ROI; compare with ROI counters but never "
                      "silently attribute trace-PC totals to first ROI.",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    all_pc, all_ctx, summaries = [], [], []
    context_keys = ("workload", "pc", "ghr16", "events", "actual_taken",
                    "actual_not_taken", "overrides", "fixes", "breaks", "net")
    for i, w in enumerate(args.workloads, 1):
        print(f"[{i}/{len(args.workloads)}] {w}: untraced P1 E256 reference", flush=True)
        a = run_one(gem5, cfg, binaries[w], out / w / "control", False)
        print(f"[{i}/{len(args.workloads)}] {w}: same-path C3 debug trace", flush=True)
        b = run_one(gem5, cfg, binaries[w], out / w / "trace", True)
        diffs = [(k, a[k], b[k]) for k in STAT_FIELDS if a[k] != b[k]]
        if diffs:
            raise RuntimeError(f"{w}: TRACE PERTURBED ROI SEMANTICS: {diffs}")
        trace_file = out / w / "trace" / "c3_diag.trace"
        if not trace_file.is_file():
            raise RuntimeError(f"{w}: --debug-file did not create trace")
        pcs, contexts, events = collect_trace(trace_file, w)
        rows = format_records(pcs, contexts, w)
        all_pc.extend(rows)
        for (pc, ghr), r in sorted(contexts.items()):
            all_ctx.append({
                "workload": w, "pc": hex(pc), "ghr16": hex(ghr),
                "events": r["events"], "actual_taken": r["actual_taken"],
                "actual_not_taken": r["actual_not_taken"],
                "overrides": r["overrides"], "fixes": r["fixes"],
                "breaks": r["breaks"], "net": r["fixes"] - r["breaks"],
            })
        f = sum(r["fixes"] for r in pcs.values())
        br = sum(r["breaks"] for r in pcs.values())
        report = {
            "workload": w,
            "full_execution_trace_events": events,
            "unique_pc": len(pcs),
            "unique_pc_ghr16_pairs": len(contexts),
            "trace_wouldFix": f, "trace_wouldBreak": br,
            "trace_net": f - br,
            "first_roi_wouldFix": a["c3PcChooserWouldFix"],
            "first_roi_wouldBreak": a["c3PcChooserWouldBreak"],
            "trace_events_equal_first_roi_eligible":
                events == a["c3PcChooserEligibleCommitted"],
            "top_negative_pc": rows[:12],
            "first_roi_control_equals_trace": True,
        }
        summaries.append(report)
        print(
            f" {w}: first-ROI wouldFix={a['c3PcChooserWouldFix']}, "
            f"wouldBreak={a['c3PcChooserWouldBreak']}; "
            f"full-execution debug events={events}, "
            f"PCs={len(pcs)}, GHR16 contexts={len(contexts)}",
            flush=True
        )
        # Save partial analysis before next benchmark.
        write_csv(out / "by_pc.csv", CSV_FIELDS, all_pc)
        write_csv(out / "by_pc_ghr16.csv", context_keys, all_ctx)
        (out / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print("\nC3_P1_PC_DIAGNOSTIC_P2=PASS", flush=True)
    print("NO CLAIM: full-execution PC trace is first-ROI aligned unless separately proved.")
    print("NO CLAIM: GHR16 correlations prove HIST_TAG causality or M1 improvement.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as ex:
        print("C3_P1_PC_DIAGNOSTIC_P2_FAIL_CLOSED: " + str(ex),
              file=sys.stderr)
        sys.exit(1)
