#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4b_iso_budget_geometry}"
MICRO_A1="${MICRO_A1:-bpu_b4a1_tagged_entries_sweep}"
MICRO_2048="${MICRO_2048:-bpu_b4a1_extension_2048}"
STOCK_ROOT="${STOCK_ROOT:-bpu_b4b_stock_tage_six}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(statemate crc32 nsichneu slre sglib-combined qrduino)
PROFILES=(tage5-iso45k tage7-iso65k)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify existing evidence and binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR: missing binary $w" >&2; exit 2; }
  [[ -f "$MICRO_A1/$w/e1024/roi.stats" ]] || { echo "ERROR: missing micro1024 $w" >&2; exit 2; }
  [[ -f "$MICRO_2048/$w/e2048/roi.stats" ]] || { echo "ERROR: missing micro2048 $w" >&2; exit 2; }
  [[ -f "$STOCK_ROOT/$w/roi.stats" ]] || { echo "ERROR: missing stock TAGE $w" >&2; exit 2; }
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

echo "[2/5] Run two budget-normalized TAGE profiles x six workloads (12 ROI)"
for p in "${PROFILES[@]}"; do
  for w in "${WORKLOADS[@]}"; do
    out="$OUT_ROOT/$p/$w"; mkdir -p "$out"
    echo "  $w / $p"
    set +e
    "$GEM5" --outdir="$out" "$CFG"       --binary "$EMBENCH_BUILD/src/$w/$w"       --bp-type "$p"       --bp-inst-shift 1 --bp-cond-shift 1 --bp-btb-shift 2 --bp-indirect-shift 1       --btb-entries 4096       >"$out.stdout" 2>"$out.stderr"
    rc=$?
    set -e
    if (( rc != 0 )); then
      echo "ERROR: $w/$p rc=$rc" >&2
      tail -n 180 "$out.stdout" >&2 || true
      tail -n 180 "$out.stderr" >&2 || true
      exit "$rc"
    fi
    grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
      tail -n 180 "$out.stdout" >&2 || true
      tail -n 180 "$out.stderr" >&2 || true
      exit 5
    }
    extract_first_roi "$out/stats.txt" "$out/roi.stats"
  done
done

echo "[3/5] Validate exact geometry/storage and summarize"
python3 - "$OUT_ROOT" "$MICRO_A1" "$MICRO_2048" "$STOCK_ROOT" <<'PY'
import configparser, csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1])
ma1=pathlib.Path(sys.argv[2])
m2048=pathlib.Path(sys.argv[3])
stock=pathlib.Path(sys.argv[4])

workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]

expected={
 "tage5-iso45k":{
   "bits":45736,
   "tables":5,
   "hist":[5,11,25,58,130],
   "tags":[0,8,8,9,10,10],
   "logs":[11,9,9,10,9,9],
 },
 "tage7-iso65k":{
   "bits":65192,
   "tables":7,
   "hist":[5,9,15,25,44,76,130],
   "tags":[0,9,9,10,10,11,11,12],
   "logs":[11,9,9,9,10,9,9,9],
 },
}

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

def cyc(s):
    return round(one(s,"simTicks")*1.4e9/1e12)

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))

D={p:{} for p in expected}

for p,e in expected.items():
    for w in workloads:
        out=root/p/w
        s=parse(out/"roi.stats")
        cp=configparser.ConfigParser(strict=False); cp.optionxform=str
        cp.read(out/"config.ini")
        hs=[sec for sec in cp.sections() if sec.endswith(".branchPred.conditionalBranchPred.tage")]
        if len(hs)!=1: raise SystemExit(f"ERROR {p}/{w}: TAGE sections={hs}")
        sec=cp[hs[0]]
        if int(sec["nHistoryTables"]) != e["tables"]:
            raise SystemExit(f"ERROR {p}/{w}: table count")
        if vec(sec["explicitHistLengths"]) != e["hist"]:
            raise SystemExit(f"ERROR {p}/{w}: histories")
        if vec(sec["tagTableTagWidths"]) != e["tags"]:
            raise SystemExit(f"ERROR {p}/{w}: tags")
        if vec(sec["logTagTableSizes"]) != e["logs"]:
            raise SystemExit(f"ERROR {p}/{w}: sizes")
        if int(sec["fixedIndexHashLogSize"]) != 0:
            raise SystemExit(f"ERROR {p}/{w}: must use native indexing")
        if int(one(s,"storageBits")) != e["bits"]:
            raise SystemExit(f"ERROR {p}/{w}: storage")
        committed=int(one(s,"committedConditionalPredictions"))
        if int(one(s,"predictionMetadataChecks")) != committed:
            raise SystemExit(f"ERROR {p}/{w}: metadata checks")
        if int(one(s,"historyRestoreChecks")) != int(one(s,"historyStateRestores")):
            raise SystemExit(f"ERROR {p}/{w}: rollback checks")
        inst=int(one(s,"simInsts"))
        wrong=int(one(s,"committedConditionalWrong"))
        D[p][w]={
          "cycles":cyc(s),
          "mpki":1000*wrong/inst,
          "inst":inst,
          "cond":committed,
        }

