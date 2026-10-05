#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b1_rv64}"
SKIP_BUILD="${SKIP_BUILD:-0}"
CFG="configs/02_little_v052_rv64_proxy.py"

if [[ "$SKIP_BUILD" == "1" ]]; then
  [[ -x build/RISCV/gem5.opt ]] || {
    echo "ERROR: SKIP_BUILD=1 but build/RISCV/gem5.opt is missing" >&2
    exit 2
  }
else
  echo "[1/5] Build gem5/RISCV with Little micro-TAGE seed"
  scons build/RISCV/gem5.opt -j"$JOBS"
fi

echo "[2/5] Build directed RV64 binaries"
bash scripts/build_benchmarks_rv64.sh

DEFAULT_BIN="$ROOT/benchmarks/bin/independent_int_rv64"
EMBENCH_BUILD="${EMBENCH_BUILD:-$ROOT/benchmarks/external/embench-iot/bd-rv64-gem5}"
if [[ -n "${BPU_AUDIT_BIN:-}" ]]; then
  AUDIT_BIN="$BPU_AUDIT_BIN"
  EVIDENCE_SCOPE="USER_SELECTED"
elif [[ -x "$EMBENCH_BUILD/src/sglib-combined/sglib-combined" ]]; then
  AUDIT_BIN="$EMBENCH_BUILD/src/sglib-combined/sglib-combined"
  EVIDENCE_SCOPE="EMBENCH_SGLIB"
else
  AUDIT_BIN="$DEFAULT_BIN"
  EVIDENCE_SCOPE="DIRECTED_SMOKE_ONLY"
fi

[[ -x "$AUDIT_BIN" ]] || {
  echo "ERROR: audit binary is missing or not executable: $AUDIT_BIN" >&2
  exit 2
}

echo "[3/5] Audit binary"
echo "BPU_AUDIT_BIN=$AUDIT_BIN"
echo "BPU_SHIFT_EVIDENCE_SCOPE=$EVIDENCE_SCOPE"
file "$AUDIT_BIN" || true
if command -v riscv64-linux-gnu-objdump >/dev/null 2>&1; then
  compressed_lines="$(
    riscv64-linux-gnu-objdump -d "$AUDIT_BIN" |
      awk '/^[[:space:]]*[0-9a-f]+:[[:space:]]+[0-9a-f]{4}[[:space:]]/ {n++}
           END {print n+0}'
  )"
  echo "BPU_AUDIT_16BIT_ENCODING_LINES=$compressed_lines"
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

run_case() {
  local pred="$1"
  local shift="$2"
  local tag="${pred}_shift${shift}"
  local out="$OUT_ROOT/$tag"

  echo
  echo "===== $tag ====="
  build/RISCV/gem5.opt     --outdir="$out"     "$CFG"     --binary "$AUDIT_BIN"     --bp-type "$pred"     --bp-inst-shift "$shift"     --btb-entries 4096

  grep -E '^simTicks|^simInsts|branchPred.*(cond|Cond|mispred|Mispred|incorrect|Incorrect|predict|Predict)'     "$out/stats.txt" >"$out/bpu_stats.txt" || true

  local ticks
  ticks="$(awk '$1=="simTicks" {print $2; exit}' "$out/stats.txt")"
  echo "BPU_CASE_RESULT predictor=$pred shift=$shift simTicks=${ticks:-NA}"
}

echo "[4/5] Tournament + micro-TAGE × RV64 PC-shift matrix"
for pred in tournament micro-tage; do
  for shift in 0 1 2; do
    run_case "$pred" "$shift"
  done
done

echo "[5/5] Verify emitted micro-TAGE configuration"
cfg_ini="$OUT_ROOT/micro-tage_shift1/config.ini"
[[ -f "$cfg_ini" ]] || {
  echo "ERROR: missing config.ini for micro-TAGE shift1" >&2
  exit 3
}

python3 - "$cfg_ini" <<'PY'
import configparser
import sys

path = sys.argv[1]
cp = configparser.ConfigParser(strict=False)
cp.optionxform = str
cp.read(path)

matches = []
for section in cp.sections():
    vals = cp[section]
    if vals.get("nHistoryTables") != "3":
        continue
    if vals.get("minHist") != "8" or vals.get("maxHist") != "64":
        continue
    explicit = vals.get("explicitHistLengths", "")
    tags = vals.get("tagTableTagWidths", "")
    sizes = vals.get("logTagTableSizes", "")
    norm = lambda x: "".join(ch for ch in x if ch.isdigit() or ch == ",")
    if norm(explicit) not in ("8,24,64", "82464"):
        continue
    if norm(tags) not in ("0,8,9,10", "08910"):
        continue
    if norm(sizes) not in ("11,9,9,9", "11999"):
        continue
    matches.append(section)

if len(matches) != 1:
    print("BPU_MICRO_TAGE_CONFIG_GATE=FAIL")
    print("matching_sections=", matches)
    raise SystemExit(4)

print("BPU_MICRO_TAGE_CONFIG_GATE=PASS")
print("micro_tage_section=", matches[0])
PY

echo
echo "BPU_B1_CONFIG_SMOKE=PASS"
echo "BPU_SHIFT_EVIDENCE_SCOPE=$EVIDENCE_SCOPE"
if [[ "$EVIDENCE_SCOPE" == "DIRECTED_SMOKE_ONLY" ]]; then
  echo "BPU_SHIFT_KNEE=NOT_CLAIMED_SMOKE_ONLY"
else
  echo "BPU_SHIFT_KNEE=READY_FOR_ANALYSIS"
fi
