#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b2_micro_tage_instrumentation}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  statemate
  crc32
  nsichneu
  slre
  sglib-combined
  qrduino
)

echo "[0/4] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/4] Ensure frozen-subset Embench binaries exist"
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

echo "[2/4] Run micro-TAGE on frozen six-workload subset"
for w in "${WORKLOADS[@]}"; do
  bin="$EMBENCH_BUILD/src/$w/$w"
  out="$OUT_ROOT/$w"
  mkdir -p "$out"
  echo "  $w"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $w failed benchmark verification" >&2
    cat "$out.stdout" >&2
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
done

echo "[3/4] Validate TAGE-internal invariants and summarize"
python3 - "$OUT_ROOT" <<'PY'
import configparser
import csv
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]

def parse(path):
    scalars={}
    vectors={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        key,raw=p[0],p[1]
        try:
            val=float(raw)
        except ValueError:
            continue
        if "::" in key:
            base,idx=key.rsplit("::",1)
            if idx.isdigit():
                vectors.setdefault(base,{})[int(idx)]=val
        scalars[key]=val
    return scalars,vectors

def scalar_suffix(scalars,suffix):
    hits=[(k,v) for k,v in scalars.items() if k.endswith(suffix)]
    if len(hits)!=1:
        raise RuntimeError(f"expected one scalar ending {suffix}, got {hits}")
    return hits[0][1]

def vector_suffix(vectors,suffix):
    hits=[(k,v) for k,v in vectors.items() if k.endswith(suffix)]
    if len(hits)!=1:
        raise RuntimeError(f"expected one vector ending {suffix}, got {[x[0] for x in hits]}")
    return hits[0][1]

rows=[]
storage_seen=set()

print()
print("=== BPU-2 micro-TAGE internal instrumentation ===")
print(
    f"{'workload':18s} {'cycles':>11s} {'TAGE MPKI':>10s} "
    f"{'weak%':>8s} {'weak wrong%':>11s} {'B0%':>8s} {'B1%':>8s} "
    f"{'B2%':>8s} {'B3%':>8s} {'bits':>8s}"
)

for w in workloads:
    out=root/w
    s,v=parse(out/"roi.stats")

    simticks=scalar_suffix(s,"simTicks")
    siminsts=scalar_suffix(s,"simInsts")
    cycles=round(simticks*1.4e9/1e12)

    total=int(scalar_suffix(s,"committedConditionalPredictions"))
    correct=int(scalar_suffix(s,"committedConditionalCorrect"))
    wrong=int(scalar_suffix(s,"committedConditionalWrong"))

    conf=vector_suffix(v,"providerConfidence")
    conf_ok=vector_suffix(v,"providerConfidenceCorrect")
    conf_bad=vector_suffix(v,"providerConfidenceWrong")
    banks=vector_suffix(v,"selectedProviderBank")

    if total != correct + wrong:
        raise SystemExit(f"ERROR {w}: total != correct+wrong")
    if int(sum(conf.values())) != total:
        raise SystemExit(f"ERROR {w}: confidence sum != total")
    if int(sum(conf_ok.values())) != correct:
        raise SystemExit(f"ERROR {w}: confidence-correct sum != correct")
    if int(sum(conf_bad.values())) != wrong:
        raise SystemExit(f"ERROR {w}: confidence-wrong sum != wrong")
    if int(sum(banks.values())) != total:
        raise SystemExit(f"ERROR {w}: provider-bank sum != total")

    storage=int(scalar_suffix(s,"storageBits"))
    bimodal=int(scalar_suffix(s,"bimodalStorageBits"))
    tagged=int(scalar_suffix(s,"taggedStorageBits"))
    history=int(scalar_suffix(s,"historyStorageBits"))
    other=int(scalar_suffix(s,"otherStorageBits"))

    if storage != bimodal + tagged + history + other:
        raise SystemExit(
            f"ERROR {w}: storage mismatch "
            f"{storage} != {bimodal}+{tagged}+{history}+{other}"
        )
    storage_seen.add((storage,bimodal,tagged,history,other))

    # Recompute the exact persistent-state convention from emitted config.
    cp=configparser.ConfigParser(strict=False)
    cp.optionxform=str
    cp.read(out/"config.ini")
    sec_hits=[sec for sec in cp.sections()
              if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(sec_hits)!=1:
        raise SystemExit(f"ERROR {w}: TAGE config section {sec_hits}")
    sec=cp[sec_hits[0]]

    def parse_vec(raw):
        return [int(x) for x in raw.replace("[","").replace("]","").replace(","," ").split()]

    logs=parse_vec(sec["logTagTableSizes"])
    tags=parse_vec(sec["tagTableTagWidths"])
    n=int(sec["nHistoryTables"])
    ctr=int(sec["tagTableCounterBits"])
    ubits=int(sec["tagTableUBits"])
    ratio=int(sec["logRatioBiModalHystEntries"])
    maxhist=int(sec["maxHist"])
    pathbits=int(sec["pathHistBits"])
    usealt_n=int(sec["numUseAltOnNa"])
    usealt_bits=int(sec["useAltOnNaBits"])
    resetbits=int(sec["logUResetPeriod"])

    expected_tagged=sum((1<<logs[i])*(ctr+ubits+tags[i]) for i in range(1,n+1))
    bsize=1<<logs[0]
    expected_bimodal=bsize+(bsize>>ratio)
    expected_history=maxhist+pathbits
    expected_other=usealt_n*usealt_bits+resetbits
    expected=expected_tagged+expected_bimodal+expected_history+expected_other

    if (storage,bimodal,tagged,history,other) != (
        expected,expected_bimodal,expected_tagged,expected_history,expected_other
    ):
        raise SystemExit(
            f"ERROR {w}: emitted-config storage accounting mismatch"
        )

    weak=int(conf.get(0,0))
    weak_wrong=int(conf_bad.get(0,0))
    weak_rate=100.0*weak/total if total else 0.0
    weak_wrong_share=100.0*weak_wrong/wrong if wrong else 0.0
    mpki=1000.0*wrong/siminsts

    br=[100.0*banks.get(i,0)/total if total else 0.0 for i in range(4)]
    print(
        f"{w:18s} {cycles:11d} {mpki:10.4f} "
        f"{weak_rate:8.3f} {weak_wrong_share:11.3f} "
        f"{br[0]:8.3f} {br[1]:8.3f} {br[2]:8.3f} {br[3]:8.3f} "
        f"{storage:8d}"
    )

    rows.append([
        w,cycles,int(siminsts),total,correct,wrong,mpki,
        weak,weak_rate,weak_wrong,weak_wrong_share,
        *[int(banks.get(i,0)) for i in range(4)],
        storage,bimodal,tagged,history,other
    ])

if len(storage_seen)!=1:
    raise SystemExit(f"ERROR: storage accounting differs across workloads: {storage_seen}")

storage,bimodal,tagged,history,other=next(iter(storage_seen))
print()
print(
    f"persistent state: total={storage} bits "
    f"({storage/8:.1f} bytes, {storage/8192:.4f} KiB)"
)
print(
    f"  tagged={tagged} bimodal={bimodal} "
    f"history={history} other={other}"
)

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "workload","cycles","simInsts","tageCommitted","tageCorrect",
        "tageWrong","tageMPKI","weakPredictions","weakRatePct",
        "weakWrong","weakWrongSharePct",
        "providerBank0","providerBank1","providerBank2","providerBank3",
        "storageBits","bimodalBits","taggedBits","historyBits","otherBits"
    ])
    wr.writerows(rows)

print()
print("BPU_B2_TAGE_INTERNAL_INVARIANTS=PASS")
print("BPU_B2_STORAGE_ACCOUNTING=PASS")
print("BPU_B2_MICRO_TAGE_INSTRUMENTATION=PASS")
PY

echo "[4/4] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "predictor=micro-tage"
  echo "conditional_shift=1"
  echo "btb_shift=2"
  echo "indirect_shift=1"
  echo "btb_entries=4096"
  echo "sweep_subset=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
  echo "roi_stats_section=first"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B2_INSTRUMENTATION_PROVENANCE=PASS"
