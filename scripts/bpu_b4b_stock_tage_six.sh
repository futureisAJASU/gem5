#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4b_stock_tage_six}"
MICRO_A1="${MICRO_A1:-bpu_b4a1_tagged_entries_sweep}"
MICRO_2048="${MICRO_2048:-bpu_b4a1_extension_2048}"
TOURN_ROOT="${TOURN_ROOT:-bpu_b1_canonical_index_closure}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(statemate crc32 nsichneu slre sglib-combined qrduino)
EXPECTED_STOCK_BITS=65192

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify comparison evidence and binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR: missing binary $w" >&2; exit 2; }
  [[ -f "$MICRO_A1/$w/e1024/roi.stats" ]] || { echo "ERROR: missing micro e1024 $w" >&2; exit 2; }
  [[ -f "$MICRO_2048/$w/e2048/roi.stats" ]] || { echo "ERROR: missing micro e2048 $w" >&2; exit 2; }
  [[ -f "$TOURN_ROOT/$w/btb2/roi.stats" ]] || { echo "ERROR: missing Tournament canonical $w" >&2; exit 2; }
done

rm -rf "$OUT_ROOT"; mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1" dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ { section++; if (section == 1) keep=1 }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst" || exit 4
}

echo "[2/5] Run stock gem5 TAGE on frozen six-workload condition"
for w in "${WORKLOADS[@]}"; do
  out="$OUT_ROOT/$w"; mkdir -p "$out"
  echo "  $w / stock TAGE"
  set +e
  "$GEM5" --outdir="$out" "$CFG"     --binary "$EMBENCH_BUILD/src/$w/$w"     --bp-type tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e
  if (( rc != 0 )); then
    echo "ERROR: $w stock TAGE rc=$rc" >&2
    tail -n 180 "$out.stdout" >&2 || true
    tail -n 180 "$out.stderr" >&2 || true
    exit "$rc"
  fi
  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || { tail -n 180 "$out.stdout" >&2; exit 5; }
  extract_first_roi "$out/stats.txt" "$out/roi.stats"
done

echo "[3/5] Validate stock geometry and compare against existing candidates"
python3 - "$OUT_ROOT" "$MICRO_A1" "$MICRO_2048" "$TOURN_ROOT" "$EXPECTED_STOCK_BITS" <<'PY'
import configparser, csv, math, pathlib, sys
root=pathlib.Path(sys.argv[1]); ma1=pathlib.Path(sys.argv[2]); m2048=pathlib.Path(sys.argv[3]); tourn=pathlib.Path(sys.argv[4]); expected=int(sys.argv[5])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]

def parse(path):
    s={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try: s[p[0]]=float(p[1])
        except ValueError: pass
    return s
def one(s,suf):
    h=[v for k,v in s.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError(f"{suf}: {h}")
    return h[0]
def vec(x):
    return [int(y) for y in x.replace("[","").replace("]","").replace(","," ").split()]
def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))
def cyc(s):
    return round(one(s,"simTicks")*1.4e9/1e12)

D={}
for w in workloads:
    out=root/w
    s=parse(out/"roi.stats")
    cp=configparser.ConfigParser(strict=False); cp.optionxform=str; cp.read(out/"config.ini")
    hs=[sec for sec in cp.sections() if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(hs)!=1: raise SystemExit(f"ERROR {w}: stock TAGE config sections={hs}")
    sec=cp[hs[0]]
    if int(sec["nHistoryTables"]) != 7: raise SystemExit(f"ERROR {w}: nHistoryTables")
    if int(sec["minHist"]) != 5 or int(sec["maxHist"]) != 130: raise SystemExit(f"ERROR {w}: min/max history")
    if vec(sec["tagTableTagWidths"]) != [0,9,9,10,10,11,11,12]:
        raise SystemExit(f"ERROR {w}: tag widths")
    if vec(sec["logTagTableSizes"]) != [13,9,9,9,9,9,9,9]:
        raise SystemExit(f"ERROR {w}: table sizes")
    if int(sec["fixedIndexHashLogSize"]) != 0: raise SystemExit(f"ERROR {w}: fixed hash must be 0")
    bits=int(one(s,"storageBits"))
    if bits != expected: raise SystemExit(f"ERROR {w}: storage={bits}, expected={expected}")
    committed=int(one(s,"committedConditionalPredictions"))
    if int(one(s,"predictionMetadataChecks")) != committed:
        raise SystemExit(f"ERROR {w}: metadata checks")
    if int(one(s,"historyRestoreChecks")) != int(one(s,"historyStateRestores")):
        raise SystemExit(f"ERROR {w}: rollback checks")
    inst=int(one(s,"simInsts")); wrong=int(one(s,"committedConditionalWrong"))
    D[w]={
      "stock_cycles":cyc(s),
      "stock_mpki":1000*wrong/inst,
      "inst":inst,
      "cond":committed,
      "micro1024":cyc(parse(ma1/w/"e1024"/"roi.stats")),
      "micro2048":cyc(parse(m2048/w/"e2048"/"roi.stats")),
      "tourn":cyc(parse(tourn/w/"btb2"/"roi.stats")),
    }

print()
print("=== BPU-4B stock gem5 TAGE audit ===")
print(f"stock exact persistent state = {expected} bits = {expected/8192:.4f} KiB")
print("geometry: base8192 + 7x512 tagged, minHist=5 maxHist=130")
print()
print(f"{'workload':18s} {'Tournament':>11s} {'micro1024':>11s} {'stockTAGE':>11s} {'micro2048':>11s} {'stock MPKI':>11s} {'simInsts':>11s} {'cond':>11s}")
for w in workloads:
    d=D[w]
    print(f"{w:18s} {d['tourn']:11d} {d['micro1024']:11d} {d['stock_cycles']:11d} {d['micro2048']:11d} {d['stock_mpki']:11.4f} {d['inst']:11d} {d['cond']:11d}")

for label,key in [("Tournament","tourn"),("micro1024","micro1024"),("micro2048","micro2048")]:
    ratio=gm([D[w]["stock_cycles"]/D[w][key] for w in workloads])
    print(f"stockTAGE/{label} geomean = {ratio:.9f} ({(ratio-1)*100:+.5f}%)")

ratio12=gm([D[w]["micro1024"]/D[w]["stock_cycles"] for w in workloads])
ratio20=gm([D[w]["micro2048"]/D[w]["stock_cycles"] for w in workloads])
print(f"micro1024/stockTAGE geomean = {ratio12:.9f} ({(ratio12-1)*100:+.5f}%)")
print(f"micro2048/stockTAGE geomean = {ratio20:.9f} ({(ratio20-1)*100:+.5f}%)")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","simInsts","committedConditionals","tournamentCycles","micro1024Cycles","stockTageCycles","stockTageMPKI","micro2048Cycles"])
    for w in workloads:
        d=D[w]
        wr.writerow([w,d["inst"],d["cond"],d["tourn"],d["micro1024"],d["stock_cycles"],f"{d['stock_mpki']:.9f}",d["micro2048"]])

print()
print("BPU_B4B_STOCK_TAGE_GEOMETRY=PASS")
print("BPU_B4B_STOCK_TAGE_STORAGE=PASS")
print("BPU_B4B_STOCK_TAGE_CORRECTNESS=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "baseline=gem5_stock_TAGE"
  echo "stock_geometry=base8192,7x512_tagged,minHist5,maxHist130"
  echo "expected_storage_bits=$EXPECTED_STOCK_BITS"
  echo "condition=cond1,btb2,indirect1,btb4096_direct_proxy"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4B_STOCK_TAGE_PROVENANCE=PASS"
