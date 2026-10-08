#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b6a_tage_prior22_full19}"
SEED_ROOT="${SEED_ROOT:-bpu_b6_perceptron_seed_full19}"
BASE_ROOT="${BASE_ROOT:-bpu_b4c_full19_geometry}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  aha-mont64 crc32 cubic edn huffbench matmult-int minver nbody
  nettle-aes nettle-sha256 nsichneu picojpeg qrduino sglib-combined
  slre st statemate ud wikisort
)

PROFILES=(v1p22 wmp22)

declare -A BP_TYPE=(
  [v1p22]="tage5-perc-v1-prior22"
  [wmp22]="tage5-perc-wm-prior22"
)

declare -A SEED_PROFILE=(
  [v1p22]="v1"
  [wmp22]="wm"
)

EXPECTED_TOTAL_BITS=55336
EXPECTED_PERC_BITS=9600

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify seed/baseline evidence and binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || { echo "ERROR missing binary $w" >&2; exit 2; }
  [[ -f "$BASE_ROOT/g5/$w/roi.stats" ]] || { echo "ERROR missing G5 $w" >&2; exit 2; }
  [[ -f "$BASE_ROOT/g7/$w/roi.stats" ]] || { echo "ERROR missing G7 $w" >&2; exit 2; }
  [[ -f "$SEED_ROOT/v1/$w/roi.stats" ]] || { echo "ERROR missing BPU-6 V1 $w" >&2; exit 2; }
  [[ -f "$SEED_ROOT/wm/$w/roi.stats" ]] || { echo "ERROR missing BPU-6 WM $w" >&2; exit 2; }
done

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1" dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ {
      section++
      if (section == 1) keep=1
    }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst" || {
    echo "ERROR: failed ROI extraction from $src" >&2
    exit 4
  }
}

echo "[2/5] Run two TAGE-prior22 variants x 19 workloads = 38 ROI"
for p in "${PROFILES[@]}"; do
  for w in "${WORKLOADS[@]}"; do
    out="$OUT_ROOT/$p/$w"
    mkdir -p "$out"
    echo "  $w / $p"

    set +e
    "$GEM5" --outdir="$out" "$CFG"       --binary "$EMBENCH_BUILD/src/$w/$w"       --bp-type "${BP_TYPE[$p]}"       --bp-inst-shift 1       --bp-cond-shift 1       --bp-btb-shift 2       --bp-indirect-shift 1       --btb-entries 4096       >"$out.stdout" 2>"$out.stderr"
    rc=$?
    set -e

    if (( rc != 0 )); then
      echo "ERROR: $w/$p rc=$rc" >&2
      tail -n 160 "$out.stdout" >&2 || true
      tail -n 160 "$out.stderr" >&2 || true
      exit "$rc"
    fi

    grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
      echo "ERROR: workload verification failed $w/$p" >&2
      exit 5
    }

    extract_first_roi "$out/stats.txt" "$out/roi.stats"
  done
done

echo "[3/5] Validate accounting and compare against BPU-6 seed"
python3 - "$OUT_ROOT" "$SEED_ROOT" "$BASE_ROOT" <<'PY'
import csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1]); seed=pathlib.Path(sys.argv[2]); base=pathlib.Path(sys.argv[3])
W=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
P={"v1p22":"v1","wmp22":"wm"}
TOTAL_BITS=55336; PERC_BITS=9600

