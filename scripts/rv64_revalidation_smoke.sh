#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_revalidation_smoke}"
SKIP_BUILD="${SKIP_BUILD:-0}"

command -v riscv64-linux-gnu-gcc >/dev/null || {
  echo "ERROR: riscv64-linux-gnu-gcc not found" >&2
  exit 2
}

if [[ "$SKIP_BUILD" == "1" ]]; then
  echo "[1/4] Reuse existing gem5/RISCV"
  [[ -x build/RISCV/gem5.opt ]] || {
    echo "ERROR: SKIP_BUILD=1 but build/RISCV/gem5.opt is missing" >&2
    exit 2
  }
else
  echo "[1/4] Build gem5/RISCV"
  scons build/RISCV/gem5.opt -j"$JOBS"
fi

echo "[2/4] Build directed RV64 binaries"
bash scripts/build_benchmarks_rv64.sh

echo "[3/4] Single-core raw-classifier accuracy smoke"
rm -rf "$OUT_ROOT/classifier"
build/RISCV/gem5.opt \
  --outdir="$OUT_ROOT/classifier" \
  configs/02_little_v052_rv64_proxy.py \
  --binary benchmarks/bin/rv64_intdiv_smoke \
  --bp-inst-shift 1

echo
echo "Raw classifier counters:"
grep -E 'earlyIntDiv(Hints|Truth|TruePositives|FalsePositives|FalseNegatives)' \
  "$OUT_ROOT/classifier/stats.txt" || true

echo "[4/4] Two-core pair-shared DIV raw-wake smoke"
rm -rf "$OUT_ROOT/pair_raw_wake"
build/RISCV/gem5.opt \
  --outdir="$OUT_ROOT/pair_raw_wake" \
  configs/02_little_v052_rv64_proxy.py \
  --binary benchmarks/bin/rv64_intdiv_smoke \
  --cores 2 \
  --distributed-iq \
  --local-iq-picker \
  --int-steering int1-first \
  --n-skip 4 \
  --pair-shared-div \
  --div-reactive-power \
  --div-raw-wake \
  --div-idle-threshold 8 \
  --div-wake-latency 4 \
  --bp-inst-shift 1

echo
echo "Raw wake counters:"
grep -E 'rawWake|reactiveWake|earlyIntDiv' \
  "$OUT_ROOT/pair_raw_wake/stats.txt" || true

echo
echo "RV64 smoke complete."
