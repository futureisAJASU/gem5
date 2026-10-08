#!/usr/bin/env python3
"""ONE-binary G5 vs C3 PC_BIAS shadow equivalence smoke (NOT M1/full-19).

Usage:
  python3 scripts/bpu_b7_c3_shadow_smoke.py --binary /abs/path/to/rv64_exe
  --out ./bpu_b7_c3_shadow_smoke

Fails on missing executables, nonzero benchmark exit, ROI mis-accounting,
baseline path/cycle divergence or any mismatch in the C3 logical-bit budget.
Requires an actual built gem5/RISCV simulator and compatible benchmark.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILES = {
    "g5": ("tage5-iso45k", 45736, 0),
    "e64": ("tage5-c3-pcbias-shadow-e64", 46760, 1024),
    "e128": ("tage5-c3-pcbias-shadow-e128", 47784, 2048),
    "e256": ("tage5-c3-pcbias-shadow-e256", 49832, 4096),
}
CFG = ROOT / "configs/02_little_v052_rv64_proxy.py"


def sha256(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_first_dump(path):
    t = path.read_text()
    begin = "---------- Begin Simulation Statistics ----------"
    end = "---------- End Simulation Statistics"
    if begin not in t or end not in t.split(begin, 1)[1]:
        raise RuntimeError(f"no complete first stats section: {path}")
    first = t.split(begin, 1)[1].split(end, 1)[0]
    d = {}
    for line in first.splitlines():
        vals = line.split()
        if len(vals) >= 2:
            try:
                d[vals[0]] = float(vals[1])
            except ValueError:
                pass
    return d


def unique_int(stats, suffix):
    matches = [v for k, v in stats.items() if k.endswith(suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"non-unique/missing stat {suffix}: {matches}")
    return int(matches[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=pathlib.Path, required=True)
    ap.add_argument("--gem5", type=pathlib.Path, default=ROOT / "build/RISCV/gem5.opt")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "bpu_b7_c3_shadow_smoke")
    args = ap.parse_args()
    binary, gem5 = args.binary.resolve(), args.gem5.resolve()
    out = args.out.resolve()
    if not binary.is_file() or not gem5.is_file():
        raise SystemExit("BLOCKED: missing RV64 benchmark or gem5/RISCV simulator")
    if out.exists():
        raise SystemExit("BLOCKED: refusing to overwrite any prior output/evidence")
    out.mkdir(parents=True, exist_ok=False)
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )
    manifest = {
        "head": proc.stdout.strip(),
        "gem5_sha256": sha256(gem5),
        "config_sha256": sha256(CFG),
        "binary_sha256": sha256(binary),
        "binary_path": str(binary),
        "mode": "C3_SHADOW_DIAGNOSTIC_ONLY",
        "timing": "NOT_M1",
        "profiles": list(PROFILES),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    reference = None
    for name, (bp, bits, extra) in PROFILES.items():
        d = out / name
        d.mkdir()
        cmd = [
            str(gem5), f"--outdir={d}", str(CFG), "--binary", str(binary),
            "--bp-type", bp, "--bp-inst-shift", "1", "--bp-cond-shift", "1",
            "--bp-btb-shift", "2", "--bp-indirect-shift", "1",
            "--btb-entries", "4096",
        ]
        (d / "command.json").write_text(json.dumps(cmd, indent=2))
        with (d / "stdout.txt").open("w") as stdout, (d / "stderr.txt").open("w") as stderr:
            completed = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr)
        if completed.returncode != 0 or "SIMULATION_EXIT_CODE=0" not in (d / "stdout.txt").read_text():
            raise RuntimeError(f"{name}: gem5/benchmark failed, see {d}")
        stats = parse_first_dump(d / "stats.txt")
        if (unique_int(stats, "storageBits"), unique_int(stats, "c3PcBiasStorageBits")) != (bits, extra):
            raise RuntimeError(f"{name}: wrong state-bits accounting")
        inst = unique_int(stats, "simInsts")
        ticks = unique_int(stats, "simTicks")
        base_wrong = unique_int(stats, "committedConditionalWrong")
        final_wrong = unique_int(stats, "finalConditionalWrong")
        if base_wrong != final_wrong:
            raise RuntimeError(f"{name}: shadow changed real G5 committed correctness")
        actual = (inst, ticks, base_wrong)
        if reference is None:
            reference = actual
        elif actual != reference:
            raise RuntimeError(f"{name}: shadow changed instruction/cycle/error baseline {actual} vs {reference}")
        eligible = unique_int(stats, "c3PcBiasEligibleCommitted")
        hits = unique_int(stats, "c3PcBiasTagHits")
        flips = unique_int(stats, "c3PcBiasWouldFlip")
        fixes = unique_int(stats, "c3PcBiasWouldFix")
        breaks = unique_int(stats, "c3PcBiasWouldBreak")
        writes = unique_int(stats, "c3PcBiasTrainWrites")
        blocked = unique_int(stats, "c3PcBiasCollisionBlocked")
        if not (0 <= flips <= hits <= eligible):
            raise RuntimeError(f"{name}: incorrect C3 eligibility/hit/flip counts")
        if flips != fixes + breaks or writes + blocked != eligible:
            raise RuntimeError(f"{name}: incorrect C3 shadow training/flip reconciliation")
        print(f"{name:5s}: cycles-ticks={ticks}, instructions={inst}, "
              f"base_wrong={base_wrong}, eligible={eligible}, "
              f"hits={hits}, fixes={fixes}, breaks={breaks}")
    print("BPU7_C3_SHADOW_SINGLE_WORKLOAD=PASS")
    print("NOT A BPU-7 REAL M1 OR FULL-19 PERFORMANCE RESULT")


if __name__ == "__main__":
    main()
