#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_pair_shared_fma_burst_density}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"

# Historical AArch64 experiment dimensions preserved exactly where known.
DENSITY_TAGS=(d25 d37p5 d43p75)
DENSITY_LABELS=("25.00%" "37.50%" "43.75%")
BURSTS=(16 32 64 128 256 512 1024 2048 4096 8192)

TOTAL_FMA_PER_CORE=172032
TOTAL_FMA_PAIR=344064

COMMON=(
  --cores 2
  --distributed-iq
  --local-iq-picker
  --int-steering first-fit
  --dist-int0 10
  --dist-int1 6
  --dist-mem 12
  --dist-div 4
  --dist-fpsimd 6
  --dist-int0-write-cap 2
  --dist-int1-write-cap 1
  --dist-mem-write-cap 3
  --dist-div-write-cap 1
  --dist-fpsimd-write-cap 3
  --n-skip 4
  --pair-shared-div
  --bp-inst-shift 2
)

echo "[0/3] Build current gem5/RISCV"
scons "$GEM5" -j"$JOBS"

echo "[1/3] Build 3 x 10 RV64 burst-density binaries"
bash scripts/build_benchmarks_rv64.sh

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

run_one() {
  local tag="$1"
  local burst="$2"
  local mode="$3"
  local bin="benchmarks/bin/rv64_fma_bd_${tag}_b${burst}"
  local out="$OUT_ROOT/${tag}/b${burst}/${mode}"
  local extra=()

  case "$mode" in
    private) ;;
    shared) extra=(--pair-shared-fpsimd) ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     "${COMMON[@]}"     "${extra[@]}"     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: ${tag}/b${burst}/${mode} failed self-check" >&2
    cat "$out.stdout" >&2
    exit 5
  fi
}

echo "[2/3] Run private/shared matrix (60 simulations)"
for i in "${!DENSITY_TAGS[@]}"; do
  tag="${DENSITY_TAGS[$i]}"
  label="${DENSITY_LABELS[$i]}"
  for burst in "${BURSTS[@]}"; do
    echo "  density=${label} burst=${burst} / private"
    run_one "$tag" "$burst" private
    echo "  density=${label} burst=${burst} / shared"
    run_one "$tag" "$burst" shared
  done
done

echo "[3/3] Validate and summarize"
python3 - "$OUT_ROOT" "$TOTAL_FMA_PAIR" <<'PY'
import csv
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
total_fma_pair = int(sys.argv[2])

densities = [
    ("d25", "25.00%"),
    ("d37p5", "37.50%"),
    ("d43p75", "43.75%"),
]
bursts = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192]

def read_stats(path):
    vals = {
        "g0": 0,
        "g1": 0,
        "cg0": 0,
        "cg1": 0,
        "ctotal": 0,
    }
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, raw = p[0], p[1]
        try:
            val = int(float(raw))
        except ValueError:
            continue

        if key == "simTicks":
            vals["ticks"] = val
        elif key == "simInsts":
            vals["insts"] = val
        elif key.endswith(".pairRequesterGrants::requester0"):
            vals["g0"] += val
        elif key.endswith(".pairRequesterGrants::requester1"):
            vals["g1"] += val
        elif key.endswith(".pairContendedRequesterGrants::requester0"):
            vals["cg0"] += val
        elif key.endswith(".pairContendedRequesterGrants::requester1"):
            vals["cg1"] += val
        elif key.endswith(".pairContendedGrants"):
            vals["ctotal"] += val

    if "ticks" not in vals or "insts" not in vals:
        raise RuntimeError(f"missing required stats in {path}")

    vals["cycles"] = vals["ticks"] * 1.4e9 / 1.0e12
    return vals

