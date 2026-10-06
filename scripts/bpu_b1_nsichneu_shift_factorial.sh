#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b1_nsichneu_shift_factorial}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
WORKLOAD="nsichneu"
BIN="$EMBENCH_BUILD/src/$WORKLOAD/$WORKLOAD"

echo "[0/4] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/4] Ensure nsichneu binary exists"
if [[ ! -x "$BIN" ]]; then
  bash scripts/rv64_embench_prepare.sh
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
    echo "ERROR: failed to extract first ROI from $src" >&2
    exit 4
  }
}

run_one() {
  local cond="$1"
  local btb="$2"
  local ind="$3"
  local tag="c${cond}_b${btb}_i${ind}"
  local out="$OUT_ROOT/$tag"

  echo "  $tag"
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$BIN"     --bp-type tournament     --bp-inst-shift 1     --bp-cond-shift "$cond"     --bp-btb-shift "$btb"     --bp-indirect-shift "$ind"     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $tag failed" >&2
    cat "$out.stdout" >&2
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/4] Run 2x2x2 shift factorial on nsichneu (8 ROI runs)"
for cond in 1 2; do
  for btb in 1 2; do
    for ind in 1 2; do
      run_one "$cond" "$btb" "$ind"
    done
  done
done

echo "[3/4] Verify config and summarize factorial effects"
python3 - "$OUT_ROOT" <<'PY'
import configparser
import itertools
import math
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])

def find_value(cp, suffix, key):
    hits = []
    for sec in cp.sections():
        if sec.endswith(suffix) and key in cp[sec]:
            hits.append((sec, cp[sec][key]))
    return hits

def read_stats(path):
    vals = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, raw = p[0], p[1]
        try:
            v = float(raw)
        except ValueError:
            continue

        if key == "simTicks":
            vals["simTicks"] = int(v)
        elif key == "simInsts":
            vals["simInsts"] = int(v)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            vals.setdefault("cycles", int(v))
        elif key.endswith(".condPredicted"):
            vals["condPredicted"] = int(v)
        elif key.endswith(".condIncorrect"):
            vals["condIncorrect"] = int(v)
        elif key.endswith(".BTBLookups"):
            vals["BTBLookups"] = int(v)
        elif key.endswith(".BTBHits"):
            vals["BTBHits"] = int(v)
        elif key.endswith(".indirectLookups"):
            vals["indirectLookups"] = int(v)
        elif key.endswith(".indirectHits"):
            vals["indirectHits"] = int(v)
        elif ".mispredictDueToPredictor::DirectCond" in key:
            vals["predDirectCond"] = int(v)
        elif ".mispredictDueToPredictor::IndirectCond" in key:
            vals["predIndirectCond"] = int(v)
        elif ".mispredictDueToBTBMiss::DirectCond" in key:
            vals["btbDirectCond"] = int(v)
        elif ".mispredictDueToBTBMiss::IndirectCond" in key:
            vals["btbIndirectCond"] = int(v)

    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1e12)
    vals["condMPKI"] = vals.get("condIncorrect", 0) / vals["simInsts"] * 1000
    vals["btbHitRate"] = (
        vals.get("BTBHits", 0) / vals["BTBLookups"]
        if vals.get("BTBLookups", 0) else float("nan")
    )
    vals["indHitRate"] = (
        vals.get("indirectHits", 0) / vals["indirectLookups"]
        if vals.get("indirectLookups", 0) else float("nan")
    )
    return vals

