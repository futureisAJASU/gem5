#!/usr/bin/env python3
"""Validate BPU-7 pre-freeze sweep matrix and emit a NON-executable ROI plan.

No predictor simulation, build, or source modification is performed.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "bpu7_sweep_matrix_v02.json"
FAMILY_COUNT = {"C1": 3, "C2": 3, "C3": 6, "C4": 3, "C5": 3, "C7": 3}
G5_BITS, G7_BITS = 45736, 65192
MAX_AUX_BITS = G7_BITS - G5_BITS


def power2(n):
    return isinstance(n, int) and n > 0 and (n & (n - 1)) == 0


def compute_bits(p):
    g = p["geometry"]
    family = p["family"]
    if family == "C1":
        assert power2(g["entries"])
        assert g["entry_bits"] == (
            1 + g["tag_bits"] + g["trip_bits"] + g["iteration_bits"]
            + g["confidence_bits"] + g["age_bits"] + 1 + 1
        ), "C1 field layout mismatch"
        return g["entries"] * g["entry_bits"]
    if family == "C2":
        assert power2(g["local_history_entries"]) and power2(g["pht_entries"])
        return g["local_history_entries"] * g["local_history_bits"] + g["pht_entries"] * g["pht_counter_bits"]
    if family == "C3":
        assert power2(g["entries"])
        assert g["entry_bits"] == g["valid_bits"] + g["tag_bits"] + g["residual_counter_bits"] + g["replacement_bits"]
        assert p["mode"] in {"PC_BIAS", "HIST_TAG"}
        return g["entries"] * g["entry_bits"]
    if family == "C4":
        assert power2(g["entries_per_bank"]) and power2(g["bias_entries"])
        assert g["banks"] == len(g["history_lengths"]) == 4
        assert g["history_lengths"] == [0, 8, 24, 64]
        return g["banks"] * g["entries_per_bank"] * g["bank_counter_bits"] + g["bias_entries"] * g["bias_counter_bits"]
    if family == "C5":
        assert power2(g["entries_per_bank"]) and power2(g["local_history_entries"])
        assert g["banks"] == len(g["features"]) == 4
        return (g["banks"] * g["entries_per_bank"] * g["bank_weight_bits"]
                + g["local_history_entries"] * g["local_history_bits"]
                + g["backward_history_bits"])
    if family == "C7":
        assert power2(g["entries"])
        assert g["imli_counter_bits"] == 8 and g["imli_valid_bits"] == 1
        return g["entries"] * g["counter_bits"] + g["imli_counter_bits"] + g["imli_valid_bits"]
    raise ValueError("Unexpected candidate: " + family)


def validate(matrix):
    assert matrix["schema"] == "little-v052-bpu7-sweep-v0.2"
    assert matrix["status"] == "PRE_FREEZE"
    assert matrix["execution_permitted"] is False, "Never auto-authorize execution"
    b = matrix["frozen_baselines"]
    assert (b["G5_bits"], b["G7_bits"], b["gap_bits"], b["C0_bits"]) == (45736, 65192, 19456, 9600)
    assert matrix["condition"] == {
        "cond_index_shift": 1, "btb_index_shift": 2, "indirect_index_shift": 1,
        "btb_proxy_entries": 4096, "ras": 16,
    }
    assert matrix["analysis_policy"]["primary_timing"] == "M1"
    assert matrix["analysis_policy"]["primary_selector"] == "G0_AND_NATIVE_G1_SINGLE_PROFILE"
    assert matrix["analysis_policy"]["oracle_only_elimination"] is False
    assert matrix["analysis_policy"]["no_posthoc_tuning"] is True
    assert len(matrix["required_p0_closures"]) >= 8

    names = matrix["workloads"]
    assert len(names) == 19 and len(set(names)) == 19, "Full-19 missing or duplicated"
    profiles = matrix["profiles"]
    assert len(profiles) == 21, "Expected 21 primary geometry profiles"
    assert Counter(p["family"] for p in profiles) == FAMILY_COUNT
    assert len({p["id"] for p in profiles}) == 21
    assert Counter(p["mode"] for p in profiles if p["family"] == "C3") == {
        "PC_BIAS": 3, "HIST_TAG": 3,
    }, "C3 must have exactly three capacity levels in each mode"
    expected_ids = {
        "C1_E64", "C1_E128", "C1_E256",
        "C2_L64_P256", "C2_L128_P512", "C2_L256_P1024",
        "C3_PC_BIAS_E64", "C3_PC_BIAS_E128", "C3_PC_BIAS_E256",
        "C3_HIST_TAG_E64", "C3_HIST_TAG_E128", "C3_HIST_TAG_E256",
        "C4_E128", "C4_E256", "C4_E512",
        "C5_E128", "C5_E256", "C5_E512",
        "C7_E256", "C7_E512", "C7_E1024",
    }
    assert {p["id"] for p in profiles} == expected_ids, (
        "Missing/unexpected C1/C2/C3/C4/C5/C7 geometry profile"
    )
    assert all(p["mode"] == "base" for p in profiles if p["family"] != "C3"), (
        "Only C3 is two-mode in Round I"
    )

    for p in profiles:
        expected = compute_bits(p)
        assert expected == p["aux_bits_expected"], "Incorrect cost: " + p["id"]
        assert 0 < expected <= MAX_AUX_BITS, "Over G7 gap: " + p["id"]
        assert p["gates"] == ["G0_AND_NATIVE_G1"]
        assert p["timing_primary"] == "M1"
        assert p["status"] == "PRE_FREEZE_UNIMPLEMENTED"
    assert len(profiles) * len(names) == 399 == matrix["expected"]["roi_first_pass"]
    return profiles, names


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    ap.add_argument("--emit", type=Path, help="Generate non-executable planned_jobs.csv and checksums")
    ap.add_argument("--require-run-ready", action="store_true", help="Fail closed while pre-freeze")
    args = ap.parse_args()
    raw = args.matrix.read_bytes()
    matrix = json.loads(raw.decode("utf-8"))
    profiles, workloads = validate(matrix)
    sha = hashlib.sha256(raw).hexdigest()
    print("BPU_B7_MATRIX_VALID=PASS")
    print("matrix_sha256=" + sha)
    print("candidate_families=6 profiles=21 workloads=19 planned_roi=399")
    print("max_extra_bits=" + str(max(x["aux_bits_expected"] for x in profiles)))
    print("BPU_B7_EXECUTION_PERMITTED=NO (PRE-FREEZE, M1 implementation not tested)")

    if args.emit:
        args.emit.mkdir(parents=True, exist_ok=True)
        with (args.emit / "planned_jobs.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["profile", "family", "mode", "workload", "aux_bits", "total_bits", "selector", "timing", "run_status"])
            for p in profiles:
                for w in workloads:
                    writer.writerow([p["id"], p["family"], p["mode"], w,
                                     p["aux_bits_expected"], G5_BITS + p["aux_bits_expected"],
                                     "G0_AND_NATIVE_G1", "M1", "NOT_IMPLEMENTED_DO_NOT_RUN"])
        (args.emit / "matrix.sha256").write_text(sha + "  " + args.matrix.name + "\n")
        print("BPU_B7_PLAN_WRITTEN=" + str(args.emit / "planned_jobs.csv"))
    if args.require_run_ready:
        raise SystemExit("BLOCKED: matrix is PRE-FREEZE and predictor implementations/M1 are not verified")


if __name__ == "__main__":
    main()
