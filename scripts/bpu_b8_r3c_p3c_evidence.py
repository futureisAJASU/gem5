#!/usr/bin/env python3
"""R3C P3C: independently rehash prior P1/P2/P2B/P3A/P3B evidence.

NO gem5 runs, NO performance inspection, NO corpus final lock.
Writes a reproducible pre-lock evidence snapshot only after checking all 11
functional manifests and every recorded stdout/stderr/input/binary hash.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import subprocess

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p3a_functional as p3a
import bpu_b8_r3c_p3b_remaining9 as p3b

EXPECTED = tuple(p2.ORDER)
P3A_CASES = tuple(p3a.CASES)
P3B_CASES = tuple(p3b.CASES)


def require(ok: bool, detail: str) -> None:
    if not ok:
        raise ValueError("P3C_AUDIT_FAIL_CLOSED: " + detail)


def absolute_within(file: Path, root: Path) -> Path:
    path = file.expanduser().resolve()
    require(path.is_relative_to(root.resolve()),
            "recorded path escapes immutable artifact directory: " + str(path))
    return path


def inspect_observation(row: dict, directory: Path) -> dict:
    name = row.get("id")
    require(isinstance(name, str) and name and "/" not in name and "\\" not in name
            and name not in (".", ".."), "invalid run id")
    result = {"id": name, "returncode": row.get("returncode")}
    for key, suffix in (("stdout", ".stdout"), ("stderr", ".stderr")):
        file = directory / (name + suffix)
        require(file.is_file(), "missing observation: " + str(file))
        digest = p2.sha(file)
        require(digest == row.get(key + "_sha256"),
                "observation SHA mismatch: " + str(file))
        require(file.stat().st_size == row.get(key + "_size"),
                "observation size mismatch: " + str(file))
        result[key + "_sha256"] = digest
        result[key + "_size"] = file.stat().st_size
    return result


def verify_p3a(p3a_root: Path, p1: dict, p1_path: Path,
               p2b_root: Path, p2b: dict, mibench: Path,
               coremark: Path) -> tuple[dict, dict]:
    record_path = p3a_root / "functional_manifest.json"
    r = json.loads(record_path.read_text())
    require(r.get("kind") == "BPU8_R3C_P3A_LP64_CORRECTNESS_FEASIBILITY_NO_PERF",
            "P3A kind wrong")
    require(r.get("verdict") == "CROSS_HOST_EQUIVALENCE_2_OF_2_PASS_NOT_CORPUS_LOCK",
            "P3A result not PASS")
    require(r.get("p1_sha256") == p2.sha(p1_path), "P3A P1 source drift")
    require(r.get("p2b_manifest_sha256") == p2.sha(
        p2b_root / "portability_manifest.json"), "P3A P2B manifest drift")
    require(r.get("gem5_runs") == 0 and r.get("predictor_comparisons") == 0
            and r.get("holdout_corpus_locked") is False, "P3A unexpected gate")
    require(set(r["results"]) == set(P3A_CASES), "P3A case set differs")
    p3a.validate_source_gate(p1, p1_path, mibench, coremark, p2b,
                             p2b_root / "portability_manifest.json", p2b_root)
    evidence = {}
    for case in P3A_CASES:
        item = r["results"][case]
        require(item["passed"] is True, case + " functional gate failed")
        execs = item["observations"]
        require(len(execs) == (2 if case == "patricia" else 6),
                case + " execution count mismatch")
        observations = [inspect_observation(x, p3a_root) for x in execs]
        input_info = item["input"]
        src = (p2b_root / "overlay_source" / "mibench" /
               p2.SPECS[case][0] / ("small.udp" if case == "patricia"
                                      else "input_small.asc"))
        require(src.is_file() and p2.sha(src) == input_info["sha256"],
                case + " staged input SHA drift")
        output_files = []
        for record in item.get("output_files", []):
            file = absolute_within(Path(record["path"]), p3a_root)
            require(file.is_file() and p2.sha(file) == record["sha256"]
                    and file.stat().st_size == record["size"],
                    case + " output evidence altered")
            output_files.append({"relative_path": str(file.relative_to(p3a_root)),
                                 "sha256": record["sha256"], "size": record["size"]})
        evidence[case] = {"source_kind": "pinned_lp64_overlay",
                          "rv64_elf_sha256": p2.sha(p2b_root / (case + ".rv64.elf")),
                          "input_sha256": input_info["sha256"],
                          "observations": observations,
                          "files": output_files,
                          "functional_evidence": "CROSS_HOST_PROVISIONAL_ONLY"}
    return r, evidence


def verify_p3b(p3b_root: Path, p1: dict, p1_path: Path,
               p2_root: Path, p2data: dict, mibench: Path,
               coremark: Path) -> tuple[dict, dict]:
    r = json.loads((p3b_root / "functional_manifest.json").read_text())
    require(r.get("kind") == "BPU8_R3C_P3B_9CASE_CROSS_ARCH_REFERENCE_NOT_HOLDOUT",
            "P3B kind wrong")
    require(r.get("verdict") == "9_CASE_CROSS_ARCH_FUNCTIONAL_PASS_NOT_CORPUS_LOCK",
            "P3B result not PASS")
    require(r.get("p1_sha256") == p2.sha(p1_path), "P3B P1 source drift")
    require(r.get("p2_full11_manifest_sha256") == p2.sha(
        p2_root / "build_manifest.json"), "P3B full11 manifest drift")
    require(r.get("gem5_jobs") == 0 and r.get("geometry_experiments") == 0
            and r.get("corpus_locked") is False, "P3B unexpected gate")
    require(r.get("case_order") == list(P3B_CASES)
            and set(r["results"]) == set(P3B_CASES), "P3B case identity drift")
    p3b.ensure_p2_gate(p1, p1_path, p2data, p2_root / "build_manifest.json",
                       p2_root, mibench, coremark)
    evidence = {}
    for case in P3B_CASES:
        row = r["results"][case]
        require(row["passed"] is True and
                row["status"] == "FUNCTIONAL_PASS_PROVISIONAL",
                case + " P3B functional result not PASS")
        checks = row["checks"]
        runs = row["runs"]
        expected_modes = 2 if case == "coremark_performance" else 1
        require(len(checks) == expected_modes and len(runs) == 2 * expected_modes
                and all(x["passed"] is True for x in checks),
                case + " P3B modes incomplete")
        observations = [inspect_observation(x, p3b_root) for x in runs]
        elf = p2_root / (case + ".rv64.elf")
        native = p3b_root / (case + ".aarch64.elf")
        require(native.is_file() and p2.sha(native) ==
                row["native_build"]["elf_sha256"] and
                row["native_build"]["rc"] == 0,
                case + " native control ELF drift")
        declared_inputs = row["input_files"]
        task = p3b.TASKS.get(case, {"inputs": []})
        require([x["path"] for x in declared_inputs] ==
                task.get("inputs", []), case + " input name mismatch")
        source = coremark if case == "coremark_performance" else mibench / p2.SPECS[case][0]
        for inp in declared_inputs:
            file = source / inp["path"]
            require(file.is_file() and file.stat().st_size == inp["size"] and
                    p2.sha(file) == inp["sha256"], case + " input SHA drift")
            for label in ("native", "rv64"):
                actual = p3b_root / (case + "." + label + ".work") / inp["path"]
                require(actual.is_file() and p2.sha(actual) == inp["sha256"],
                        case + " copied input drift")
        if case == "susan_edges":
            for check in checks:
                for label in ("native", "rv64"):
                    rec = check["image_" + label]
                    file = p3b_root / (case + "." + label + ".work") / "edges.pgm"
                    require(rec["exists"] is True and file.is_file()
                            and p2.sha(file) == rec["sha256"],
                            "SUSAN image SHA drift")
        evidence[case] = {
            "source_kind": "pinned_unmodified_mibench_or_coremark",
            "rv64_elf_sha256": p2.sha(elf),
            "native_elf_sha256": p2.sha(native),
            "inputs": declared_inputs,
            "reference_check_modes": [c["mode"] for c in checks],
            "reference_checks": checks,
            "observations": observations,
            "functional_evidence": "CROSS_HOST_PROVISIONAL_ONLY",
        }
    return r, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("p1", "p2_full11_dir", "p2b_dir", "p3a_dir", "p3b_dir",
                 "mibench_dir", "coremark_dir", "out"):
        parser.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    args = parser.parse_args()
    p1path = args.p1.expanduser().resolve()
    p2root = args.p2_full11_dir.expanduser().resolve()
    p2broot = args.p2b_dir.expanduser().resolve()
    p3aroot = args.p3a_dir.expanduser().resolve()
    p3broot = args.p3b_dir.expanduser().resolve()
    mibench = args.mibench_dir.expanduser().resolve()
    coremark = args.coremark_dir.expanduser().resolve()
    dest = args.out.expanduser().resolve()
    require(not dest.exists(), "never overwrite an evidence snapshot")
    p1 = json.loads(p1path.read_text())
    p2data = json.loads((p2root / "build_manifest.json").read_text())
    p2b = json.loads((p2broot / "portability_manifest.json").read_text())
    require(p2b.get("kind") == "BPU8_R3C_P2B_LP64_OVERLAY_BUILD_ONLY"
            and p2b.get("verdict") == "OVERLAY_ELF_2_OF_2_PASS_NOT_FUNCTIONAL",
            "P2B source/ELF gate incomplete")
    p2.verify_p1(p1, mibench, coremark)
    a, ev_a = verify_p3a(p3aroot, p1, p1path, p2broot, p2b, mibench, coremark)
    b, ev_b = verify_p3b(p3broot, p1, p1path, p2root, p2data, mibench, coremark)
    evidence = {**ev_a, **ev_b}
    require(len(evidence) == len(EXPECTED)
            and set(evidence) == set(EXPECTED),
            "11 candidate coverage incomplete")
    prereg_path = p2.ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json"
    prereg = json.loads(prereg_path.read_text())
    require(prereg["status"] == "PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED"
            and [x["id"] for x in prereg["suite_candidates"]] == list(EXPECTED)
            and p2.sha(prereg_path) == p1["prereg_sha256"],
            "pre-result candidate identities modified")
    snapshot = {
        "kind": "BPU8_R3C_P3C_11CASE_PRELOCK_EVIDENCE_SNAPSHOT",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ALL_11_CROSS_HOST_PROVISIONAL_PASS_NOT_CORPUS_LOCK",
        "source_gem5_repo_head": p2.git_head(p2.ROOT),
        "p1_sha256": p2.sha(p1path),
        "p2_full11_manifest_sha256": p2.sha(p2root / "build_manifest.json"),
        "p2b_manifest_sha256": p2.sha(p2broot / "portability_manifest.json"),
        "p3a_manifest_sha256": p2.sha(p3aroot / "functional_manifest.json"),
        "p3b_manifest_sha256": p2.sha(p3broot / "functional_manifest.json"),
        "prereg_sha256": p2.sha(prereg_path),
        "source_revisions": {"mibench": p1["mibench"]["git_head"],
                             "coremark": p1["coremark"]["git_head"]},
        "fixed_profiles": prereg["fixed_profiles"],
        "cases": {case: evidence[case] for case in EXPECTED},
        "case_count": len(EXPECTED),
        "expected_paired_jobs_if_and_only_if_later_locked": 66,
        "gem5_performance_jobs_performed_here": 0,
        "physical_ppa_jobs_performed_here": 0,
        "corpus_frozen": False,
        "unresolved_lock_gates": [
            "independent proof no exact prior benchmark+input/ELF geometry-development overlap",
            "gem5 SE can execute every exact ELF+argv+stdin+working directory and preserve first ROI",
            "first-ROI timing boundaries and exact output/exit codes specified before six-way comparison",
            "susan case is EDGES ONLY; adpcm case is ENCODE ONLY; rijndael case must define encryption-only versus full roundtrip",
            "patricia upstream program intentionally exits 1; gem5 run must distinguish expected process exit status from simulator invocation success",
            "CoreMark fixed 10 iterations is a correctness-only short run, not official EEMBC score",
            "MiBench library license and overlay reproducibility review",
            "separate committed immutable r3c_corpus_lock.json and tested runner",
            "R3P SRAM macro aware physical implementation is completely separate from R3C",
        ],
        "interpretation": ("Cross-host functional evidence audited. This is NOT an "
                           "independent proof of all algorithms, NOT a holdout run, "
                           "NOT a finished runnable corpus lock."),
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print("R3C_P3C_SNAPSHOT=" + str(dest))
    print("R3C_P3C_CASES=11/11")
    print("R3C_P3C_VERDICT=PRELOCK_FUNCTIONAL_EVIDENCE_PASS_CORPUS_NOT_FROZEN")
    print("NO CLAIM: gem5 first-ROI, holdout performance, official CoreMark score or PPA")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("R3C_P3C_FAIL_CLOSED: " + str(exc), file=sys.stderr)
        sys.exit(1)