data = {}
for c,b,i in itertools.product((1,2),(1,2),(1,2)):
    tag=f"c{c}_b{b}_i{i}"
    out=root/tag
    cp=configparser.ConfigParser(strict=False)
    cp.optionxform=str
    cp.read(out/"config.ini")

    # Verify the effective split-shift wiring in emitted config.
    cond_hits=find_value(cp, ".branchPred.conditionalBranchPred", "instShiftAmt")
    btb_hits=find_value(cp, ".branchPred.btb", "instShiftAmt")
    idx_hits=find_value(cp, ".branchPred.btb.btbIndexingPolicy", "set_shift")
    ind_hits=find_value(cp, ".branchPred.indirectBranchPred", "instShiftAmt")

    def require(hits, expected, label):
        if len(hits) != 1 or int(hits[0][1]) != expected:
            raise SystemExit(
                f"ERROR: {tag} {label} expected {expected}, got {hits}"
            )

    require(cond_hits,c,"conditional shift")
    require(btb_hits,b,"BTB instShiftAmt")
    require(idx_hits,b,"BTB set_shift")
    require(ind_hits,i,"indirect shift")
    data[(c,b,i)] = read_stats(out/"roi.stats")

base=data[(1,1,1)]
print()
print("=== nsichneu split-shift 2x2x2 factorial ===")
print(
    f"{'config':10s} {'cycles':>11s} {'vs111%':>9s} {'condMPKI':>10s} "
    f"{'BTBhit%':>9s} {'Indhit%':>9s} {'PredDC':>9s} {'BTBDC':>9s}"
)
for key in itertools.product((1,2),(1,2),(1,2)):
    d=data[key]
    gap=(d["cycles"]/base["cycles"]-1)*100
    bhr=d["btbHitRate"]*100 if math.isfinite(d["btbHitRate"]) else float("nan")
    ihr=d["indHitRate"]*100 if math.isfinite(d["indHitRate"]) else float("nan")
    print(
        f"c{key[0]}b{key[1]}i{key[2]:1d} "
        f"{d['cycles']:11d} {gap:9.3f} {d['condMPKI']:10.4f} "
        f"{bhr:9.4f} {ihr:9.4f} "
        f"{d.get('predDirectCond',-1):9d} {d.get('btbDirectCond',-1):9d}"
    )

# Main effects averaged geometrically across the other two factors.
print()
print("=== geometric-mean main effects on cycles ===")
for name,pos in (("conditional",0),("BTB",1),("indirect",2)):
    lvl={}
    for level in (1,2):
        vals=[]
        for key,d in data.items():
            if key[pos]==level:
                vals.append(d["cycles"])
        lvl[level]=math.exp(sum(math.log(v) for v in vals)/len(vals))
    ratio=lvl[2]/lvl[1]
    print(
        f"{name:11s}: shift2/shift1 = {ratio:.9f} "
        f"({(ratio-1)*100:+.3f}%)"
    )

# Interaction-focused pairs with other components held at shift1.
for key,label in [
    ((2,1,1),"conditional only"),
    ((1,2,1),"BTB only"),
    ((1,1,2),"indirect only"),
    ((2,2,1),"conditional+BTB"),
    ((2,1,2),"conditional+indirect"),
    ((1,2,2),"BTB+indirect"),
    ((2,2,2),"all shift2"),
]:
    d=data[key]
    print(
        f"{label:20s}: {(d['cycles']/base['cycles']-1)*100:+.3f}% "
        f"cycles, condMPKI={d['condMPKI']:.4f}"
    )

insts={d["simInsts"] for d in data.values()}
if len(insts)!=1:
    raise SystemExit(f"ERROR: simInsts mismatch across factorial: {insts}")

print()
print("BPU_B1_NSICHNEU_SHIFT_FACTORIAL=PASS")
print("BPU_SPLIT_SHIFT_CONFIG_GATE=PASS")
PY

echo "[4/4] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "workload=$WORKLOAD"
  echo "predictor=tournament"
  echo "top_level_bp_inst_shift=1"
  echo "conditional_shifts=1,2"
  echo "btb_shifts=1,2"
  echo "indirect_shifts=1,2"
  echo "btb_entries=4096"
  echo "roi_stats_section=first"
  sha256sum "$BIN" | sed 's/^/binary_sha256=/'
} >"$OUT_ROOT/manifest.txt"

echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B1_NSICHNEU_FACTORIAL_PROVENANCE=PASS"
