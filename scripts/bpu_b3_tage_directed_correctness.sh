#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
CC="${RISCV64_CC:-riscv64-linux-gnu-gcc}"
OBJDUMP="${RISCV64_OBJDUMP:-riscv64-linux-gnu-objdump}"
CROSS_PREFIX="${RISCV64_CROSS_PREFIX:-riscv64-linux-gnu-}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
SRC="$ROOT/benchmarks/src/bpu_tage_rollback_directed.c"
BIN="$ROOT/benchmarks/bin/bpu_tage_rollback_directed"
M5LIB="$ROOT/util/m5/build/riscv/out/libm5.a"
OUT_ROOT="${OUT_ROOT:-bpu_b3_tage_directed_correctness}"

echo "[0/5] Build gem5 and RV64 libm5"
scons build/RISCV/gem5.opt -j"$JOBS"
scons -C util/m5 "riscv.CROSS_COMPILE=$CROSS_PREFIX" build/riscv/out/libm5.a -j"$JOBS"

echo "[1/5] Build deterministic branch-directed RV64 binary"
mkdir -p "$(dirname "$BIN")"
"$CC"   -O2 -static -march=rv64imafd -mabi=lp64d   -fno-if-conversion -fno-if-conversion2   -I"$ROOT/include"   "$SRC" "$M5LIB" -o "$BIN"

file "$BIN"

cond_static="$("$OBJDUMP" -d --disassemble=branch_kernel "$BIN" | awk '
  /^[[:space:]]*[0-9a-f]+:/ {
    m=$3
    if (m ~ /^(beq|bne|blt|bge|bltu|bgeu|beqz|bnez)$/) n++
  }
  END { print n+0 }
')"
echo "DIRECTED_STATIC_CONDITIONAL_BRANCHES=$cond_static"
if (( cond_static < 4 )); then
  echo "ERROR: directed kernel did not retain enough conditional branches" >&2
  exit 3
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1"
  local dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ {
      section++
      if (section == 1) keep=1
    }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst" || {
    echo "ERROR: first ROI extraction failed for $src" >&2
    exit 4
  }
}

run_one() {
  local tag="$1"
  local out="$OUT_ROOT/$tag"
  mkdir -p "$out"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$BIN"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  local rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $tag gem5 exited with rc=$rc" >&2
    echo "----- $tag stdout -----" >&2
    tail -n 200 "$out.stdout" >&2 || true
    echo "----- $tag stderr -----" >&2
    tail -n 200 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $tag benchmark verification failed despite gem5 rc=0" >&2
    echo "----- $tag stdout -----" >&2
    tail -n 200 "$out.stdout" >&2 || true
    echo "----- $tag stderr -----" >&2
    tail -n 200 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/5] Run directed correctness workload twice"
run_one run1
run_one run2

echo "[3/5] Verify history rollback, metadata, exact geometry, determinism"
python3 - "$OUT_ROOT" <<'PY'
import configparser
import pathlib
import sys

root=pathlib.Path(sys.argv[1])

def parse(path):
    s={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        try:
            s[p[0]]=float(p[1])
        except ValueError:
            pass
    return s

def suffix(s,name):
    h=[(k,v) for k,v in s.items() if k.endswith(name)]
    if len(h)!=1:
        raise SystemExit(f"ERROR: suffix {name}: {h}")
    return int(h[0][1])

def config_geometry(path):
    cp=configparser.ConfigParser(strict=False)
    cp.optionxform=str
    cp.read(path)
    hits=[sec for sec in cp.sections()
          if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(hits)!=1:
        raise SystemExit(f"ERROR: TAGE config sections {hits}")
    sec=cp[hits[0]]
    def vec(k):
        return [int(x) for x in sec[k].replace("[","").replace("]","").replace(","," ").split()]
    return {
        "n":int(sec["nHistoryTables"]),
        "hist":vec("explicitHistLengths"),
        "tags":vec("tagTableTagWidths"),
        "logs":vec("logTagTableSizes"),
        "instShift":int(sec["instShiftAmt"]),
    }

rows=[]
for tag in ("run1","run2"):
    s=parse(root/tag/"roi.stats")
    rec=suffix(s,"historyStateRecords")
    restores=suffix(s,"historyStateRestores")
    checks=suffix(s,"historyRestoreChecks")
    metadata=suffix(s,"predictionMetadataChecks")
    committed=suffix(s,"committedConditionalPredictions")
    wrong=suffix(s,"committedConditionalWrong")
    storage=suffix(s,"storageBits")
    simticks=suffix(s,"simTicks")
    siminsts=suffix(s,"simInsts")

    if rec <= 0:
        raise SystemExit(f"ERROR {tag}: no history snapshots recorded")
    if restores <= 0:
        raise SystemExit(f"ERROR {tag}: no speculative history restores observed")
    if checks != restores:
        raise SystemExit(
            f"ERROR {tag}: restore checks {checks} != restores {restores}"
        )
    if metadata != committed:
        raise SystemExit(
            f"ERROR {tag}: metadata checks {metadata} != committed {committed}"
        )
    if wrong <= 0:
        raise SystemExit(f"ERROR {tag}: directed workload caused no TAGE misses")
    if storage != 24166:
        raise SystemExit(f"ERROR {tag}: storage {storage} != 24166")

    geom=config_geometry(root/tag/"config.ini")
    expected={
        "n":3,
        "hist":[8,24,64],
        "tags":[0,8,9,10],
        "logs":[11,9,9,9],
        "instShift":1,
    }
    if geom != expected:
        raise SystemExit(f"ERROR {tag}: geometry {geom} != {expected}")

    rows.append((simticks,siminsts,rec,restores,checks,metadata,committed,wrong,storage))

print("run,simTicks,simInsts,histRecords,histRestores,restoreChecks,metadataChecks,committedCond,tageWrong,storageBits")
for i,r in enumerate(rows,1):
    print("run%d,%s" % (i, ",".join(str(x) for x in r)))

if rows[0] != rows[1]:
    raise SystemExit(
        "ERROR: two identical directed runs are not deterministic:\n"
        f"  run1={rows[0]}\n  run2={rows[1]}"
    )

print()
print("BPU_B3_HISTORY_ROLLBACK_CHECK=PASS")
print("BPU_B3_PREDICTION_METADATA_CHECK=PASS")
print("BPU_B3_EXACT_GEOMETRY_CHECK=PASS")
print("BPU_B3_DETERMINISM_CHECK=PASS")
print("BPU_B3_DIRECTED_CORRECTNESS=PASS")
PY

echo "[4/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "directed_source_sha256=$(sha256sum "$SRC" | awk '{print $1}')"
  echo "directed_binary_sha256=$(sha256sum "$BIN" | awk '{print $1}')"
  echo "compiler=$("$CC" --version | head -n 1)"
  echo "predictor=micro-tage"
  echo "conditional_shift=1"
  echo "btb_shift=2"
  echo "indirect_shift=1"
  echo "history_lengths=8,24,64"
  echo "tag_widths=8,9,10"
  echo "tagged_entries_per_table=512"
  echo "bimodal_entries=2048"
  echo "persistent_storage_bits=24166"
  echo "static_conditional_branches=$cond_static"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B3_DIRECTED_CORRECTNESS_PROVENANCE=PASS"