refs={}
for w in workloads:
    refs[w]={
      "micro1024":cyc(parse(ma1/w/"e1024"/"roi.stats")),
      "stock":cyc(parse(stock/w/"roi.stats")),
      "micro2048":cyc(parse(m2048/w/"e2048"/"roi.stats")),
    }

print()
print("=== BPU-4B budget-normalized geometry audit ===")
print("G5 state = 45,736 bits; micro1024 = 45,670 bits (+66 bits)")
print("G7 state = 65,192 bits; stock TAGE = 65,192 bits (exact)")
print()
print(f"{'workload':18s} {'m3-45K':>10s} {'G5-45K':>10s} {'stock65K':>10s} {'G7-65K':>10s} {'m3-89K':>10s}")
for w in workloads:
    print(
      f"{w:18s} "
      f"{refs[w]['micro1024']:10d} "
      f"{D['tage5-iso45k'][w]['cycles']:10d} "
      f"{refs[w]['stock']:10d} "
      f"{D['tage7-iso65k'][w]['cycles']:10d} "
      f"{refs[w]['micro2048']:10d}"
    )

comparisons=[
 ("G5/micro1024","tage5-iso45k","micro1024"),
 ("G7/stock","tage7-iso65k","stock"),
 ("G5/stock","tage5-iso45k","stock"),
 ("G7/micro1024","tage7-iso65k","micro1024"),
 ("G7/micro2048","tage7-iso65k","micro2048"),
]

print()
print("=== geomean ratios ===")
for label,p,ref in comparisons:
    r=gm([D[p][w]["cycles"]/refs[w][ref] for w in workloads])
    print(f"{label:20s} = {r:.9f} ({(r-1)*100:+.5f}%)")

print()
print("=== internal TAGE MPKI for new profiles ===")
print(f"{'workload':18s} {'G5 MPKI':>10s} {'G7 MPKI':>10s}")
for w in workloads:
    print(f"{w:18s} {D['tage5-iso45k'][w]['mpki']:10.4f} {D['tage7-iso65k'][w]['mpki']:10.4f}")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","micro1024Cycles","g5Cycles","g5MPKI","stockCycles","g7Cycles","g7MPKI","micro2048Cycles"])
    for w in workloads:
        wr.writerow([
          w,refs[w]["micro1024"],D["tage5-iso45k"][w]["cycles"],
          f"{D['tage5-iso45k'][w]['mpki']:.9f}",
          refs[w]["stock"],D["tage7-iso65k"][w]["cycles"],
          f"{D['tage7-iso65k'][w]['mpki']:.9f}",
          refs[w]["micro2048"],
        ])

print()
print("BPU_B4B_ISO_BUDGET_GEOMETRY_GATE=PASS")
print("BPU_B4B_ISO_BUDGET_STORAGE_GATE=PASS")
print("BPU_B4B_ISO_BUDGET_CORRECTNESS_GATE=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-4B_budget_normalized_geometry"
  echo "G5_bits=45736"
  echo "G5_histories=5,11,25,58,130"
  echo "G5_tags=8,8,9,10,10"
  echo "G5_tagged_entries=512,512,1024,512,512"
  echo "G7_bits=65192"
  echo "G7_histories=5,9,15,25,44,76,130"
  echo "G7_tags=9,9,10,10,11,11,12"
  echo "G7_tagged_entries=512,512,512,1024,512,512,512"
  echo "condition=cond1,btb2,indirect1,btb4096_direct_proxy"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4B_ISO_BUDGET_PROVENANCE=PASS"
