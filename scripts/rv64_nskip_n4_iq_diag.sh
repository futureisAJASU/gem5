#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_nskip_n4_iq_diag}"
JOBS="${JOBS:-$(nproc)}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"

echo "[0/2] Rebuild gem5/RISCV"
scons "$GEM5" -j"$JOBS"

echo "[1/2] Build directed RV64 GAP binaries"
bash scripts/build_benchmarks_rv64.sh

COMMON=(
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
  --bp-inst-shift 2
  --n-skip 4
)

echo "[2/2] Run N4 per-IQ visibility diagnostics"
for gap in 0 1 2 3 4 5 6 7 8; do
  echo "  GAP $gap"
  out="$OUT_ROOT/gap${gap}"
  rm -rf "$out"
  "$GEM5" --outdir="$out"     "$CFG"     --binary "benchmarks/bin/rv64_gap_${gap}"     "${COMMON[@]}"     >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"
  grep -q 'nSkipLocalHiddenReadySamplesByIQ::IQ0' "$out/stats.txt"
done

echo
echo "=== N4 per-IQ hidden-ready attribution ==="
printf "%3s %14s %12s %12s %12s %12s %12s | %12s %12s %12s %12s %12s\n"   "GAP" "simTicks" "H_INT0" "H_INT1" "H_MEM" "H_DIV" "H_FP"   "NV_INT0" "NV_INT1" "NV_MEM" "NV_DIV" "NV_FP"

for gap in 0 1 2 3 4 5 6 7 8; do
  stats="$OUT_ROOT/gap${gap}/stats.txt"
  ticks="$(awk '$1=="simTicks"{print $2; exit}' "$stats")"

  vals=()
  for i in 0 1 2 3 4; do
    vals+=("$(awk -v pat="nSkipLocalHiddenReadySamplesByIQ::IQ$i" '$1 ~ pat {print $2; exit}' "$stats")")
  done
  nvs=()
  for i in 0 1 2 3 4; do
    nvs+=("$(awk -v pat="nSkipLocalNoVisibleReadyCyclesByIQ::IQ$i" '$1 ~ pat {print $2; exit}' "$stats")")
  done

  printf "%3s %14s %12s %12s %12s %12s %12s | %12s %12s %12s %12s %12s\n"     "$gap" "$ticks"     "${vals[0]:-0}" "${vals[1]:-0}" "${vals[2]:-0}" "${vals[3]:-0}" "${vals[4]:-0}"     "${nvs[0]:-0}" "${nvs[1]:-0}" "${nvs[2]:-0}" "${nvs[3]:-0}" "${nvs[4]:-0}"
done
