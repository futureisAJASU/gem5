#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_pair_shared_fma}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"
BIN="benchmarks/bin/rv64_fma16_stress"

# 8192 iterations * 16 FMADD.D/core * 2 cores.
TOTAL_FMA=262144

echo "[0/3] Build current gem5/RISCV"
scons "$GEM5" -j"$JOBS"

echo "[1/3] Build directed RV64 FMA workload"
bash scripts/build_benchmarks_rv64.sh

COMMON=(
  --binary "$BIN"
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

run_one() {
  local mode="$1"
  local out="$OUT_ROOT/$mode"
  local extra=()

  case "$mode" in
    private-fp) ;;
    shared-fp) extra=(--pair-shared-fpsimd) ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  rm -rf "$out"
  mkdir -p "$OUT_ROOT"

  "$GEM5" --outdir="$out"     "$CFG"     "${COMMON[@]}"     "${extra[@]}"     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $mode workload self-check failed" >&2
    cat "$out.stdout" >&2
    exit 5
  fi
}

echo "[2/3] Run private-vs-pair-shared FP comparison"
run_one private-fp
run_one shared-fp

echo "[3/3] Summarize"
python3 - "$OUT_ROOT" "$TOTAL_FMA" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
total_fma = int(sys.argv[2])

def stats(mode):
    path = root / mode / "stats.txt"
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

    if "ticks" not in vals:
        raise RuntimeError(f"missing simTicks in {path}")

    vals["cycles"] = vals["ticks"] * 1.4e9 / 1.0e12
    vals["fma_per_cycle"] = total_fma / vals["cycles"]
    return vals

private = stats("private-fp")
shared = stats("shared-fp")

print()
print("=== RV64 P21313 scalar-FMA pair-sharing ===")
print(f"{'mode':12s} {'simTicks':>14s} {'cycles':>12s} {'FMA/cycle':>12s} {'g0':>10s} {'g1':>10s} {'cg0':>10s} {'cg1':>10s}")
for name, d in (("private-fp", private), ("shared-fp", shared)):
    print(
        f"{name:12s} {d['ticks']:14d} {d['cycles']:12.1f} "
        f"{d['fma_per_cycle']:12.6f} {d['g0']:10d} {d['g1']:10d} "
        f"{d['cg0']:10d} {d['cg1']:10d}"
    )

print()
print(f"Shared/private runtime ratio: {shared['cycles']/private['cycles']:.6f}")
print(f"Shared FMA throughput efficiency vs 2 FMA/cycle: {shared['fma_per_cycle']/2.0*100:.3f}%")

if shared["g0"] == 0 or shared["g1"] == 0:
    raise SystemExit("ERROR: shared FP requester-grant stats missing")

imb = abs(shared["g0"] - shared["g1"])
cimb = abs(shared["cg0"] - shared["cg1"])
print(f"Shared requester grant imbalance: {imb}")
print(f"Shared contended grant imbalance: {cimb}")
print()
print("AArch64 historical directed reference: 262144 FMA / 138729 cycles = 1.8896 FMA/cycle.")
print("Use the RV64 result as a qualitative cross-ISA replication, not an exact-match requirement.")
PY

{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "binary_sha256=$(sha256sum "$BIN" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "bp_inst_shift=2"
  echo "cores=2"
  echo "scheduler=P21313 local N4"
  echo "total_fma=262144"
  echo "fma_opclass=FloatMultAcc"
} >"$OUT_ROOT/manifest.txt"

echo "Manifest: $OUT_ROOT/manifest.txt"
