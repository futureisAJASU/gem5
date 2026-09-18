#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT="${OUT:-rv64_div_fairness}"
GEM5="build/RISCV/gem5.opt"
CFG="configs/02_little_v052_rv64_proxy.py"
BIN="benchmarks/bin/rv64_div_fairness"

echo "[1/3] Rebuild gem5/RISCV with fairness instrumentation"
scons "$GEM5" -j"$JOBS"

echo "[2/3] Build bare RV64 sustained-DIV workload"
bash scripts/build_benchmarks_rv64.sh

echo "[3/3] Run two-core pair-shared DIV contention"
rm -rf "$OUT"
"$GEM5" --outdir="$OUT" \
  "$CFG" \
  --binary "$BIN" \
  --cores 2 \
  --distributed-iq \
  --local-iq-picker \
  --n-skip 4 \
  --pair-shared-div \
  --bp-inst-shift 1

STATS="$OUT/stats.txt"

echo
echo "=== pair-shared DIV fairness ==="
grep -E 'instQueues3\.fuPool\.(pairRequesterGrants|pairContendedRequesterGrants|pairContendedGrants)' "$STATS" || true

g0="$(awk '/instQueues3\.fuPool\.pairRequesterGrants::requester0/{print $2; exit}' "$STATS")"
g1="$(awk '/instQueues3\.fuPool\.pairRequesterGrants::requester1/{print $2; exit}' "$STATS")"
c0="$(awk '/instQueues3\.fuPool\.pairContendedRequesterGrants::requester0/{print $2; exit}' "$STATS")"
c1="$(awk '/instQueues3\.fuPool\.pairContendedRequesterGrants::requester1/{print $2; exit}' "$STATS")"

g0="${g0:-0}"; g1="${g1:-0}"; c0="${c0:-0}"; c1="${c1:-0}"

python3 - "$g0" "$g1" "$c0" "$c1" <<'PY'
import sys
g0,g1,c0,c1 = map(int, sys.argv[1:])
def ratio(a,b):
    return float("inf") if min(a,b)==0 else max(a,b)/min(a,b)
def imbalance(a,b):
    return 0.0 if a+b==0 else abs(a-b)/(a+b)

print(f"total_grants:      requester0={g0} requester1={g1} ratio={ratio(g0,g1):.9f} imbalance={imbalance(g0,g1):.9f}")
print(f"contended_grants:  requester0={c0} requester1={c1} ratio={ratio(c0,c1):.9f} imbalance={imbalance(c0,c1):.9f}")
print("expected architectural DIVs per requester: 32768")
PY

echo
echo "=== completion ==="
grep -E '^(simTicks|simInsts)' "$STATS" || true
