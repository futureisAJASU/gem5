#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1_extension_8192}"
PRIOR_ROOT="${PRIOR_ROOT:-bpu_b4a1_extension_4096}"
TOURN_ROOT="${TOURN_ROOT:-bpu_b1_canonical_index_closure}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(statemate crc32 nsichneu slre sglib-combined qrduino)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify prior 4096-point evidence and Embench binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR: missing binary $w" >&2; exit 2; }
  [[ -f "$PRIOR_ROOT/$w/e4096/roi.stats" ]] || { echo "ERROR: missing prior e4096 ROI $w" >&2; exit 2; }
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

echo "[2/5] Run 8192-entry native extension point on frozen six-workload subset"
for w in "${WORKLOADS[@]}"; do
  out="$OUT_ROOT/$w/e8192"; mkdir -p "$out"
  echo "  $w / entries=8192"
  set +e
  "$GEM5" --outdir="$out" "$CFG"     --binary "$EMBENCH_BUILD/src/$w/$w"     --bp-type micro-tage     --bp-inst-shift 1 --bp-cond-shift 1 --bp-btb-shift 2 --bp-indirect-shift 1     --micro-tage-tagged-entries 8192     --micro-tage-fixed-index-hash-log 0     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e
  if (( rc != 0 )); then
    echo "ERROR: $w/e8192 rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi
  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || { tail -n 160 "$out.stdout" >&2; exit 5; }
  extract_first_roi "$out/stats.txt" "$out/roi.stats"
done

echo "[3/5] Compare 4096 -> 8192 and evaluate endpoint rule"
python3 - "$OUT_ROOT" "$PRIOR_ROOT" "$TOURN_ROOT" <<'PY'
import configparser, csv, math, pathlib, sys
root=pathlib.Path(sys.argv[1]); prior=pathlib.Path(sys.argv[2]); tourn=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
KNEE=0.005; GUARD=0.020
BITS_4096=174694; BITS_8192=346726

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
    if len(h)!=1: raise RuntimeError((suf,h))
    return h[0]
def vec(x): return [int(y) for y in x.replace("[","").replace("]","").replace(","," ").split()]
def gm(xs): return math.exp(sum(math.log(x) for x in xs)/len(xs))

