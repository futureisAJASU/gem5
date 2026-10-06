#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1d_fixed12_2048_4096}"
NATIVE_2048="${NATIVE_2048:-bpu_b4a1_extension_2048}"
NATIVE_4096="${NATIVE_4096:-bpu_b4a1_extension_4096}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(statemate crc32 nsichneu slre sglib-combined qrduino)
ENTRIES=(2048 4096)
FIXED_HASH_LOG=12

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify native evidence and frozen-subset binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR: missing binary $w" >&2; exit 2; }
  [[ -f "$NATIVE_2048/$w/e2048/roi.stats" ]] || { echo "ERROR: missing native e2048 $w" >&2; exit 2; }
  [[ -f "$NATIVE_4096/$w/e4096/roi.stats" ]] || { echo "ERROR: missing native e4096 $w" >&2; exit 2; }
done

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1" dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ { section++; if (section == 1) keep=1 }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst" || exit 4
}

echo "[2/5] Run fixed-12 capacity diagnostic (2 points x 6 workloads = 12 ROI)"
for w in "${WORKLOADS[@]}"; do
  for e in "${ENTRIES[@]}"; do
    out="$OUT_ROOT/$w/e$e"
    mkdir -p "$out"
    echo "  $w / entries=$e / fixed-hash-log=12"
    set +e
    "$GEM5" --outdir="$out" "$CFG"       --binary "$EMBENCH_BUILD/src/$w/$w"       --bp-type micro-tage       --bp-inst-shift 1 --bp-cond-shift 1 --bp-btb-shift 2 --bp-indirect-shift 1       --micro-tage-tagged-entries "$e"       --micro-tage-fixed-index-hash-log 12       --btb-entries 4096       >"$out.stdout" 2>"$out.stderr"
    rc=$?
    set -e
    if (( rc != 0 )); then
      echo "ERROR: $w/e$e fixed12 rc=$rc" >&2
      tail -n 160 "$out.stdout" >&2 || true
      tail -n 160 "$out.stderr" >&2 || true
      exit "$rc"
    fi
    grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || { tail -n 160 "$out.stdout" >&2; exit 5; }
    extract_first_roi "$out/stats.txt" "$out/roi.stats"
  done
done

echo "[3/5] Validate fixed-12 isolation and 4096 positive control"
python3 - "$OUT_ROOT" "$NATIVE_2048" "$NATIVE_4096" <<'PY'
import configparser, csv, math, pathlib, sys
root=pathlib.Path(sys.argv[1]); n2048=pathlib.Path(sys.argv[2]); n4096=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
bits={2048:88678,4096:174694}
logs={2048:[11,11,11,11],4096:[11,12,12,12]}

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
def native_path(w,e): return (n2048 if e==2048 else n4096)/w/f"e{e}"/"roi.stats"

D={}; N={}
for w in workloads:
    D[w]={}; N[w]={}
    for e in (2048,4096):
        out=root/w/f"e{e}"
        s,v=parse(out/"roi.stats")
        cp=configparser.ConfigParser(strict=False); cp.optionxform=str; cp.read(out/"config.ini")
        hs=[sec for sec in cp.sections() if sec.endswith(".branchPred.conditionalBranchPred.tage")]
        if len(hs)!=1: raise SystemExit(f"ERROR {w}/e{e}: tage sections {hs}")
        sec=cp[hs[0]]
        if vec(sec["logTagTableSizes"])!=logs[e]: raise SystemExit(f"ERROR {w}/e{e}: physical logs")
        if int(sec["fixedIndexHashLogSize"])!=12: raise SystemExit(f"ERROR {w}/e{e}: fixed hash != 12")
        if vec(sec["explicitHistLengths"])!=[8,24,64] or vec(sec["tagTableTagWidths"])!=[0,8,9,10]:
            raise SystemExit(f"ERROR {w}/e{e}: non-capacity geometry changed")
        if int(one(s,"storageBits"))!=bits[e]: raise SystemExit(f"ERROR {w}/e{e}: storage")
        committed=int(one(s,"committedConditionalPredictions"))
        if int(one(s,"predictionMetadataChecks"))!=committed: raise SystemExit(f"ERROR {w}/e{e}: metadata invariant")
        restores=int(one(s,"historyStateRestores"))
        if int(one(s,"historyRestoreChecks"))!=restores: raise SystemExit(f"ERROR {w}/e{e}: rollback invariant")
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
        if D[w][4096][key]!=N[w][4096][key]:
            raise SystemExit(f"ERROR positive-control {w} {key}: fixed12 e4096 != native")
print("BPU_B4_A1D_FIXED12_4096_NATIVE_CONVERGENCE=PASS")

print()
print("=== BPU-4 A1D fixed-12 capacity isolation: 2048 -> 4096 ===")
print(f"{'workload':18s} {'e2048 cyc':>11s} {'MPKI':>9s} {'e4096 cyc':>11s} {'vs2048%':>9s} {'MPKI':>9s} {'ctrl/native2048%':>17s}")
for w in workloads:
    a,b=D[w][2048],D[w][4096]
    m1=1000*a["wrong"]/a["inst"]; m2=1000*b["wrong"]/b["inst"]
    sens=(a["cycles"]/N[w][2048]["cycles"]-1)*100
    print(f"{w:18s} {a['cycles']:11d} {m1:9.4f} {b['cycles']:11d} {(b['cycles']/a['cycles']-1)*100:9.3f} {m2:9.4f} {sens:17.3f}")

ctrl=gm([D[w][4096]["cycles"]/D[w][2048]["cycles"] for w in workloads])
native=gm([N[w][4096]["cycles"]/N[w][2048]["cycles"] for w in workloads])
sens=gm([D[w][2048]["cycles"]/N[w][2048]["cycles"] for w in workloads])
print()
print(f"2048 -> 4096 controlled fixed-12: {(ctrl-1)*100:+.5f}% cycles")
print(f"2048 -> 4096 native geometry:     {(native-1)*100:+.5f}% cycles")
print(f"e2048 fixed12/native geomean:      {(sens-1)*100:+.5f}%")
print(f"effect difference controlled-native: {(ctrl-native)*100:+.5f} pp")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f); wr.writerow(["workload","entries","controlledCycles","nativeCycles","controlledVsNativePct"])
    for w in workloads:
        for e in (2048,4096):
            wr.writerow([w,e,D[w][e]["cycles"],N[w][e]["cycles"],
                         f"{(D[w][e]['cycles']/N[w][e]['cycles']-1)*100:.9f}"])

print()
print("BPU_B4_A1D_FIXED12_GEOMETRY_GATE=PASS")
print("BPU_B4_A1D_FIXED12_STORAGE_GATE=PASS")
print("BPU_B4_A1D_FIXED12_CAPACITY_ISOLATION=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "diagnostic=fixed12_capacity_isolation"
  echo "fixed_index_hash_log=12"
  echo "physical_entries_per_table=2048,4096"
  echo "positive_control=fixed12_e4096_must_match_native_e4096"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4_A1D_FIXED12_PROVENANCE=PASS"