def parse(path):
    s={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try:s[p[0]]=float(p[1])
        except ValueError:pass
    return s
def one(s,suf):
    h=[v for k,v in s.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError((suf,h))
    return h[0]
def cyc(s): return round(one(s,"simTicks")*1.4e9/1e12)
def gm(xs): return math.exp(sum(math.log(x) for x in xs)/len(xs))

R={}; rows=[]
for p,sp in P.items():
    R[p]={}
    for w in W:
        s=parse(root/p/w/"roi.stats")
        ss=parse(seed/sp/w/"roi.stats")
        g5=parse(base/"g5"/w/"roi.stats")
        g7=parse(base/"g7"/w/"roi.stats")

        committed=int(one(s,"committedConditionalPredictions"))
        tage_wrong=int(one(s,"committedConditionalWrong"))
        final_correct=int(one(s,"finalConditionalCorrect"))
        final_wrong=int(one(s,"finalConditionalWrong"))
        eligible=int(one(s,"perceptronEligiblePredictions"))
        disagree=int(one(s,"perceptronDisagreements"))
        override=int(one(s,"perceptronOverrides"))
        fix=int(one(s,"perceptronWouldFix"))
        brk=int(one(s,"perceptronWouldBreak"))
        train=int(one(s,"perceptronTrainings"))
        inst=int(one(s,"simInsts"))

        if int(one(s,"storageBits"))!=TOTAL_BITS: raise SystemExit(f"ERROR {p}/{w}: storage")
        if int(one(s,"perceptronStorageBits"))!=PERC_BITS: raise SystemExit(f"ERROR {p}/{w}: perceptron storage")
        if final_correct+final_wrong!=committed: raise SystemExit(f"ERROR {p}/{w}: final count")
        if override!=fix+brk: raise SystemExit(f"ERROR {p}/{w}: override identity")
        if final_wrong!=tage_wrong-fix+brk: raise SystemExit(f"ERROR {p}/{w}: final wrong identity")
        if override>disagree or train>eligible: raise SystemExit(f"ERROR {p}/{w}: monotonicity")

        R[p][w]=dict(
          cycles=cyc(s), seed_cycles=cyc(ss), g5=cyc(g5), g7=cyc(g7),
          committed=committed, tage_wrong=tage_wrong, final_wrong=final_wrong,
          eligible=eligible, fix=fix, brk=brk, override=override, train=train, inst=inst
        )

print()
print("=== BPU-6A fixed TAGE-prior22 full-19 ===")
print("prior source: gem5 MPP-TAGE init_lsum = +/-22")
print(f"{'profile':10s} {'vsSeed%':>10s} {'vsG5%':>10s} {'vsG7%':>10s} {'act%':>8s} {'TAGEwrong':>11s} {'finalWrong':>11s} {'fix':>9s} {'break':>9s} {'net':>9s}")
for p in P:
    d=R[p]
    rs=gm([d[w]["cycles"]/d[w]["seed_cycles"] for w in W])
    rg5=gm([d[w]["cycles"]/d[w]["g5"] for w in W])
    rg7=gm([d[w]["cycles"]/d[w]["g7"] for w in W])
    cond=sum(d[w]["committed"] for w in W); elig=sum(d[w]["eligible"] for w in W)
    tw=sum(d[w]["tage_wrong"] for w in W); fw=sum(d[w]["final_wrong"] for w in W)
    fx=sum(d[w]["fix"] for w in W); br=sum(d[w]["brk"] for w in W)
    print(f"{p:10s} {(rs-1)*100:+10.5f} {(rg5-1)*100:+10.5f} {(rg7-1)*100:+10.5f} {100*elig/cond:8.3f} {tw:11d} {fw:11d} {fx:9d} {br:9d} {fx-br:+9d}")

print()
print("=== per-workload V1 prior22 ===")
print(f"{'workload':18s} {'vsSeed%':>9s} {'vsG5%':>9s} {'act%':>8s} {'TAGE MPKI':>10s} {'final MPKI':>11s} {'fix':>7s} {'break':>7s}")
for w in W:
    d=R["v1p22"][w]
    print(
      f"{w:18s} {(d['cycles']/d['seed_cycles']-1)*100:9.3f} "
      f"{(d['cycles']/d['g5']-1)*100:9.3f} {100*d['eligible']/d['committed']:8.3f} "
      f"{1000*d['tage_wrong']/d['inst']:10.4f} {1000*d['final_wrong']/d['inst']:11.4f} "
      f"{d['fix']:7d} {d['brk']:7d}"
    )

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["profile","workload","cycles","seedCycles","g5Cycles","g7Cycles","activationPct","tageWrong","finalWrong","fixes","breaks","netFix","overrides","trainings"])
    for p in P:
        for w in W:
            d=R[p][w]
            wr.writerow([p,w,d["cycles"],d["seed_cycles"],d["g5"],d["g7"],f"{100*d['eligible']/d['committed']:.9f}",d["tage_wrong"],d["final_wrong"],d["fix"],d["brk"],d["fix"]-d["brk"],d["override"],d["train"]])

print()
print("BPU_B6A_STORAGE_GATE=PASS")
print("BPU_B6A_FINAL_ERROR_RECONCILIATION=PASS")
print("BPU_B6A_PRIOR22_FULL19=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-6A_TAGE_prior22_full19"
  echo "profiles=v1p22,wmp22"
  echo "tage_prior=22"
  echo "prior_source=gem5_MPP-TAGE_init_lsum"
  echo "perceptron_entries=64"
  echo "perceptron_history=24"
  echo "perceptron_weight_bits=6"
  echo "perceptron_train_threshold=60"
  echo "combined_state_bits=55336"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B6A_PROVENANCE=PASS"
