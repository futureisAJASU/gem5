#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_revalidation_wake_w4}"
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

COMMON=(
  "$CFG"
  --binary "$BIN"
  --cores 2
  --distributed-iq
  --local-iq-picker
  --n-skip 4
  --pair-shared-div
  --div-reactive-power
  --div-idle-threshold 8
  --div-wake-latency 4
  --bp-inst-shift 1
)

run_case() {
  local name="$1"
  shift
  local out="$OUT_ROOT/$name"
  rm -rf "$out"
  echo "=== $name ==="
  "$GEM5" --outdir="$out" "${COMMON[@]}" "$@"
}

run_case reactive
run_case decode --div-decode-wake
run_case raw --div-raw-wake

echo
echo "=== W4 summary ==="
printf "%-12s %14s %14s %10s %10s %10s %10s\n" \
  "case" "simTicks" "simInsts" "reactive" "decode" "raw" "blocked"

for name in reactive decode raw; do
  stats="$OUT_ROOT/$name/stats.txt"
  simticks="$(awk '$1=="simTicks"{print $2; exit}' "$stats")"
  siminsts="$(awk '$1=="simInsts"{print $2; exit}' "$stats")"
  reactive="$(awk '/instQueues3\.fuPool\.reactiveWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
  decode="$(awk '/instQueues3\.fuPool\.decodeWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
  raw="$(awk '/instQueues3\.fuPool\.rawWakeTransitions/{s+=$2} END{print s+0}' "$stats")"
  blocked="$(awk '/instQueues3\.fuPool\.reactivePowerBlockedRequests/{s+=$2} END{print s+0}' "$stats")"
  printf "%-12s %14s %14s %10s %10s %10s %10s\n" \
    "$name" "$simticks" "$siminsts" "$reactive" "$decode" "$raw" "$blocked"
done

echo
echo "=== classifier exactness (raw case) ==="
grep -E 'earlyIntDiv(Hints|Truth|TruePositives|FalsePositives|FalseNegatives)' \
  "$OUT_ROOT/raw/stats.txt" || true

echo
echo "=== raw lineage (raw case) ==="
grep -E 'rawIntDivReachedDecode|rawIntDivSquashedBeforeDecode' \
  "$OUT_ROOT/raw/stats.txt" || true

echo
echo "=== predictive lifecycle (decode/raw) ==="
for name in decode raw; do
  echo "--- $name ---"
  grep -E 'instQueues3\.fuPool\.(decodeWake|rawWake)' \
    "$OUT_ROOT/$name/stats.txt" || true
done