rows = []
for tag, label in densities:
    for burst in bursts:
        base = root / tag / f"b{burst}"
        private = read_stats(base / "private" / "stats.txt")
        shared = read_stats(base / "shared" / "stats.txt")

        if private["insts"] != shared["insts"]:
            raise SystemExit(
                f"ERROR: simInsts mismatch {tag}/b{burst}: "
                f"private={private['insts']} shared={shared['insts']}"
            )

        if shared["g0"] == 0 or shared["g1"] == 0:
            raise SystemExit(
                f"ERROR: missing shared requester grants for {tag}/b{burst}"
            )

        ratio = shared["cycles"] / private["cycles"]
        slowdown = (ratio - 1.0) * 100.0
        fma_per_cycle = total_fma_pair / shared["cycles"]
        pair_peak_eff = fma_per_cycle / 2.0 * 100.0
        grant_imbalance = abs(shared["g0"] - shared["g1"])
        contended_imbalance = abs(shared["cg0"] - shared["cg1"])
        contended = shared["cg0"] + shared["cg1"]
        grants = shared["g0"] + shared["g1"]
        contended_fraction = (contended / grants * 100.0) if grants else 0.0

        rows.append({
            "density_tag": tag,
            "density": label,
            "burst": burst,
            "private_cycles": private["cycles"],
            "shared_cycles": shared["cycles"],
            "private_insts": private["insts"],
            "shared_insts": shared["insts"],
            "shared_private_ratio": ratio,
            "slowdown_pct": slowdown,
            "shared_fma_per_cycle": fma_per_cycle,
            "shared_pair_peak_eff_pct": pair_peak_eff,
            "grant0": shared["g0"],
            "grant1": shared["g1"],
            "contended0": shared["cg0"],
            "contended1": shared["cg1"],
            "grant_imbalance": grant_imbalance,
            "contended_imbalance": contended_imbalance,
            "contended_grant_fraction_pct": contended_fraction,
        })

print()
print("=== RV64 P21313 pair-shared FMA burst-density sweep ===")
print(
    f"{'density':>8s} {'burst':>6s} "
    f"{'private_cy':>12s} {'shared_cy':>12s} "
    f"{'slow%':>8s} {'FMA/cy':>8s} {'peak%':>8s} "
    f"{'gdiff':>7s} {'cgdiff':>7s} {'cont%':>8s}"
)
for r in rows:
    print(
        f"{r['density']:>8s} {r['burst']:6d} "
        f"{r['private_cycles']:12.1f} {r['shared_cycles']:12.1f} "
        f"{r['slowdown_pct']:8.3f} "
        f"{r['shared_fma_per_cycle']:8.4f} "
        f"{r['shared_pair_peak_eff_pct']:8.2f} "
        f"{r['grant_imbalance']:7d} "
        f"{r['contended_imbalance']:7d} "
        f"{r['contended_grant_fraction_pct']:8.2f}"
    )

print()
print("=== Per-density persistence summary ===")
for tag, label in densities:
    subset = [r for r in rows if r["density_tag"] == tag]
    ratios = [r["shared_private_ratio"] for r in subset]
    gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
    first = subset[0]
    last = subset[-1]
    worst = max(subset, key=lambda x: x["slowdown_pct"])
    print(
        f"{label}: geomean shared/private={gm:.6f} "
        f"(+{(gm-1)*100:.3f}%), "
        f"B16={first['slowdown_pct']:+.3f}%, "
        f"B8192={last['slowdown_pct']:+.3f}%, "
        f"worst=B{worst['burst']} {worst['slowdown_pct']:+.3f}%"
    )

with (root / "summary.csv").open("w", newline="") as f:
    fields = [
        "density_tag","density","burst",
        "private_cycles","shared_cycles",
        "private_insts","shared_insts",
        "shared_private_ratio","slowdown_pct",
        "shared_fma_per_cycle","shared_pair_peak_eff_pct",
        "grant0","grant1","contended0","contended1",
        "grant_imbalance","contended_imbalance",
        "contended_grant_fraction_pct",
    ]
    wr = csv.DictWriter(f, fieldnames=fields)
    wr.writeheader()
    wr.writerows(rows)

print()
print("All 60 simulations self-checked; private/shared simInsts match for every point.")
print("Density labels are nominal payload-period ratios from the reconstructed workload;")
print("interpret measured runtime/FU behavior rather than treating them as literal hardware duty cycle.")
print(f"CSV: {root / 'summary.csv'}")
PY

{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "bp_inst_shift=2"
  echo "cores=2"
  echo "scheduler=P21313 local N4"
  echo "pair_shared_div=on"
  echo "density_points=25,37.5,43.75"
  echo "burst_points=16,32,64,128,256,512,1024,2048,4096,8192"
  echo "total_fma_per_core=$TOTAL_FMA_PER_CORE"
  echo "total_fma_pair=$TOTAL_FMA_PAIR"
  echo "method=RV64 reconstruction of preserved AArch64 experiment dimensions; original generator unavailable"
} >"$OUT_ROOT/manifest.txt"

for tag in "${DENSITY_TAGS[@]}"; do
  for burst in "${BURSTS[@]}"; do
    sha256sum "benchmarks/bin/rv64_fma_bd_${tag}_b${burst}"
  done
done >"$OUT_ROOT/binary_sha256.txt"

echo "Manifest: $OUT_ROOT/manifest.txt"
echo "Binary hashes: $OUT_ROOT/binary_sha256.txt"
