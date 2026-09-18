#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_wake_latency_sweep}"
BIN="${BIN:-benchmarks/bin/rv64_intdiv_smoke}"
CFG="configs/02_little_v052_rv64_proxy.py"
GEM5="build/RISCV/gem5.opt"

if [[ ! -x "$GEM5" ]]; then
  echo "ERROR: $GEM5 missing; run scripts/rv64_revalidation_smoke.sh first" >&2
  exit 2
fi

if [[ ! -f "$BIN" ]]; then
  bash scripts/build_benchmarks_rv64.sh
fi

LATENCIES=(0 1 2 3 4 5 6 7 8)

run_case() {
  local latency="$1"
  local mode="$2"
  local out="$OUT_ROOT/W${latency}/${mode}"
  local extra=()

  case "$mode" in
    reactive) ;;
    decode) extra+=(--div-decode-wake) ;;
    raw) extra+=(--div-raw-wake) ;;
    *) echo "unknown mode: $mode" >&2; exit 2 ;;
  esac

  rm -rf "$out"
  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" \
    "$CFG" \
    --binary "$BIN" \
    --cores 2 \
    --distributed-iq \
    --local-iq-picker \
    --n-skip 4 \
    --pair-shared-div \
    --div-reactive-power \
    --div-idle-threshold 8 \
    --div-wake-latency "$latency" \
    --bp-inst-shift 1 \
    "${extra[@]}" \
    >"$out.stdout" 2>"$out.stderr"
}

for w in "${LATENCIES[@]}"; do
  echo "=== W$w ==="
  run_case "$w" reactive
  run_case "$w" decode
  run_case "$w" raw
done

echo
echo "=== RV64 predictive-wake latency sweep ==="
printf "%3s %-9s %14s %10s %10s %10s %10s %10s %10s\n" \
  "W" "case" "simTicks" "blocked" "reactive" "decode" "raw" "matched" "expired"

for w in "${LATENCIES[@]}"; do
  for mode in reactive decode raw; do
    stats="$OUT_ROOT/W${w}/${mode}/stats.txt"
    simticks="$(awk '$1=="simTicks"{print $2; exit}' "$stats")"
    blocked="$(awk '/instQueues3\.fuPool\.reactivePowerBlockedRequests/{s+=$2} END{print s+0}' "$stats")"
    reactive="$(awk '/instQueues3\.fuPool\.reactiveWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
    decode="$(awk '/instQueues3\.fuPool\.decodeWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
    raw="$(awk '/instQueues3\.fuPool\.rawWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
    if [[ "$mode" == "decode" ]]; then
      matched="$(awk '/instQueues3\.fuPool\.decodeWakeDemandMatched/{s+=$2} END{print s+0}' "$stats")"
      expired="$(awk '/instQueues3\.fuPool\.decodeWakeExpired/{s+=$2} END{print s+0}' "$stats")"
    elif [[ "$mode" == "raw" ]]; then
      matched="$(awk '/instQueues3\.fuPool\.rawWakeDemandMatched/{s+=$2} END{print s+0}' "$stats")"
      expired="$(awk '/instQueues3\.fuPool\.rawWakeExpired/{s+=$2} END{print s+0}' "$stats")"
    else
      matched=0
      expired=0
    fi
    printf "%3s %-9s %14s %10s %10s %10s %10s %10s %10s\n" \
      "$w" "$mode" "$simticks" "$blocked" "$reactive" "$decode" "$raw" "$matched" "$expired"
  done
done

echo
echo "=== Performance deltas vs reactive at each W ==="
printf "%3s %14s %14s %14s %12s %12s\n" \
  "W" "reactiveTicks" "decodeTicks" "rawTicks" "decSaved" "rawSaved"

for w in "${LATENCIES[@]}"; do
  rt="$(awk '$1=="simTicks"{print $2; exit}' "$OUT_ROOT/W${w}/reactive/stats.txt")"
  dt="$(awk '$1=="simTicks"{print $2; exit}' "$OUT_ROOT/W${w}/decode/stats.txt")"
  bt="$(awk '$1=="simTicks"{print $2; exit}' "$OUT_ROOT/W${w}/raw/stats.txt")"
  printf "%3s %14s %14s %14s %12d %12d\n" \
    "$w" "$rt" "$dt" "$bt" "$((rt-dt))" "$((rt-bt))"
done
