#!/usr/bin/env python3
"""BPU-8 R3C P0 environment/source inventory. NO benchmark execution or corpus lock."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(args: list[str], cwd: Path) -> str | None:
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=10, check=True)
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def detect_source_dirs(root: Path) -> dict[str, str | None]:
    locations = {
        "mibench": ["MiBench", "mibench", "benchmarks/mibench", "benchmarks/MiBench"],
        "coremark": ["coremark", "CoreMark", "benchmarks/coremark"],
    }
    return {
        key: next((str(root / name) for name in names if (root / name).is_dir()), None)
        for key, names in locations.items()
    }


def collect(args: argparse.Namespace) -> dict:
    repo = args.repo.resolve()
    matrix = repo / "docs/bpu8_r3_g5_lock_v01.json"
    preg = repo / "docs/bpu8_r3c_holdout_p0_prereg_v01.json"
    if not matrix.is_file() or not preg.is_file():
        raise SystemExit("R3C_P0_FAIL_CLOSED: expected R3/R3C preregistration files missing")
    r3 = json.loads(matrix.read_text())
    pre = json.loads(preg.read_text())
    names = pre["fixed_profiles"]
    if len(names) != 6 or set(names) != set(r3["profiles"]):
        raise SystemExit("R3C_P0_FAIL_CLOSED: six-profile frozen-matrix mismatch")
    for name in names:
        profile = r3["profiles"][name]
        if profile["total_bits"] != 45736 or not profile["r3_diagnostics"]:
            raise SystemExit(f"R3C_P0_FAIL_CLOSED: unexpected R3 profile {name}")
    if pre["status"] != "PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED":
        raise SystemExit("R3C_P0_FAIL_CLOSED: unexpected prereg state")
    home = Path.home()
    branch = git(["branch", "--show-current"], repo)
    head = git(["rev-parse", "HEAD"], repo)
    dirty = git(["status", "--porcelain", "--untracked-files=no"], repo)
    flags = ("riscv64-linux-gnu-gcc", "riscv64-linux-gnu-g++",
             "riscv64-linux-gnu-readelf", "make", "scons", "yosys", "openroad")
    tools = {command: shutil.which(command) for command in flags}
    sources = detect_source_dirs(home)
    if args.mibench_dir is not None:
        sources["mibench"] = str(args.mibench_dir.resolve()) if args.mibench_dir.is_dir() else None
    if args.coremark_dir is not None:
        sources["coremark"] = str(args.coremark_dir.resolve()) if args.coremark_dir.is_dir() else None
    source_commits = {
        k: git(["rev-parse", "HEAD"], Path(v)) if v else None
        for k, v in sources.items()
    }
    return {
        "kind": "BPU8_R3C_P0_ENV_INVENTORY_NOT_RESULTS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "git_branch": branch,
        "git_head": head,
        "tracked_changes": None if dirty is None else bool(dirty),
        "r3_matrix_sha256": sha256(matrix),
        "r3c_candidate_prereg_sha256": sha256(preg),
        "candidate_cases": [x["id"] for x in pre["suite_candidates"]],
        "candidate_case_count": len(pre["suite_candidates"]),
        "tools": tools,
        "benchmark_source_directories": sources,
        "benchmark_source_git_heads": source_commits,
        "ppa_reference_dir": str(args.ppa_dir.resolve()) if args.ppa_dir and args.ppa_dir.is_dir() else None,
        "host": {"machine": platform.machine(), "python": platform.python_version(),
                 "cpu_count_reported": os.cpu_count()},
        "verdict": "P0_INVENTORY_ONLY_NOT_CORPUS_LOCK_AND_NO_SIMULATIONS",
        "next_gate": "pin external source/input hashes, validate static RV64 ELF and golden outputs, then lock corpus BEFORE paired profile results",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--mibench-dir", type=Path)
    parser.add_argument("--coremark-dir", type=Path)
    parser.add_argument("--ppa-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = collect(args)
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out = args.out.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(encoded)
        print(f"R3C_P0_INVENTORY_WRITTEN={out}")
    print(encoded, end="")


if __name__ == "__main__":
    main()
