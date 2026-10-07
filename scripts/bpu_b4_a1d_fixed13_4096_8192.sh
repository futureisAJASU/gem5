#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1d_fixed13_4096_8192}"
NATIVE_4096="${NATIVE_4096:-bpu_b4a1_extension_4096}"
NATIVE_8192="${NATIVE_8192:-bpu_b4a1_extension_8192}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(statemate crc32 nsichneu slre sglib-combined qrduino)
ENTRIES=(4096 8192)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify native evidence and frozen-subset binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR: missing binary $w" >&2; exit 2; }
  [[ -f "$NATIVE_4096/$w/e4096/roi.stats" ]] || { echo "ERROR: missing native e4096 $w" >&2; exit 2; }
  [[ -f "$NATIVE_8192/$w/e8192/roi.stats" ]] || { echo "ERROR: missing native e8192 $w" >&2; exit 2; }
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

echo "[2/5] Run fixed-13 capacity diagnostic (2 points x 6 workloads = 12 ROI)"
for w in "${WORKLOADS[@]}"; do
  for e in "${ENTRIES[@]}"; do
    out="$OUT_ROOT/$w/e$e"; mkdir -p "$out"
    echo "  $w / entries=$e / fixed-hash-log=13"
    set +e
    "$GEM5" --outdir="$out" "$CFG"       --binary "$EMBENCH_BUILD/src/$w/$w"       --bp-type micro-tage       --bp-inst-shift 1 --bp-cond-shift 1 --bp-btb-shift 2 --bp-indirect-shift 1       --micro-tage-tagged-entries "$e"       --micro-tage-fixed-index-hash-log 13       --btb-entries 4096       >"$out.stdout" 2>"$out.stderr"
    rc=$?
    set -e
    if (( rc != 0 )); then
      echo "ERROR: $w/e$e fixed13 rc=$rc" >&2
      tail -n 160 "$out.stdout" >&2 || true
      tail -n 160 "$out.stderr" >&2 || true
      exit "$rc"
    fi
    grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || { tail -n 160 "$out.stdout" >&2; exit 5; }
    extract_first_roi "$out/stats.txt" "$out/roi.stats"
  done
done

echo "[3/5] Validate fixed-13 isolation and 8192 positive control"
python3 - "$OUT_ROOT" "$NATIVE_4096" "$NATIVE_8192" <<'PY'
import configparser, csv, math, pathlib, sys
root=pathlib.Path(sys.argv[1]); n4096=pathlib.Path(sys.argv[2]); n8192=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
bits={4096:174694,8192:346726}
logs={4096:[11,12,12,12],8192:[11,13,13,13]}

