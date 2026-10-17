#!/usr/bin/env bash
# Little v0.52 G0-A-R: verified Embench st+st / cubic+cubic
# Fresh output only; preserves original ELFs and previous G0 evidence.
set -euo pipefail

ROOT="$HOME/gem5-g0-roi-20261016"
EM="$HOME/gem5-g8i-xbar/benchmarks/external/embench-iot"
BD="$EM/bd-rv64-gem5"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
MARKERS="$ROOT/configs/g0_pair_roi_markers.S"
AUDITOR="$ROOT/configs/g0_verify_effective_config.py"
CC="riscv64-linux-gnu-gcc"
OBJDUMP="riscv64-linux-gnu-objdump"
NM="riscv64-linux-gnu-nm"
EXPECTED_HEAD="989abe595b3f71b172e6c17b32dbe2b96a965edf"
OUT="${G0_OUTPUT_DIR:-$HOME/g0-a-r-st-cubic-v2-$(date +%Y%m%d-%H%M%S)}"

for tool in "$CC" "$OBJDUMP" "$NM" sha256sum python3 timeout; do
  command -v "$tool" >/dev/null || { echo "MISSING COMMAND: $tool" >&2; exit 2; }
done
for path in "$GEM5" "$CFG" "$MARKERS" "$AUDITOR"; do
  test -f "$path" || { echo "MISSING INPUT: $path" >&2; exit 2; }
done
test -x "$GEM5"
actual_head="$(git -C "$ROOT" rev-parse HEAD)"
if [ "$actual_head" != "$EXPECTED_HEAD" ]; then
  echo "HEAD MISMATCH: expected=$EXPECTED_HEAD actual=$actual_head" >&2
  exit 2
fi
if [ -e "$OUT" ]; then
  echo "REFUSING TO OVERWRITE: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT/bin"
echo "RESULT_ROOT=$OUT"

{
  echo "G0-A-R ST+CUBIC verified independent real Embench V2"
  echo "gem5_head=$actual_head"
  echo "gem5_status_porcelain_begin"
  git -C "$ROOT" status --porcelain
  echo "gem5_status_porcelain_end"
  "$CC" --version | head -1
  sha256sum "$GEM5" "$CFG" "$MARKERS" "$AUDITOR"
} > "$OUT/provenance.txt"

# Step 1: link app-specific, correctly-labelled guest verification witnesses.
for APP in st cubic; do
  case "$APP" in
    st) SOURCE="$EM/src/st/libst.c" ;;
    cubic) SOURCE="$EM/src/cubic/basicmath_small.c" ;;
  esac
  GOLDEN="$BD/src/$APP/$APP"
  test -f "$SOURCE" || { echo "MISSING SOURCE: $SOURCE" >&2; exit 3; }
  test -f "$GOLDEN" || { echo "MISSING GOLDEN ELF: $GOLDEN" >&2; exit 3; }

  echo "===== BUILD VERIFIED ELF: $APP ====="
  sha256sum "$SOURCE" "$GOLDEN" >> "$OUT/provenance.txt"
  sha256sum "$GOLDEN" > "$OUT/golden-$APP.sha256"

  cat > "$OUT/hooks-$APP.c" <<EOF
#include <stdio.h>

extern void g0_pair_roi_begin(void);
extern void g0_pair_roi_end(void);
extern int __real_verify_benchmark(int result);

void __wrap_start_trigger(void) { g0_pair_roi_begin(); }
void __wrap_stop_trigger(void) { g0_pair_roi_end(); }

