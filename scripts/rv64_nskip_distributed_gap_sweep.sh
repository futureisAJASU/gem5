#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_nskip_distributed_gap}"
JOBS="${JOBS:-$(nproc)}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"
GAPS=(0 1 2 3 4 5 6 7 8)
CONFIGS=(stock N0 N1 N2 N4)

echo "[0/2] Rebuild gem5/RISCV so the run cannot use a stale binary"
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
)

run_one() {
  local gap="$1"
  local cfg="$2"
  local out="$OUT_ROOT/gap${gap}/${cfg}"
  local narg=()

  case "$cfg" in
    stock) ;;
    N0) narg=(--n-skip 0) ;;
    N1) narg=(--n-skip 1) ;;
    N2) narg=(--n-skip 2) ;;
    N4) narg=(--n-skip 4) ;;
    *) echo "unknown config: $cfg" >&2; exit 2 ;;
  esac

  rm -rf "$out"
  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "benchmarks/bin/rv64_gap_${gap}"     "${COMMON[@]}"     "${narg[@]}"     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: GAP=$gap config=$cfg failed architectural self-check" >&2
    cat "$out.stdout" >&2
    exit 1
  fi

  if [[ "$cfg" != "stock" ]] &&
     ! grep -q 'nSkipLocalHiddenReady' "$out/stats.txt"; then
    echo "ERROR: local N-SKIP visibility stats missing; refusing stale/instrumentation-mismatched binary" >&2
    exit 3
  fi
}

for gap in "${GAPS[@]}"; do
  echo "=== GAP $gap ==="
  for cfg in "${CONFIGS[@]}"; do
    echo "  $cfg"
    run_one "$gap" "$cfg"
  done
done

echo
echo "=== RV64 P21313 distributed N-SKIP GAP sweep ==="
printf "%3s %-6s %14s %12s %12s %12s %12s %8s\n"   "GAP" "cfg" "simTicks" "hidden" "noVisCy" "head" "bypass" "maxOff"

for gap in "${GAPS[@]}"; do
  for cfg in "${CONFIGS[@]}"; do
    stats="$OUT_ROOT/gap${gap}/${cfg}/stats.txt"
    ticks="$(awk '$1=="simTicks"{print $2; exit}' "$stats")"
    hidden="$(awk '/\.nSkipLocalHiddenReadySamples /{s+=$2} END{print s+0}' "$stats")"
    novis="$(awk '/\.nSkipLocalNoVisibleReadyCycles /{s+=$2} END{print s+0}' "$stats")"
    head="$(awk '/\.nSkipHeadIssued /{s+=$2} END{print s+0}' "$stats")"
    bypass="$(awk '/\.nSkipBypassIssued /{s+=$2} END{print s+0}' "$stats")"
    maxoff="$(awk '
      /\.nSkipIssuedOffset::/ && $2+0 > 0 {
        name=$1
        sub(/^.*::/, "", name)
        if (name ~ /^[0-9]+$/ && name+0 > m) m=name+0
      }
      END {print m+0}
    ' "$stats")"
    printf "%3s %-6s %14s %12s %12s %12s %12s %8s\n"       "$gap" "$cfg" "$ticks" "$hidden" "$novis" "$head" "$bypass" "$maxoff"
  done
done

echo
echo "=== normalized simTick overhead versus distributed stock ==="
printf "%3s %14s %11s %11s %11s %11s\n"   "GAP" "stockTicks" "N0%" "N1%" "N2%" "N4%"

python3 - "$OUT_ROOT" <<'PY'
import pathlib, sys
root=pathlib.Path(sys.argv[1])
configs=["N0","N1","N2","N4"]

def ticks(path):
    for line in path.read_text().splitlines():
        p=line.split()
        if p and p[0]=="simTicks":
            return int(p[1])
    raise RuntimeError(path)

for gap in range(9):
    stock=ticks(root/f"gap{gap}"/"stock"/"stats.txt")
    vals=[]
    for cfg in configs:
        t=ticks(root/f"gap{gap}"/cfg/"stats.txt")
        vals.append((t/stock-1.0)*100.0)
    print(f"{gap:3d} {stock:14d} " + " ".join(f"{v:10.3f}%" for v in vals))
PY

echo
echo "=== P21313 INT steering, N4 only ==="
printf "%3s %12s %12s %12s %12s\n"   "GAP" "IQ0_dispatch" "IQ1_dispatch" "IQ0_fullcy" "IQ1_fullcy"

for gap in "${GAPS[@]}"; do
  stats="$OUT_ROOT/gap${gap}/N4/stats.txt"
  iq0="$(awk '/\.steerIntAluDispatches::IQ0 /{print $2; exit}' "$stats")"
  iq1="$(awk '/\.steerIntAluDispatches::IQ1 /{print $2; exit}' "$stats")"
  f0="$(awk '/\.steerFullCycles::IQ0 /{print $2; exit}' "$stats")"
  f1="$(awk '/\.steerFullCycles::IQ1 /{print $2; exit}' "$stats")"
  printf "%3s %12s %12s %12s %12s\n"     "$gap" "${iq0:-0}" "${iq1:-0}" "${f0:-0}" "${f1:-0}"
done

echo
echo "All 45 distributed runs exited with code 0."
