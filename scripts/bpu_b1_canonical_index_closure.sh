#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b1_canonical_index_closure}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  aha-mont64 crc32 cubic edn huffbench matmult-int minver nbody
  nettle-aes nettle-sha256 nsichneu picojpeg qrduino sglib-combined
  slre st statemate ud wikisort
)

# A: historical RV64 split-equivalent baseline
# B: proposed canonical proxy condition: architectural cond/indirect shift1,
#    BTB set/index shift2
# C: same BTB condition, but conditional predictor shift2 sensitivity
MODES=(base btb2 cond2)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Ensure exact RV64 Embench binaries exist"
missing=0
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || missing=1
done
if (( missing )); then
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
  local workload="$1"
  local mode="$2"
  local cond btb ind

  case "$mode" in
    base)  cond=1; btb=1; ind=1 ;;
    btb2)  cond=1; btb=2; ind=1 ;;
    cond2) cond=2; btb=2; ind=1 ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/$mode"

  echo "  $workload / $mode (c$cond b$btb i$ind)"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type tournament     --bp-inst-shift 1     --bp-cond-shift "$cond"     --bp-btb-shift "$btb"     --bp-indirect-shift "$ind"     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $workload/$mode failed benchmark verification" >&2
    cat "$out.stdout" >&2
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/5] Run 19-workload indexing closure (57 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  for mode in "${MODES[@]}"; do
    run_one "$w" "$mode"
  done
done

echo "[3/5] Verify emitted split-shift config"
python3 - "$OUT_ROOT" <<'PY'
import configparser
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
expected = {
    "base":  (1,1,1),
    "btb2":  (1,2,1),
    "cond2": (2,2,1),
}

sample = "nsichneu"
for mode, (c,b,i) in expected.items():
    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str
    cp.read(root / sample / mode / "config.ini")

    def one(suffix, key):
        hits=[(sec,cp[sec][key]) for sec in cp.sections()
              if sec.endswith(suffix) and key in cp[sec]]
        if len(hits) != 1:
            raise SystemExit(f"ERROR: {mode} {suffix}.{key}: {hits}")
        return int(hits[0][1])

    got_c = one(".branchPred.conditionalBranchPred", "instShiftAmt")
    got_b = one(".branchPred.btb", "instShiftAmt")
    got_bs = one(".branchPred.btb.btbIndexingPolicy", "set_shift")
    got_i = one(".branchPred.indirectBranchPred", "instShiftAmt")

    if (got_c, got_b, got_bs, got_i) != (c,b,b,i):
        raise SystemExit(
            f"ERROR: {mode} split shift mismatch: "
            f"got {(got_c,got_b,got_bs,got_i)} expected {(c,b,b,i)}"
        )

print("BPU_CANONICAL_INDEX_CONFIG_GATE=PASS")
PY

echo "[4/5] Summarize corpus effects and select future sweep subset"
python3 - "$OUT_ROOT" <<'PY'
import csv
import math
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
workloads=[
 "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver","nbody",
 "nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino","sglib-combined",
 "slre","st","statemate","ud","wikisort"
]
modes=["base","btb2","cond2"]

def read_stats(path):
    d={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        k,v=p[0],p[1]
        try: x=float(v)
        except ValueError: continue
        if k=="simTicks": d["simTicks"]=int(x)
        elif k=="simInsts": d["simInsts"]=int(x)
        elif k.endswith(".numCycles") and "cores0.core" in k:
            d.setdefault("cycles",int(x))
        elif k.endswith(".condPredicted"): d["condPredicted"]=int(x)
        elif k.endswith(".condIncorrect"): d["condIncorrect"]=int(x)
        elif k.endswith(".BTBLookups"): d["BTBLookups"]=int(x)
        elif k.endswith(".BTBHits"): d["BTBHits"]=int(x)

    req=["simTicks","simInsts","condPredicted","condIncorrect"]
    miss=[k for k in req if k not in d]
    if miss: raise RuntimeError(f"{path}: missing {miss}")
    if "cycles" not in d:
        d["cycles"]=round(d["simTicks"]*1.4e9/1e12)
    d["condMPKI"]=d["condIncorrect"]/d["simInsts"]*1000.0
    d["condPKI"]=d["condPredicted"]/d["simInsts"]*1000.0
    d["BTBHitRate"]=(d.get("BTBHits",0)/d["BTBLookups"]
                     if d.get("BTBLookups",0) else float("nan"))
    return d

D={w:{m:read_stats(root/w/m/"roi.stats") for m in modes} for w in workloads}

for w in workloads:
    if len({D[w][m]["simInsts"] for m in modes}) != 1:
        raise SystemExit(f"ERROR: simInsts mismatch for {w}")

print()
print("=== BPU-1 canonical indexing closure ===")
print(f"{'workload':18s} {'base':>11s} {'btb2':>11s} {'cond2':>11s} {'btb2/base%':>11s} {'cond2/btb2%':>13s} {'MPKI base':>10s} {'MPKI btb2':>10s}")
for w in workloads:
    a,b,c=D[w]["base"],D[w]["btb2"],D[w]["cond2"]
    gb=(b["cycles"]/a["cycles"]-1)*100
    gc=(c["cycles"]/b["cycles"]-1)*100
    print(f"{w:18s} {a['cycles']:11d} {b['cycles']:11d} {c['cycles']:11d} {gb:11.4f} {gc:13.4f} {a['condMPKI']:10.4f} {b['condMPKI']:10.4f}")

def gm_ratio(num_mode,den_mode,ws=workloads):
    rs=[D[w][num_mode]["cycles"]/D[w][den_mode]["cycles"] for w in ws]
    return math.exp(sum(math.log(r) for r in rs)/len(rs))

r_btb=gm_ratio("btb2","base")
r_cond=gm_ratio("cond2","btb2")
r_btb_no_ns=gm_ratio("btb2","base",[w for w in workloads if w!="nsichneu"])

print()
print(f"btb2/base geomean:      {r_btb:.9f} ({(r_btb-1)*100:+.5f}%)")
print(f"btb2/base excl nsichneu:{r_btb_no_ns:.9f} ({(r_btb_no_ns-1)*100:+.5f}%)")
print(f"cond2/btb2 geomean:     {r_cond:.9f} ({(r_cond-1)*100:+.5f}%)")

wins=sum(D[w]["btb2"]["cycles"]<D[w]["base"]["cycles"] for w in workloads)
loss=sum(D[w]["btb2"]["cycles"]>D[w]["base"]["cycles"] for w in workloads)
tie=len(workloads)-wins-loss
print(f"btb2 wins/losses/ties: {wins}/{loss}/{tie}")

# Freeze future geometry subset from the canonical proxy condition (btb2).
# Rank by committed conditional misprediction MPKI as an empirical branch-pressure
# proxy, while retaining the caveat that condIncorrect includes target-side misses.
ranked=sorted(workloads,key=lambda w:(D[w]["btb2"]["condMPKI"],w))
low=ranked[:2]
mid=ranked[len(ranked)//2-1:len(ranked)//2+1]
high=ranked[-2:]
subset=low+mid+high

print()
print("=== canonical-condition future geometry subset ===")
for role,ws in (("low",low),("mid",mid),("high",high)):
    for w in ws:
        d=D[w]["btb2"]
        print(f"{role:4s} {w:18s} condMPKI={d['condMPKI']:.6f} cond/kI={d['condPKI']:.6f}")
print("BPU_SWEEP_SUBSET="+",".join(subset))

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","mode","cycles","simTicks","simInsts","condPredicted","condIncorrect","condMPKI","condPKI","BTBLookups","BTBHits","BTBHitRate"])
    for w in workloads:
        for m in modes:
            d=D[w][m]
            wr.writerow([w,m,d["cycles"],d["simTicks"],d["simInsts"],d["condPredicted"],d["condIncorrect"],f"{d['condMPKI']:.9f}",f"{d['condPKI']:.9f}",d.get("BTBLookups",""),d.get("BTBHits",""),f"{d['BTBHitRate']:.9f}" if math.isfinite(d["BTBHitRate"]) else ""])

with (root/"sweep_subset.txt").open("w") as f:
    f.write("selection_condition=TournamentBP_condShift1_BTBshift2_indirectShift1\n")
    f.write("selection_metric=committed_condIncorrect_per_kilo_instruction\n")
    f.write("selection_rule=2_low+2_median+2_high\n")
    f.write("workloads="+",".join(subset)+"\n")

print()
print("BPU_B1_CANONICAL_INDEX_CLOSURE=PASS")
print("BPU_SWEEP_SUBSET_REFREEZE=PASS")
PY

echo "[5/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "predictor=tournament"
  echo "base=c1_b1_i1"
  echo "canonical_candidate=c1_b2_i1"
  echo "conditional_sensitivity=c2_b2_i1"
  echo "btb_entries=4096"
  echo "roi_stats_section=first"
  "${RISCV64_CC:-riscv64-linux-gnu-gcc}" --version | head -n 1 | sed 's/^/compiler=/'
  for w in "${WORKLOADS[@]}"; do
    bin="$EMBENCH_BUILD/src/$w/$w"
    echo "$w=$(sha256sum "$bin" | awk '{print $1}')"
  done
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Subset: $OUT_ROOT/sweep_subset.txt"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B1_CANONICAL_INDEX_PROVENANCE=PASS"
