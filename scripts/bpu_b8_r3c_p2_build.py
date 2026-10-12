#!/usr/bin/env python3
"""R3C P2: reproduce a P1-pinned set of RV64 static ELF builds. NO gem5 runs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    "basicmath": ("automotive/basicmath",
                  ["basicmath_small.c", "rad2deg.c", "cubic.c", "isqrt.c"], ["-lm"], "-O3"),
    "bitcount": ("automotive/bitcount",
                 ["bitcnt_1.c", "bitcnt_2.c", "bitcnt_3.c", "bitcnt_4.c",
                  "bitcnts.c", "bitfiles.c", "bitstrng.c", "bstr_i.c"], [], "-O3"),
    "qsort": ("automotive/qsort", ["qsort_small.c"], ["-lm"], "-O3"),
    "susan_edges": ("automotive/susan", ["susan.c"], ["-lm"], "-O3"),
    "dijkstra": ("network/dijkstra", ["dijkstra_small.c"], [], "-O3"),
    "patricia": ("network/patricia", ["patricia.c", "patricia_test.c"], [], "-O3"),
    "rijndael_encrypt": ("security/rijndael", ["aes.c", "aesxam.c"], [], "-O3"),
    "fft": ("telecomm/FFT", ["main.c", "fftmisc.c", "fourierf.c"], ["-lm"], "-O3"),
    "adpcm_encode": ("telecomm/adpcm",
                     ["src/adpcm.c", "src/rawcaudio.c"], [], "-O3"),
    "stringsearch": ("office/stringsearch",
                     ["bmhasrch.c", "bmhisrch.c", "bmhsrch.c", "pbmsrch_small.c"], [], "-O3"),
    "coremark_performance": (".",
                              ["core_list_join.c", "core_main.c", "core_matrix.c",
                               "core_state.c", "core_util.c", "posix/core_portme.c"],
                              ["-lm"], "-O2"),
}
ORDER = list(SPECS)

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def git_head(p: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=p, text=True,
        stderr=subprocess.DEVNULL, timeout=15).strip()

def verify_p1(p1: dict, mibench: Path, coremark: Path) -> None:
    if p1.get("verdict") != "SOURCE_TREE_PRESENT_NOT_CORPUS_LOCK":
        raise ValueError("P1 source gate not PASS")
    for name, base in [("mibench", mibench), ("coremark", coremark)]:
        rec = p1[name]
        if not base.is_dir() or not rec.get("git_head") or git_head(base) != rec["git_head"]:
            raise ValueError(name + ": source HEAD differs from P1")
        if rec.get("git_tracked_dirty"):
            raise ValueError(name + ": P1 source tracked tree was dirty")
        state = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=base, text=True, timeout=15).strip()
        if state:
            raise ValueError(name + ": source has new tracked changes")
    for label, info in p1["candidate_sources"].items():
        d = mibench / info["source_subdir"]
        if not d.is_dir():
            raise ValueError(label + ": source directory disappeared")
        for entry in info["files"]:
            file = d / entry["path"]
            if not file.is_file() or file.stat().st_size != entry["size"] or sha(file) != entry["sha256"]:
                raise ValueError(label + ": source bytes differ from P1: " + entry["path"])
    for name, rec in p1["coremark_sources"].items():
        if "sha256" not in rec:
            if not rec.get("exists"):
                raise ValueError("P1 CoreMark include contract failed: " + name)
            continue
        p = coremark / name
        if not p.is_file() or sha(p) != rec["sha256"]:
            raise ValueError("CoreMark file changed since P1: " + name)
    if p1["missing_source_paths"]:
        raise ValueError("P1 contains missing source paths")

def build_cmd(name: str, mibench: Path, coremark: Path,
              gcc: str, target: Path) -> tuple[list[str], Path]:
    rel, sources, libs, opt = SPECS[name]
    work = coremark if name == "coremark_performance" else mibench / rel
    cmd = [gcc, "-static", "-no-pie", "-march=rv64gc", "-mabi=lp64d", opt]
    if name == "coremark_performance":
        cmd.extend(["-I" + str(work), "-I" + str(work / "posix"),
                    '-DFLAGS_STR="RV64GC_STATIC_CROSS_BUILD"',
                    "-DITERATIONS=10", "-DPERFORMANCE_RUN=1",
                    "-DMULTITHREAD=1"])
    cmd.extend(str(work / src) for src in sources)
    cmd.extend(["-o", str(target)])
    cmd.extend(libs)
    return cmd, work

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p1", type=Path, required=True)
    ap.add_argument("--mibench-dir", type=Path, required=True)
    ap.add_argument("--coremark-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="+", choices=ORDER)
    args = ap.parse_args()
    p1file = args.p1.expanduser().resolve()
    p1 = json.loads(p1file.read_text())
    mibench = args.mibench_dir.expanduser().resolve()
    coremark = args.coremark_dir.expanduser().resolve()
    verify_p1(p1, mibench, coremark)
    prereg = json.loads((ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json").read_text())
    if sha(ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json") != p1["prereg_sha256"]:
        raise ValueError("P2 prereg JSON bytes differ from original P1")
    if prereg.get("status") != "PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED":
        raise ValueError("R3C candidate suite lock state invalid")
    if {c["id"] for c in prereg["suite_candidates"]} != set(ORDER):
        raise ValueError("P2 candidate map differs from prereg")
    gcc = shutil.which("riscv64-linux-gnu-gcc")
    readelf = shutil.which("riscv64-linux-gnu-readelf")
    if not gcc or not readelf:
        raise ValueError("RV64 compiler / readelf missing")
    order = [name for name in ORDER if args.only is None or name in args.only]
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError("P2 output directory already exists: select new --out")
    out.mkdir(parents=True)
    results = []
    manifest = {
        "kind": "BPU8_R3C_P2_BUILD_ONLY_NOT_FUNCTIONAL_OR_HOLDOUT",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "p1_snapshot_sha256": sha(p1file),
        "source_commits": {k: p1[k]["git_head"] for k in ("mibench", "coremark")},
        "prereg_sha256": p1["prereg_sha256"],
        "compiler_path": gcc,
        "compiler_version": subprocess.check_output([gcc, "--version"], text=True).splitlines()[0],
        "compiler_binary_sha256": sha(Path(gcc).resolve()),
        "compile_only": True,
        "gem5_runs": 0,
        "output_verdict": "INCOMPLETE",
        "attempted_cases": order,
        "results": results,
    }
    try:
        for name in order:
            outfile = out / (name + ".rv64.elf")
            command, cwd = build_cmd(name, mibench, coremark, gcc, outfile)
            proc = subprocess.run(command, cwd=cwd, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=180)
            (out / (name + ".compile.log")).write_text(proc.stdout)
            item = {"case": name, "compile_cmd": command, "compile_cwd": str(cwd),
                    "compile_returncode": proc.returncode}
            if proc.returncode == 0 and outfile.is_file():
                elf = subprocess.run([readelf, "-h", str(outfile)],
                                     capture_output=True, text=True, timeout=15, check=True)
                dyn = subprocess.run([readelf, "-d", str(outfile)],
                                     capture_output=True, text=True, timeout=15, check=True)
                (out / (name + ".elf-header.txt")).write_text(elf.stdout)
                rv64 = bool(re.search(r"Class:\\s+ELF64", elf.stdout)
                            and re.search(r"Machine:\\s+RISC-V", elf.stdout)
                            and "double-float ABI" in elf.stdout
                            and "NEEDED" not in dyn.stdout)
                item.update(size=outfile.stat().st_size, sha256=sha(outfile),
                            static_rv64_lp64d=rv64)
                if not rv64:
                    item["error"] = "RV64 64-bit LP64D/static check failed"
            else:
                item["error"] = "compile failed; inspect preserved compile log"
            results.append(item)
            print(f"R3C_P2_BUILD {name}: " +
                  ("PASS" if item.get("static_rv64_lp64d") else "FAIL"), flush=True)
    finally:
        ok = len(results) == len(order) and all(x.get("static_rv64_lp64d") for x in results)
        manifest["output_verdict"] = (
            "ALL_SELECTED_STATIC_RV64_ELFS_BUILT_NOT_FUNCTIONALLY_TESTED"
            if ok else "INCOMPLETE_OR_BUILD_FAILURE_NOT_CORPUS_LOCK")
        (out / "build_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(f"R3C_P2_MANIFEST={out / 'build_manifest.json'}", flush=True)
        print(f"R3C_P2_VERDICT={manifest['output_verdict']}", flush=True)
        print("NO CLAIM: functional correctness, fixed inputs, gem5 ROI, holdout or PPA.", flush=True)
    return 0 if ok else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print("R3C_P2_FAIL_CLOSED: " + str(e), file=sys.stderr)
        sys.exit(1)
