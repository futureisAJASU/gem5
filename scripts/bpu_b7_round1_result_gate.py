#!/usr/bin/env python3
"""Fail-closed BPU-7 Round-I result reconciler and Pareto *screen*.

No simulations are launched. Requires normalized REAL per-ROI evidence from the
yet-to-be-written C1..C7 implementations. Do not use synthetic rows as results.

Expected CSV columns:
  profile,workload,cycles,insts,committed,base_wrong,final_wrong,
  fixes,breaks,overrides,total_bits,bp_reads,bp_writes,m1_verified,
  test_gate_pass,run_sha,artifact_sha256

Must include R0 and R1 for every workload, plus all 21 registered candidates.
C0 is historical and not a required Round-I row.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "bpu7_sweep_matrix_v02.json"
NUMERIC = ("cycles", "insts", "committed", "base_wrong", "final_wrong",
           "fixes", "breaks", "overrides", "total_bits", "bp_reads", "bp_writes")
REQUIRED = {"profile", "workload", *NUMERIC, "m1_verified", "test_gate_pass",
            "run_sha", "artifact_sha256"}


def fail(message):
    raise ValueError(message)


def read_matrix(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "little-v052-bpu7-sweep-v0.2":
        fail("unknown matrix schema")
    if data.get("execution_permitted") is not False:
        fail("preflight script is designed for the frozen v0.2 pre-freeze matrix")
    profiles = data["profiles"]
    names = [p["id"] for p in profiles]
    if len(names) != 21 or len(set(names)) != 21:
        fail("matrix profile count or identities invalid")
    w = data["workloads"]
    if len(w) != 19 or len(set(w)) != 19:
        fail("matrix workload list invalid")
    bits = {p["id"]: 45736 + p["aux_bits_expected"] for p in profiles}
    bits.update({"R0": 45736, "R1": 65192})
    return names, w, bits


def read_results(path, names, workloads, bits):
    seen = {}
    with path.open(newline="", encoding="utf-8") as stream:
        rd = csv.DictReader(stream)
        if not rd.fieldnames or not REQUIRED.issubset(set(rd.fieldnames)):
            fail("missing CSV columns: " + ", ".join(sorted(REQUIRED - set(rd.fieldnames or []))))
        for line, row in enumerate(rd, 2):
            key = row["profile"], row["workload"]
            if key in seen:
                fail(f"duplicate profile/workload at line {line}: {key}")
            if key[0] not in names + ["R0", "R1"] or key[1] not in workloads:
                fail(f"unregistered profile/workload at line {line}: {key}")
            if row["test_gate_pass"] != "PASS":
                fail(f"test gate not PASS for {key}")
            if row["m1_verified"] not in ("0", "1"):
                fail(f"invalid m1 flag {key}")
            if key[0] not in ("R0", "R1") and row["m1_verified"] != "1":
                fail(f"no M1 latency proof for candidate {key}")
            if not re.fullmatch("[0-9a-f]{40}", row["run_sha"]):
                fail(f"missing git commit SHA {key}")
            if not re.fullmatch("[0-9a-f]{64}", row["artifact_sha256"]):
                fail(f"missing actual artifact digest {key}")
            for field in NUMERIC:
                try:
                    row[field] = int(row[field])
                except (TypeError, ValueError):
                    fail(f"invalid integer {field} at {key}")
                if row[field] < 0:
                    fail(f"negative value {field} at {key}")
            if min(row["cycles"], row["insts"], row["committed"]) == 0:
                fail(f"empty ROI at {key}")
            if row["total_bits"] != bits[key[0]]:
                fail(f"storage mismatch {key}: got {row['total_bits']} expected {bits[key[0]]}")
            if row["final_wrong"] > row["committed"] or row["base_wrong"] > row["committed"]:
                fail(f"branch accounting exceeds committed count {key}")
            if row["overrides"] != row["fixes"] + row["breaks"]:
                fail(f"overrides != fixes+breaks {key}")
            if row["final_wrong"] != row["base_wrong"] - row["fixes"] + row["breaks"]:
                fail(f"finalWrong identity fails {key}")
            if row["fixes"] > row["base_wrong"] or row["breaks"] > row["committed"] - row["base_wrong"]:
                fail(f"fixes/breaks exceed available labels {key}")
            if key[0] in ("R0", "R1") and (row["overrides"] or row["fixes"] or row["breaks"]):
                fail(f"bare TAGE baseline has incorrect auxiliary overrides {key}")
            seen[key] = row

    need = {(p, w) for p in names + ["R0", "R1"] for w in workloads}
    missing = sorted(need - set(seen))
    if missing:
        fail(f"INCOMPLETE: {len(seen)}/{len(need)} ROI; missing {len(missing)}; examples {missing[:8]}")
    inst_per_workload = defaultdict(set)
    for (_, w), row in seen.items():
        inst_per_workload[w].add(row["insts"])
    mismatches = {w: sorted(inst) for w, inst in inst_per_workload.items() if len(inst) != 1}
    if mismatches:
        fail(f"committed instruction counts differ across profiles: {mismatches}")
    return seen


def geomean(ratios):
    if not ratios or any(x <= 0 for x in ratios):
        fail("geomean nonpositive/empty input")
    return math.exp(sum(math.log(x) for x in ratios) / len(ratios))


def aggregate(rows, profiles, workloads):
    result = []
    for profile in profiles:
        rs = [rows[(profile, w)] for w in workloads]
        g5 = [rows[("R0", w)] for w in workloads]
        g7 = [rows[("R1", w)] for w in workloads]
        ratios = [a["cycles"] / b["cycles"] for a, b in zip(rs, g5)]
        inst = sum(r["insts"] for r in rs)
        result.append({
            "profile": profile,
            "bits": rs[0]["total_bits"],
            "g5_geomean_pct": (geomean(ratios) - 1.0) * 100.0,
            "g7_geomean_pct": (geomean([a["cycles"] / b["cycles"] for a, b in zip(rs, g7)]) - 1.0) * 100.0,
            "worst_vs_g5_pct": (max(ratios) - 1.0) * 100.0,
            "bp_reads_per_kinst": 1000 * sum(r["bp_reads"] for r in rs) / inst,
            "bp_writes_per_kinst": 1000 * sum(r["bp_writes"] for r in rs) / inst,
            "fixes": sum(r["fixes"] for r in rs),
            "breaks": sum(r["breaks"] for r in rs),
            "net_fixes": sum(r["fixes"] - r["breaks"] for r in rs),
            "roi_count": len(rs),
        })
    return result


def dominates(a, b):
    # An engineering shortlist, not a statistical assertion or PPA signoff.
    keys = ("g5_geomean_pct", "bits", "bp_reads_per_kinst", "worst_vs_g5_pct")
    no_worse = all(a[k] <= b[k] for k in keys)
    strict = any(a[k] < b[k] for k in keys)
    return no_worse and strict


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", type=Path, default=MATRIX)
    ap.add_argument("--results", type=Path, required=True,
                    help="Normalized REAL 437-row ROI CSV, not planned_jobs.csv")
    ap.add_argument("--out", type=Path, help="Write validated preliminary Pareto table")
    args = ap.parse_args()
    try:
        profiles, workloads, bits = read_matrix(args.matrix)
        if not args.results.is_file():
            fail("BLOCKED: real BPU-7 ROI result CSV does not exist")
        rows = read_results(args.results, profiles, workloads, bits)
        summary = aggregate(rows, ["R0", "R1"] + profiles, workloads)
        for item in summary:
            item["round1_dominated"] = any(
                dominates(other, item) for other in summary if other["profile"] != item["profile"]
            )
        print("BPU_B7_ROUND1_COMPLETE=PASS")
        print("candidate_profiles=21, reference_profiles=2, real_roi=437")
        print("NOTE: exploratory Pareto screening only; holdout and RTL/PPA NOT verified")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", newline="", encoding="utf-8") as out:
                writer = csv.DictWriter(out, fieldnames=list(summary[0]))
                writer.writeheader()
                writer.writerows(summary)
            print("BPU_B7_PARETO_CSV=" + str(args.out))
        for item in sorted(summary, key=lambda r: r["g5_geomean_pct"]):
            print("{profile:21} {g5_geomean_pct:+9.5f}% {bits:6d} bits "
                  "{bp_reads_per_kinst:10.2f} reads/KI "
                  "{worst_vs_g5_pct:+8.4f}% worst, netFix={net_fixes:+d} "
                  "dominated={round1_dominated}".format(**item))
    except (ValueError, OSError, KeyError) as exc:
        print("BPU_B7_ROUND1_COMPLETE=BLOCKED: " + str(exc), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