int __wrap_verify_benchmark(int result)
{
    int correct = __real_verify_benchmark(result);
    printf("G0_APP_VERIFY program=$APP result=%d correct=%d\\n", result, correct);
    fflush(stdout);
    return correct;
}
EOF
  "$CC" -O2 -fno-lto -march=rv64gc -mabi=lp64d \
    -c "$OUT/hooks-$APP.c" -o "$OUT/hooks-$APP.o"

  mapfile -d '' -t BENCH_OBJS < <(
    find "$BD/src/$APP" -maxdepth 1 -type f -name '*.o' -print0 | sort -z
  )
  mapfile -d '' -t PLATFORM_OBJS < <(
    find "$BD/config/riscv64linux" -type f -name '*.o' -print0 | sort -z
  )
  mapfile -d '' -t SUPPORT_OBJS < <(
    find "$BD/support" -maxdepth 1 -type f -name '*.o' -print0 | sort -z
  )

  if (( ${#BENCH_OBJS[@]} == 0 || ${#PLATFORM_OBJS[@]} == 0 || ${#SUPPORT_OBJS[@]} == 0 )); then
    echo "MISSING EXISTING OBJ SET: $APP (bench/platform/support)" >&2
    exit 3
  fi
  # Avoid nm | grep -q under pipefail: early grep exit can SIGPIPE nm
  # and falsely report a missing strong verifier symbol.
  "$NM" -A --defined-only "${BENCH_OBJS[@]}" > "$OUT/symbols-$APP.txt"
  if ! grep -Eq '[[:space:]]T[[:space:]]verify_benchmark$' "$OUT/symbols-$APP.txt"; then
    echo "STRONG VERIFY SYMBOL MISSING: $APP" >&2
    grep -E 'verify_benchmark' "$OUT/symbols-$APP.txt" >&2 || true
    exit 3
  fi
  sha256sum "${BENCH_OBJS[@]}" "${PLATFORM_OBJS[@]}" "${SUPPORT_OBJS[@]}" \
    "$OUT/hooks-$APP.o" >> "$OUT/provenance.txt"

  "$CC" -static -march=rv64gc -mabi=lp64d \
    -Wl,--wrap=start_trigger \
    -Wl,--wrap=stop_trigger \
    -Wl,--wrap=verify_benchmark \
    -Wl,--gc-sections \
    -Wl,-Map,"$OUT/$APP.map" \
    "${BENCH_OBJS[@]}" \
    "${PLATFORM_OBJS[@]}" \
    "${SUPPORT_OBJS[@]}" \
    "$OUT/hooks-$APP.o" "$MARKERS" -lm \
    -o "$OUT/bin/$APP"

  "$OBJDUMP" -d --disassemble=main "$OUT/bin/$APP" \
    > "$OUT/main-$APP.dis"
  for sym in __wrap_start_trigger __wrap_stop_trigger __wrap_verify_benchmark; do
    grep -Fq "<$sym>" "$OUT/main-$APP.dis" || {
      echo "MAIN DID NOT CALL WRAPPER: app=$APP sym=$sym" >&2
      exit 4
    }
  done
  "$OBJDUMP" -d --disassemble=g0_pair_roi_begin "$OUT/bin/$APP" \
    > "$OUT/marker-begin-$APP.dis"
  "$OBJDUMP" -d --disassemble=g0_pair_roi_end "$OUT/bin/$APP" \
    > "$OUT/marker-end-$APP.dis"
  grep -Fq 'b400007b' "$OUT/marker-begin-$APP.dis" || exit 4
  grep -Fq 'b600007b' "$OUT/marker-end-$APP.dis" || exit 4

  sha256sum -c "$OUT/golden-$APP.sha256"
  sha256sum "$OUT/bin/$APP" "$OUT/hooks-$APP.c" \
    "$OUT/$APP.map" >> "$OUT/provenance.txt"
  echo "G0_APP_LINK_PASS program=$APP"
done

# Step 2: run the 2x2 same-ELF comparisons.
for APP in st cubic; do
  for MODE in private2 shared1; do
    DIR="$OUT/$APP/$MODE"
    mkdir -p "$DIR"
    MODE_ARGS=(--g0-div-mode "$MODE")
    if [ "$MODE" = shared1 ]; then
      MODE_ARGS+=(--pair-shared-div)
    fi
    echo "===== SIMULATION: $APP+$APP / $MODE ====="

    if ! timeout 1800s env \
      LITTLE_G0_AUDIT_FU=1 \
      LITTLE_G0_PAIR_ROI=1 \
      LITTLE_G0_CONSTRUCTED_MANIFEST_PATH="$DIR/constructed_fu_manifest.json" \
      "$GEM5" --outdir="$DIR" "$CFG" \
        --binary "$OUT/bin/$APP" \
        --core-binary "$OUT/bin/$APP" \
        --core-binary "$OUT/bin/$APP" \
        --cores 2 \
        --distributed-iq \
        --local-iq-picker \
        --n-skip -1 \
        --int-steering int1-first \
        --clock 1.4GHz \
        --l2-topology shared4 \
        --div-wake-latency 0 \
        --div-idle-threshold 8 \
        --g0-pair-roi \
        "${MODE_ARGS[@]}" \
      > "$DIR/simulator.log" 2>&1; then
      echo "SIMULATION FAILED OR TIMEOUT: $APP/$MODE" >&2
      tail -80 "$DIR/simulator.log" >&2
      exit 5
    fi

    python3 "$AUDITOR" "$DIR" --mode "$MODE" \
      --json "$DIR/effective_config_audit.json"

    grep -E \
      '^G0_DIV_STRUCTURE_ASSERT|^G0_PAIR_ROI_|^G0_APP_VERIFY|^SIMULATION_EXIT_' \
      "$DIR/simulator.log"

    sha256sum "$DIR/config.ini" "$DIR/stats.txt" \
      "$DIR/simulator.log" "$DIR/effective_config_audit.json" \
      "$DIR/constructed_fu_manifest.json" >> "$OUT/provenance.txt"
  done
done

# Step 3: persist a strict auditor for later independent re-evaluation.
cat > "$OUT/verify_pairs.py" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()


def only(text, pattern, count, context):
    found = re.findall(pattern, text, re.M)
    if len(found) != count:
        raise AssertionError(
            f"{context}: wanted {count} matches, found {len(found)} for {pattern}"
        )
    return found


def load(app, mode):
    directory = root / app / mode
    log = (directory / "simulator.log").read_text(
        encoding="utf-8", errors="replace"
    )
    stats = (directory / "stats.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    ctx = f"{app}/{mode}"
    get = lambda p, n: only(log, p, n, ctx)
    units = 2 if mode == "private2" else 1
    struct = get(rf"^G0_DIV_STRUCTURE_ASSERT: mode={mode}\b.*$", 1)[0]
    assert f"pair_physical_divs_expected={units}" in struct, ctx
    assert "latency=20 II=20 pipelined=False" in struct, ctx
    assert "reactivePowerGating=False" in struct, ctx
    assert "predictiveWakeEnabled=False" in struct, ctx
    assert "powerWakeLatency=0" in struct, ctx
    get(r"^SIMULATION_EXIT_CAUSE=exiting with last active thread context$", 1)
    get(r"^SIMULATION_EXIT_CODE=0$", 1)

    verify = get(
        rf"^G0_APP_VERIFY program={app} result=(-?\d+) correct=(-?\d+)$", 2
    )
    assert all(correct == "1" for _, correct in verify), (ctx, verify)

    ready = get(r"^G0_PAIR_ROI_READY core=([01]) ready_tick=(\d+)$", 2)
    start, r0, r1, period = map(int, get(
        r"^G0_PAIR_ROI_SYNC start_tick=(\d+) "
        r"ready0=(\d+) ready1=(\d+) "
        r"clock_period_ticks=(\d+) early_core_idle_policy=quiesce$", 1
    )[0])
    assert period == 714 and start == max(r0, r1), ctx
    assert {int(c): int(t) for c, t in ready} == {0: r0, 1: r1}, ctx

    finishes = get(
        r"^G0_PAIR_ROI_FINISH core=([01]) "
        r"finish_tick=(\d+) pair_start_tick=(\d+) "
        r"committed_insts=(\d+) committed_intdivs=(\d+)$", 2
    )
    cores = {}
    for c, tick, base, insts, divs in finishes:
        c, tick, base, insts, divs = map(int, (c, tick, base, insts, divs))
        assert c not in cores and base == start and tick > start, ctx
        assert insts > 0 and divs > 0, (ctx, c, insts, divs)
        assert (tick - start) % period == 0, (ctx, c)
        cores[c] = {
            "cycles": (tick - start) // period,
            "tick": tick,
            "committed_insts": insts,
            "committed_intdivs": divs,
        }
    assert set(cores) == {0, 1}, ctx

    ss, f0, f1, ticks, pp, first = map(int, get(
        r"^G0_PAIR_ROI_SUMMARY pair_start_tick=(\d+) "
        r"finish0=(\d+) finish1=(\d+) pair_makespan_ticks=(\d+) "
        r"clock_period_ticks=(\d+) first_finished_core=([01])$", 1
    )[0])
    assert (ss, f0, f1, pp) == (
        start, cores[0]["tick"], cores[1]["tick"], period
    ), ctx
    assert ticks == max(f0, f1) - start and ticks % period == 0, ctx
    assert first == (0 if f0 <= f1 else 1), ctx
    audit = json.loads((directory / "effective_config_audit.json").read_text())
    assert audit["mode"] == mode, ctx
    assert audit["pair_div_physical_units"] == units, ctx
    assert audit["status"] == (
        "G0_A_CONFIG_AND_POWER_DISABLED_VERIFIED_NOT_PERFORMANCE"
    ), ctx

    # Informational whole-process counters only: do not claim ROI stall cycles.
    busy = {}
    for core in (0, 1):
        pattern = (
            rf"^board\.processor\.cores{core}\.core\.statFuBusy::IntDiv\s+(\d+)"
        )
        found = re.findall(pattern, stats, re.M)
        busy[str(core)] = int(found[-1]) if found else None
    return {
        "cores": cores,
        "makespan_cycles": ticks // period,
        "guest_verify": sorted(verify),
        "whole_sim_failed_fu_allocation_attempts": busy,
    }


results = {}
for app in ("st", "cubic"):
    private = load(app, "private2")
    shared = load(app, "shared1")
    assert private["guest_verify"] == shared["guest_verify"], app
    for core in (0, 1):
        p, s = private["cores"][core], shared["cores"][core]
        assert p["committed_insts"] == s["committed_insts"], (app, core)
        assert p["committed_intdivs"] == s["committed_intdivs"], (app, core)
    p, s = private["makespan_cycles"], shared["makespan_cycles"]
    slowdown = 100.0 * (s / p - 1.0)
    throughput_change = 100.0 * (p / s - 1.0)
    print(f"\n========== {app.upper()} + {app.upper()} ==========")
    for c in (0, 1):
        pc = private["cores"][c]
        sc = shared["cores"][c]
        print(
            f"core{c}: private={pc['cycles']:,} shared={sc['cycles']:,} "
            f"committed_insts={pc['committed_insts']:,} "
            f"committed_DIV={pc['committed_intdivs']:,}"
        )
    print(f"PAIR: PRIVATE2={p:,} SHARED1={s:,} extra={s-p:+,} cycles")
    print(f"Slowdown: {slowdown:+.6f}% | Throughput change: {throughput_change:+.6f}%")
    print("Whole-sim FU allocation failures (NOT ROI stall cycles):")
    print("  PRIVATE2", private["whole_sim_failed_fu_allocation_attempts"])
    print("  SHARED1 ", shared["whole_sim_failed_fu_allocation_attempts"])
    print(f"G0_A_R_{app.upper()}_VERIFIED_PAIR_PASS")
    results[app] = {
        "status": "VERIFIED_MATCHED_ROI_PAIR_PASS",
        "private2": private,
        "shared1": shared,
        "slowdown_percent": slowdown,
        "throughput_change_percent": throughput_change,
    }

(root / "real_workload_report.json").write_text(
    json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print("\nG0_A_R_ST_CUBIC_MATCHED_PAIR_PASS")
PY

python3 "$OUT/verify_pairs.py" "$OUT"
sha256sum "$OUT/verify_pairs.py" "$OUT/real_workload_report.json" \
  >> "$OUT/provenance.txt"
echo "RESULT_ROOT=$OUT"
echo "G0_A_R_ST_CUBIC_ALL_PASS"