#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_nskip_gap}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"
GAPS=(0 1 2 3 4 5 6 7 8)
CONFIGS=(stock N0 N1 N2 N4)

if [[ ! -x "$GEM5" ]]; then
  echo "ERROR: $GEM5 missing" >&2
  exit 2
fi

bash scripts/build_benchmarks_rv64.sh

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

  "$GEM5" --outdir="$out" \
    "$CFG" \
    --binary "benchmarks/bin/rv64_gap_${gap}" \
    --bp-inst-shift 2 \
    "${narg[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: GAP=$gap config=$cfg failed architectural self-check" >&2
    cat "$out.stdout" >&2
    exit 1
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
echo "=== RV64 centralized N-SKIP directed GAP sweep ==="
printf "%3s %-6s %14s %12s %12s %12s %12s %8s\n" \
  "GAP" "cfg" "simTicks" "rejects" "blocked" "head" "bypass" "maxOff"

for gap in "${GAPS[@]}"; do
  for cfg in "${CONFIGS[@]}"; do
    stats="$OUT_ROOT/gap${gap}/${cfg}/stats.txt"
    ticks="$(awk '$1=="simTicks"{print $2; exit}' "$stats")"
    rejects="$(awk '/\.nSkipWindowRejects /{s+=$2} END{print s+0}' "$stats")"
    blocked="$(awk '/\.nSkipBlockedCycles /{s+=$2} END{print s+0}' "$stats")"
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
    printf "%3s %-6s %14s %12s %12s %12s %12s %8s\n" \
      "$gap" "$cfg" "$ticks" "$rejects" "$blocked" "$head" "$bypass" "$maxoff"
  done
done

echo
echo "=== normalized simTick overhead versus stock ==="
printf "%3s %14s %11s %11s %11s %11s\n" \
  "GAP" "stockTicks" "N0%" "N1%" "N2%" "N4%"

python3 - "$OUT_ROOT" <<'PY'
import pathlib, re, sys
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
echo "All 45 directed runs exited with code 0."
