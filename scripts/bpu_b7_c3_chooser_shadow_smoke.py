#!/usr/bin/env python3
"""ONE-binary G5 vs C3 PC_CHOOSER shadow equivalence smoke (NOT M1/full-19).

Usage:
  python3 scripts/bpu_b7_c3_chooser_shadow_smoke.py --binary /abs/path/to/rv64_exe
  --out ./bpu_b7_c3_chooser_shadow_smoke

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
    "e64": ("tage5-c3-pcchooser-shadow-e64", 46824, 1088),
    "e128": ("tage5-c3-pcchooser-shadow-e128", 47912, 2176),
    "e256": ("tage5-c3-pcchooser-shadow-e256", 50088, 4352),
}
CFG = ROOT / "configs/02_little_v052_rv64_proxy.py"


def sha256(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_first_dump(path):
    # Same prefix semantics as the historical BPU-4C runner.
    # gem5 text.cc emits THREE spaces before the end marker's dashes.
    from decimal import Decimal
    lines = path.read_text().splitlines()
    begin = "---------- Begin Simulation Statistics"
    end = "---------- End Simulation Statistics"
    start = next((i for i, v in enumerate(lines) if v.startswith(begin)), None)
    if start is None:
        raise RuntimeError(f"missing first ROI begin marker: {path}")
    finish = next((i for i in range(start + 1, len(lines))
                   if lines[i].startswith(end)), None)
    if finish is None:
        raise RuntimeError(f"missing complete first ROI end marker: {path}")
    values = {}
    for line in lines[start + 1:finish]:
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            Decimal(fields[1])
        except Exception:
            continue
        if fields[0] in values:
            raise RuntimeError(f"duplicate ROI stat {fields[0]} in {path}")
        values[fields[0]] = fields[1]
    return values


def unique_int(stats, suffix):
    from decimal import Decimal
    matches = [value for key, value in stats.items()
               if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise RuntimeError(f"non-unique/missing exact stat {suffix}: {matches}")
    value = Decimal(matches[0])
    if not value.is_finite() or value != int(value):
        raise RuntimeError(f"non-integral stat {suffix}={value}")
    return int(value)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=pathlib.Path, required=True)
    ap.add_argument("--gem5", type=pathlib.Path, default=ROOT / "build/RISCV/gem5.opt")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "bpu_b7_c3_chooser_shadow_smoke")
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
        "mode": "C3_PC_CHOOSER_SHADOW_DIAGNOSTIC_ONLY",
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
        if (unique_int(stats, "storageBits"), unique_int(stats, "c3PcChooserStorageBits")) != (bits, extra):
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
        eligible = unique_int(stats, "c3PcChooserEligibleCommitted")
        hits = unique_int(stats, "c3PcChooserTagHits")
        flips = unique_int(stats, "c3PcChooserWouldOverride")
        fixes = unique_int(stats, "c3PcChooserWouldFix")
        breaks = unique_int(stats, "c3PcChooserWouldBreak")
        writes = unique_int(stats, "c3PcChooserRowWrites")
        blocked = unique_int(stats, "c3PcChooserCollisionBlocked")
        if not (0 <= flips <= hits <= eligible):
            raise RuntimeError(f"{name}: incorrect C3 eligibility/hit/flip counts")
        disagreements = unique_int(stats, "c3PcChooserDisagreements")
        chooser_updates = unique_int(stats, "c3PcChooserChooserUpdates")
        if flips != fixes + breaks or writes != eligible:
            raise RuntimeError(f"{name}: incorrect C3 chooser shadow accounting")
        if not (flips <= disagreements <= hits and chooser_updates <= disagreements):
            raise RuntimeError(f"{name}: incorrect C3 chooser comparison accounting")
        print(f"{name:5s}: cycles-ticks={ticks}, instructions={inst}, "
              f"base_wrong={base_wrong}, eligible={eligible}, "
              f"hits={hits}, fixes={fixes}, breaks={breaks}")
    print("BPU7_C3_SHADOW_SINGLE_WORKLOAD=PASS")
    print("NOT A BPU-7 REAL M1 OR FULL-19 PERFORMANCE RESULT")


if __name__ == "__main__":
    main()
