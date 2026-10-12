#!/usr/bin/env python3
"""R3C P1 source custody audit — no builds, ROI, or geometry comparisons."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = {
    "basicmath": "automotive/basicmath",
    "bitcount": "automotive/bitcount",
    "qsort": "automotive/qsort",
    "susan_edges": "automotive/susan",
    "dijkstra": "network/dijkstra",
    "patricia": "network/patricia",
    "rijndael_encrypt": "security/rijndael",
    "fft": "telecomm/FFT",
    "adpcm_encode": "telecomm/adpcm",
    "stringsearch": "office/stringsearch",
}

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def cmd(*args: str, cwd: Path) -> str | None:
    try:
        return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.PIPE, timeout=20).strip()
    except (OSError, subprocess.SubprocessError):
        return None

def dir_record(root: Path) -> dict:
    if not root.is_dir():
        return {"exists": False, "path": str(root)}
    return {
        "exists": True,
        "path": str(root.resolve()),
        "git_head": cmd("git", "rev-parse", "HEAD", cwd=root),
        "git_branch": cmd("git", "branch", "--show-current", cwd=root),
        "git_remote_origin": cmd("git", "remote", "get-url", "origin", cwd=root),
        "git_tracked_dirty": bool(cmd("git", "status", "--porcelain", "--untracked-files=no", cwd=root) or ""),
    }

def file_record(root: Path, subdir: str) -> dict:
    folder = root / subdir
    record = {"source_subdir": subdir, "exists": folder.is_dir()}
    if not folder.is_dir():
        return record
    files = sorted((p for p in folder.rglob("*") if p.is_file() and not p.is_symlink()),
                   key=lambda x: x.relative_to(folder).as_posix())
    leaves = [{"path": p.relative_to(folder).as_posix(), "size": p.stat().st_size,
               "sha256": sha(p)} for p in files]
    h = hashlib.sha256()
    for f in leaves:
        h.update(json.dumps(f, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    record.update(files_count=len(leaves),
                  tree_sha256_of_path_size_hash_manifest=h.hexdigest(),
                  files=leaves,
                  has_compile=(folder / "COMPILE").is_file(),
                  has_license=(folder / "LICENSE").is_file(),
                  has_small_runner=(folder / "runme_small.sh").is_file(),
                  has_large_runner=(folder / "runme_large.sh").is_file())
    return record

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mibench-dir", required=True, type=Path)
    p.add_argument("--coremark-dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    mibench = args.mibench_dir.expanduser().resolve()
    coremark = args.coremark_dir.expanduser().resolve()
    prereg_path = ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json"
    prereg = json.loads(prereg_path.read_text())
    if prereg.get("status") != "PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED":
        raise SystemExit("R3C_P1_FAIL_CLOSED: wrong prereg status")
    expected = set(CANDIDATES) | {"coremark_performance"}
    if set(c["id"] for c in prereg["suite_candidates"]) != expected:
        raise SystemExit("R3C_P1_FAIL_CLOSED: candidate identity drift")
    mrec = dir_record(mibench)
    crec = dir_record(coremark)
    cases = {name: file_record(mibench, rel) for name, rel in CANDIDATES.items()}
    core_files = ["LICENSE.md", "README.md", "Makefile", "core_main.c",
                  "core_list_join.c", "core_matrix.c", "core_state.c",
                  "core_util.c", "coremark.h", "linux/core_portme.mak",
                  "posix/core_portme.mak", "posix/core_portme.c",
                  "posix/core_portme.h",
                  "posix/core_portme_posix_overrides.h"]
    core_status = {
        name: {"exists": (coremark / name).is_file(),
               "sha256": sha(coremark / name) if (coremark / name).is_file() else None}
        for name in core_files
    }
    # eembc/coremark Linux port is a Makefile wrapper over POSIX sources.
    # Do not require nonexistent linux/core_portme.c or .h files.
    # These are source-contract checks only, NOT evidence of a working RV64 build.
    linux_mak = coremark / "linux/core_portme.mak"
    posix_mak = coremark / "posix/core_portme.mak"
    if linux_mak.is_file():
        linux_contents = linux_mak.read_text()
        core_status["linux_make_includes_posix"] = {
            "exists": "include posix/core_portme.mak" in linux_contents
        }
    if posix_mak.is_file():
        posix_contents = posix_mak.read_text()
        core_status["posix_make_uses_port_source"] = {
            "exists": "PORT_SRCS = posix/core_portme.c" in posix_contents
        }
    missing = [name for name, rec in cases.items() if not rec["exists"]]
    missing += ["coremark/" + name for name, rec in core_status.items() if not rec["exists"]]
    result = {
        "kind": "BPU8_R3C_P1_SOURCE_CUSTODY_NO_COMPILE_NO_RUN",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "gem5_repo_commit": cmd("git", "rev-parse", "HEAD", cwd=ROOT),
        "prereg_sha256": sha(prereg_path),
        "mibench": mrec,
        "coremark": crec,
        "candidate_sources": cases,
        "coremark_sources": core_status,
        "missing_source_paths": missing,
        "verdict": ("SOURCE_TREE_PRESENT_NOT_CORPUS_LOCK"
                    if not missing else "SOURCE_INCOMPLETE_NOT_CORPUS_LOCK"),
        "explicit_limits": [
            "source presence and file hashes only",
            "MiBench mirror must not be silently called official distribution",
            "per-case license and expected output validation still pending",
            "static RV64 builds and ABI still untested",
            "input filenames, exact bytes and runtime command lines NOT LOCKED",
            "no baseline/candidate gem5 performance was run",
            "PPA environment separate; no SRAM macro cost claims",
        ],
    }
    out = args.out.expanduser().resolve()
    if out.exists():
        raise SystemExit("R3C_P1_FAIL_CLOSED: output already exists; choose new --out")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"R3C_P1_SOURCE_AUDIT_WRITTEN={out}")
    print(f"R3C_P1_SOURCE_PATHS_MISSING={len(missing)}")
    print("R3C_P1_VERDICT=" + result["verdict"])
    if missing:
        print("R3C_P1_MISSING=" + ",".join(missing))
    print("NO CLAIM: corpus locked, RV64 validated, holdout completed or RTL/PPA.")
    return 0 if not missing else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print("R3C_P1_FAIL_CLOSED: " + str(e), file=sys.stderr)
        sys.exit(1)