D={}
print()
print("=== BPU-4 A1 native endpoint extension: 4096 -> 8192 entries/table ===")
print(f"{'workload':18s} {'e4096 cyc':>11s} {'MPKI':>9s} {'e8192 cyc':>11s} {'vs4096%':>9s} {'MPKI':>9s}")
for w in workloads:
    s1=parse(prior/w/"e4096"/"roi.stats"); s2=parse(root/w/"e8192"/"roi.stats")
    c1=round(one(s1,"simTicks")*1.4e9/1e12); c2=round(one(s2,"simTicks")*1.4e9/1e12)
    i1=int(one(s1,"simInsts")); i2=int(one(s2,"simInsts"))
    w1=int(one(s1,"committedConditionalWrong")); w2=int(one(s2,"committedConditionalWrong"))
    if i1!=i2: raise SystemExit(f"ERROR {w}: simInsts changed")
    if int(one(s1,"storageBits"))!=BITS_4096: raise SystemExit(f"ERROR {w}: prior storage")
    if int(one(s2,"storageBits"))!=BITS_8192: raise SystemExit(f"ERROR {w}: e8192 storage")
    if int(one(s2,"predictionMetadataChecks"))!=int(one(s2,"committedConditionalPredictions")):
        raise SystemExit(f"ERROR {w}: metadata invariant")
    if int(one(s2,"historyRestoreChecks"))!=int(one(s2,"historyStateRestores")):
        raise SystemExit(f"ERROR {w}: rollback invariant")

    cp=configparser.ConfigParser(strict=False); cp.optionxform=str; cp.read(root/w/"e8192"/"config.ini")
    hs=[sec for sec in cp.sections() if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(hs)!=1: raise SystemExit(f"ERROR {w}: tage sections")
    sec=cp[hs[0]]
    if vec(sec["logTagTableSizes"]) != [11,13,13,13]: raise SystemExit(f"ERROR {w}: logs")
    if int(sec["fixedIndexHashLogSize"]) != 0: raise SystemExit(f"ERROR {w}: non-native hash")
    if vec(sec["explicitHistLengths"]) != [8,24,64] or vec(sec["tagTableTagWidths"]) != [0,8,9,10]:
        raise SystemExit(f"ERROR {w}: non-capacity geometry changed")

    m1=1000*w1/i1; m2=1000*w2/i2
    D[w]={"c4096":c1,"c8192":c2,"m4096":m1,"m8192":m2}
    print(f"{w:18s} {c1:11d} {m1:9.4f} {c2:11d} {(c2/c1-1)*100:9.3f} {m2:9.4f}")

ratio=gm([D[w]["c8192"]/D[w]["c4096"] for w in workloads])
benefit=1-ratio
max_small=max(D[w]["c4096"]/D[w]["c8192"]-1 for w in workloads)
worst=max(workloads,key=lambda w:D[w]["c4096"]/D[w]["c8192"]-1)

print()
print("=== extension geomean / guardrail ===")
print(f"e8192/e4096 = {ratio:.9f} ({(ratio-1)*100:+.5f}%)")
print(f"benefit e4096 -> e8192 = {benefit*100:+.5f}%")
print(f"max workload regression of e4096 vs e8192 = {max_small*100:+.5f}% ({worst})")

decision="4096" if (benefit < KNEE and max_small < GUARD) else "EXTEND_ABOVE_8192_REQUIRED"
print()
print("=== A1 endpoint decision ===")
print(f"BPU_B4_A1_FINAL_DECISION={decision}")
print()
print("=== exact persistent state ===")
print(f"4096 entries/table : {BITS_4096} bits = {BITS_4096/8192:.4f} KiB")
print(f"8192 entries/table : {BITS_8192} bits = {BITS_8192/8192:.4f} KiB")
print(f"storage growth 4096 -> 8192 = {(BITS_8192/BITS_4096-1)*100:+.2f}%")

if all((tourn/w/"btb2"/"roi.stats").exists() for w in workloads):
    rs=[]; worstv=(-1e9,None)
    for w in workloads:
        ts=parse(tourn/w/"btb2"/"roi.stats"); tc=round(one(ts,"simTicks")*1.4e9/1e12)
        r=D[w]["c8192"]/tc; rs.append(r)
        if r-1>worstv[0]: worstv=(r-1,w)
    gr=gm(rs)
    print()
    print(f"e8192 geomean vs Tournament = {(gr-1)*100:+.5f}%")
    print(f"e8192 worst vs Tournament = {worstv[1]} {worstv[0]*100:+.5f}%")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f); wr.writerow(["workload","e4096_cycles","e4096_tageMPKI","e8192_cycles","e8192_tageMPKI","e8192_vs_e4096_pct"])
    for w in workloads:
        d=D[w]; wr.writerow([w,d["c4096"],f"{d['m4096']:.9f}",d["c8192"],f"{d['m8192']:.9f}",f"{(d['c8192']/d['c4096']-1)*100:.9f}"])

(root/"decision.txt").write_text(
    "axis=tagged_entries_per_table\nprior_endpoint=4096\nextension_point=8192\n"
    "geomean_knee_threshold=0.005\nper_workload_next_larger_guardrail=0.020\n"
    f"decision={decision}\n"
)
print()
print("BPU_B4_A1_8192_GEOMETRY_GATE=PASS")
print("BPU_B4_A1_8192_STORAGE_GATE=PASS")
print("BPU_B4_A1_8192_KNEE_EVALUATION=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "axis=tagged_entries_per_table"
  echo "prior_endpoint=4096"
  echo "extension_point=8192"
  echo "native_index_hash=on"
  echo "fixed_bimodal_entries=2048"
  echo "fixed_tables=3"
  echo "fixed_histories=8,24,64"
  echo "fixed_tags=8,9,10"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Decision: $OUT_ROOT/decision.txt"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4_A1_8192_PROVENANCE=PASS"