def parse(path):
    s={}; v={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try: x=float(p[1])
        except ValueError: continue
        s[p[0]]=x
        if "::" in p[0]:
            b,i=p[0].rsplit("::",1)
            if i.isdigit(): v.setdefault(b,{})[int(i)]=x
    return s,v
def one(s,suf):
    h=[x for k,x in s.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError((suf,h))
    return h[0]
def vector(v,suf):
    h=[x for k,x in v.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError((suf,h))
    return h[0]
def vec(x): return [int(y) for y in x.replace("[","").replace("]","").replace(","," ").split()]
def gm(xs): return math.exp(sum(math.log(x) for x in xs)/len(xs))
def native_path(w,e): return (n4096 if e==4096 else n8192)/w/f"e{e}"/"roi.stats"

D={}; N={}
for w in workloads:
    D[w]={}; N[w]={}
    for e in (4096,8192):
        out=root/w/f"e{e}"; s,v=parse(out/"roi.stats")
        cp=configparser.ConfigParser(strict=False); cp.optionxform=str; cp.read(out/"config.ini")
        hs=[sec for sec in cp.sections() if sec.endswith(".branchPred.conditionalBranchPred.tage")]
        if len(hs)!=1: raise SystemExit(f"ERROR {w}/e{e}: tage sections")
        sec=cp[hs[0]]
        if vec(sec["logTagTableSizes"])!=logs[e]: raise SystemExit(f"ERROR {w}/e{e}: physical logs")
        if int(sec["fixedIndexHashLogSize"])!=13: raise SystemExit(f"ERROR {w}/e{e}: fixed hash != 13")
        if vec(sec["explicitHistLengths"])!=[8,24,64] or vec(sec["tagTableTagWidths"])!=[0,8,9,10]:
            raise SystemExit(f"ERROR {w}/e{e}: non-capacity geometry changed")
        if int(one(s,"storageBits"))!=bits[e]: raise SystemExit(f"ERROR {w}/e{e}: storage")
        committed=int(one(s,"committedConditionalPredictions"))
        if int(one(s,"predictionMetadataChecks"))!=committed: raise SystemExit(f"ERROR {w}/e{e}: metadata invariant")
        if int(one(s,"historyRestoreChecks"))!=int(one(s,"historyStateRestores")): raise SystemExit(f"ERROR {w}/e{e}: rollback invariant")
        D[w][e]={
          "cycles":round(one(s,"simTicks")*1.4e9/1e12),
          "inst":int(one(s,"simInsts")),
          "wrong":int(one(s,"committedConditionalWrong")),
          "correct":int(one(s,"committedConditionalCorrect")),
          "committed":committed,
          "banks":vector(v,"selectedProviderBank"),
          "conf":vector(v,"providerConfidence"),
        }
        ns,nv=parse(native_path(w,e))
        N[w][e]={
          "cycles":round(one(ns,"simTicks")*1.4e9/1e12),
          "inst":int(one(ns,"simInsts")),
          "wrong":int(one(ns,"committedConditionalWrong")),
          "correct":int(one(ns,"committedConditionalCorrect")),
          "committed":int(one(ns,"committedConditionalPredictions")),
          "banks":vector(nv,"selectedProviderBank"),
          "conf":vector(nv,"providerConfidence"),
        }

for w in workloads:
    for key in ("cycles","inst","wrong","correct","committed","banks","conf"):
        if D[w][8192][key]!=N[w][8192][key]:
            raise SystemExit(f"ERROR positive-control {w} {key}: fixed13 e8192 != native")
print("BPU_B4_A1D_FIXED13_8192_NATIVE_CONVERGENCE=PASS")

print()
print("=== BPU-4 A1D fixed-13 capacity isolation: 4096 -> 8192 ===")
print(f"{'workload':18s} {'e4096 cyc':>11s} {'MPKI':>9s} {'e8192 cyc':>11s} {'vs4096%':>9s} {'MPKI':>9s} {'ctrl/native4096%':>17s}")
for w in workloads:
    a,b=D[w][4096],D[w][8192]
    m1=1000*a["wrong"]/a["inst"]; m2=1000*b["wrong"]/b["inst"]
    sens=(a["cycles"]/N[w][4096]["cycles"]-1)*100
    print(f"{w:18s} {a['cycles']:11d} {m1:9.4f} {b['cycles']:11d} {(b['cycles']/a['cycles']-1)*100:9.3f} {m2:9.4f} {sens:17.3f}")

ctrl=gm([D[w][8192]["cycles"]/D[w][4096]["cycles"] for w in workloads])
native=gm([N[w][8192]["cycles"]/N[w][4096]["cycles"] for w in workloads])
sens=gm([D[w][4096]["cycles"]/N[w][4096]["cycles"] for w in workloads])
print()
print(f"4096 -> 8192 controlled fixed-13: {(ctrl-1)*100:+.5f}% cycles")
print(f"4096 -> 8192 native geometry:     {(native-1)*100:+.5f}% cycles")
print(f"e4096 fixed13/native geomean:      {(sens-1)*100:+.5f}%")
print(f"effect difference controlled-native: {(ctrl-native)*100:+.5f} pp")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f); wr.writerow(["workload","entries","controlledCycles","nativeCycles","controlledVsNativePct"])
    for w in workloads:
        for e in (4096,8192):
            wr.writerow([w,e,D[w][e]["cycles"],N[w][e]["cycles"],
                         f"{(D[w][e]['cycles']/N[w][e]['cycles']-1)*100:.9f}"])

print()
print("BPU_B4_A1D_FIXED13_GEOMETRY_GATE=PASS")
print("BPU_B4_A1D_FIXED13_STORAGE_GATE=PASS")
print("BPU_B4_A1D_FIXED13_CAPACITY_ISOLATION=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "diagnostic=fixed13_capacity_isolation"
  echo "fixed_index_hash_log=13"
  echo "physical_entries_per_table=4096,8192"
  echo "positive_control=fixed13_e8192_must_match_native_e8192"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4_A1D_FIXED13_PROVENANCE=PASS"
