#!/usr/bin/env bash
# G0-A 2-core RV64 DIV matched-comparator pilot; run from a gem5 worktree.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${GEM5_BIN:-$ROOT/build/RISCV/gem5.opt}"
CC="${G0_RV64_CC:-riscv64-linux-gnu-gcc}"
OBJDUMP="${G0_RV64_OBJDUMP:-riscv64-linux-gnu-objdump}"
SRC="$ROOT/configs/g0_div_directed.c"
PY="$ROOT/configs/02_little_v052_rv64_proxy.py"
OUT="${G0_OUTPUT_DIR:-$HOME/little-v052-g0-a-$(date +%Y%m%d-%H%M%S)-$$}"
[[ -x "$BIN" ]] || { echo "Missing gem5 binary $BIN. Build with: scons build/RISCV/gem5.opt -j4" >&2; exit 2; }
command -v "$CC" >/dev/null || { echo "Missing RV64 compiler $CC" >&2; exit 2; }
command -v "$OBJDUMP" >/dev/null || { echo "Missing RV64 objdump $OBJDUMP" >&2; exit 2; }
[[ -f "$PY" && -f "$SRC" ]] || { echo "Missing G0 config/source" >&2; exit 2; }
[[ ! -e "$OUT" ]] || { echo "Refusing to overwrite existing $OUT" >&2; exit 2; }
mkdir -p "$OUT/bin"
{
  echo "G0-A PILOT - NOT A FULL PERFORMANCE ACCEPTANCE"
  echo "gem5_head=$(git -C "$ROOT" rev-parse HEAD)"
  echo "gem5_dirty=$(git -C "$ROOT" status --porcelain | wc -l)"
  echo "gem5_binary=$BIN"
  sha256sum "$BIN" "$PY" "$SRC"
  "$CC" --version | head -1
  echo "gem5_version_cli=UNSUPPORTED_use_sha256_and_git_head"
} > "$OUT/manifest.txt"
for kind in heavy sparse; do
  every=1
  [[ "$kind" == "sparse" ]] && every=16
  "$CC" -static -O2 -march=rv64imafd -mabi=lp64d \
    -DG0_DIV_EVERY="$every" -DG0_ITERATIONS="${G0_ITERATIONS:-3072}" \
    "$SRC" -o "$OUT/bin/$kind"
  sha256sum "$OUT/bin/$kind" >> "$OUT/manifest.txt"
  "$OBJDUMP" -d "$OUT/bin/$kind" > "$OUT/$kind.dis"
  grep -Eq '[[:space:]](divu|remu)[[:space:]]' "$OUT/$kind.dis" || {
    echo "No RV64 DIVU/REMU in $kind ELF; pilot invalid" >&2; exit 3;
  }
done
COMMON=(
  --cores 2 --distributed-iq --local-iq-picker --n-skip -1
  --int-steering int1-first --clock 1.4GHz
  --div-wake-latency 0 --div-idle-threshold 8
  --l2-topology shared4
)
for pair in heavy_sparse sparse_heavy heavy_heavy sparse_sparse; do
  first="${pair%%_*}"; second="${pair#*_}"
  for mode in private2 shared1; do
    mode_args=(--g0-div-mode "$mode")
    [[ "$mode" == "shared1" ]] && mode_args+=(--pair-shared-div)
    outdir="$OUT/$pair/$mode"
    mkdir -p "$outdir"
    LITTLE_G0_AUDIT_FU=1 \
    LITTLE_G0_CONSTRUCTED_MANIFEST_PATH="$outdir/constructed_fu_manifest.json" \
      "$BIN" --outdir="$outdir" "$PY" \
      --binary "$OUT/bin/$first" \
      --core-binary "$OUT/bin/$first" \
      --core-binary "$OUT/bin/$second" \
      "${COMMON[@]}" "${mode_args[@]}" \
      >"$outdir/simulator.log" 2>&1 || {
        echo "FAIL gem5 $pair $mode; check $outdir/simulator.log" >&2; exit 4;
      }
    grep -q "G0_DIV_STRUCTURE_ASSERT: mode=$mode" "$outdir/simulator.log" || {
      echo "FAIL structure assertion absent: $pair $mode" >&2; exit 5;
    }
    grep -q 'SIMULATION_EXIT_CODE=0' "$outdir/simulator.log" || {
      echo "FAIL exit code: $pair $mode" >&2; exit 6;
    }
    grep 'G0_RESULT every=' "$outdir/simulator.log" | sort > "$outdir/checksums.txt"
    [[ "$(wc -l < "$outdir/checksums.txt")" -eq 2 ]] || {
      echo "FAIL expected 2 G0_RESULT lines: $pair $mode" >&2; exit 7;
    }
    [[ -s "$outdir/config.ini" && -s "$outdir/stats.txt" ]] || {
      echo "FAIL missing config.ini or stats.txt: $pair $mode" >&2; exit 8;
    }
    python3 "$ROOT/configs/g0_verify_effective_config.py" \
      "$outdir" --mode "$mode" --json "$outdir/effective_config_audit.json" \
      | tee "$outdir/effective_config_gate.log"
    sha256sum "$outdir/config.ini" "$outdir/stats.txt" \
      "$outdir/constructed_fu_manifest.json" \
      "$outdir/effective_config_audit.json" >> "$OUT/manifest.txt"
  done
  diff -u "$OUT/$pair/private2/checksums.txt" "$OUT/$pair/shared1/checksums.txt" || {
    echo "FAIL functional checksums diverged for $pair" >&2; exit 9;
  }
  echo "PILOT FUNCTIONAL PASS $pair (not quantitative acceptance)" | tee -a "$OUT/manifest.txt"
done
python3 "$ROOT/configs/g0_summarize_div_pilot.py" "$OUT" --csv "$OUT/summary.csv" > "$OUT/summary_stdout.csv"
echo "G0_A_PILOT_COMPLETED: $OUT"
echo "G0_A_PILOT_SUMMARY: $OUT/summary.csv (full-process ticks only)"
echo "G0_A_CONSTRUCTION_AND_WAKE_GATE: audited from config.ini, C++ inventory and stats"
echo "OPEN: synchronized ROI, per-core completion/pair makespan, dynamic op counts, contention, NoFreeFU and wait counters; no accepted performance slowdown yet"
