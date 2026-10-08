#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b6_perceptron_seed_full19}"
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

PROFILES=(v1 wm always)

declare -A BP_TYPE=(
  [v1]="tage5-perc-v1"
  [wm]="tage5-perc-wm"
  [always]="tage5-perc-always"
)

EXPECTED_TOTAL_BITS=55336
EXPECTED_PERC_BITS=9600
EXPECTED_G5_BITS=45736
EXPECTED_G7_BITS=65192

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify baselines and binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing binary $w" >&2; exit 2;
  }
  [[ -f "$BASE_ROOT/g5/$w/roi.stats" ]] || {
    echo "ERROR: missing G5 baseline $w" >&2; exit 2;
  }
  [[ -f "$BASE_ROOT/g7/$w/roi.stats" ]] || {
    echo "ERROR: missing G7 reference $w" >&2; exit 2;
  }
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
    echo "ERROR: failed to extract ROI from $src" >&2
    exit 4
  }
}

echo "[2/5] Run 3 perceptron gates x 19 workloads = 57 ROI"
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
      tail -n 180 "$out.stdout" >&2 || true
      tail -n 180 "$out.stderr" >&2 || true
      exit "$rc"
    fi

    grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
      echo "ERROR: workload verification failed $w/$p" >&2
      exit 5
    }

    extract_first_roi "$out/stats.txt" "$out/roi.stats"
  done
done

echo "[3/5] Validate exact storage/accounting and summarize"
python3 - "$OUT_ROOT" "$BASE_ROOT" <<'PY'
import csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1])
base=pathlib.Path(sys.argv[2])

W=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
P=["v1","wm","always"]
TOTAL_BITS=55336
PERC_BITS=9600
G5_BITS=45736
G7_BITS=65192

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
    if len(h)!=1:
        raise RuntimeError(f"{suf}: {h}")
    return h[0]

def cyc(s):
    return round(one(s,"simTicks")*1.4e9/1e12)

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))

D={p:{} for p in P}
B={}

for w in W:
    g5=parse(base/"g5"/w/"roi.stats")
    g7=parse(base/"g7"/w/"roi.stats")
    if int(one(g5,"storageBits"))!=G5_BITS:
        raise SystemExit(f"ERROR {w}: G5 storage")
    if int(one(g7,"storageBits"))!=G7_BITS:
        raise SystemExit(f"ERROR {w}: G7 storage")
    B[w]={"g5":cyc(g5),"g7":cyc(g7)}

for p in P:
    for w in W:
        s=parse(root/p/w/"roi.stats")
        committed=int(one(s,"committedConditionalPredictions"))
        tage_wrong=int(one(s,"committedConditionalWrong"))
        final_correct=int(one(s,"finalConditionalCorrect"))
        final_wrong=int(one(s,"finalConditionalWrong"))
        eligible=int(one(s,"perceptronEligiblePredictions"))
        disagreements=int(one(s,"perceptronDisagreements"))
        overrides=int(one(s,"perceptronOverrides"))
        fixes=int(one(s,"perceptronWouldFix"))
        breaks=int(one(s,"perceptronWouldBreak"))
        trainings=int(one(s,"perceptronTrainings"))
        inst=int(one(s,"simInsts"))

        if int(one(s,"storageBits"))!=TOTAL_BITS:
            raise SystemExit(f"ERROR {p}/{w}: total storage")
        if int(one(s,"perceptronStorageBits"))!=PERC_BITS:
            raise SystemExit(f"ERROR {p}/{w}: perceptron storage")
        if final_correct+final_wrong != committed:
            raise SystemExit(f"ERROR {p}/{w}: final count reconciliation")
        if overrides != fixes+breaks:
            raise SystemExit(f"ERROR {p}/{w}: override fix/break reconciliation")
        if final_wrong != tage_wrong-fixes+breaks:
            raise SystemExit(f"ERROR {p}/{w}: final wrong identity")
        if overrides > disagreements or trainings > eligible:
            raise SystemExit(f"ERROR {p}/{w}: event monotonicity")
        if p=="always" and eligible!=committed:
            raise SystemExit(f"ERROR {p}/{w}: always gate not always active")

        D[p][w]={
          "cycles":cyc(s),
          "inst":inst,
          "committed":committed,
          "tage_wrong":tage_wrong,
          "final_wrong":final_wrong,
          "eligible":eligible,
          "overrides":overrides,
          "fixes":fixes,
          "breaks":breaks,
          "trainings":trainings,
          "activation":100*eligible/committed if committed else 0,
          "final_mpki":1000*final_wrong/inst,
        }

print()
print("=== BPU-6 selective perceptron seed full-19 ===")
print("G5 base state       = 45,736 bits")
print("perceptron weights  =  9,600 bits")
print("combined state      = 55,336 bits = 6.7549 KiB")
print("G7 reference state  = 65,192 bits")
print()

print(f"{'profile':10s} {'vsG5 cyc%':>11s} {'vsG7 cyc%':>11s} {'act%':>9s} {'TAGEwrong':>11s} {'finalWrong':>11s} {'fix':>9s} {'break':>9s}")
for p in P:
    rg5=gm([D[p][w]["cycles"]/B[w]["g5"] for w in W])
    rg7=gm([D[p][w]["cycles"]/B[w]["g7"] for w in W])
    total_cond=sum(D[p][w]["committed"] for w in W)
    total_elig=sum(D[p][w]["eligible"] for w in W)
    tw=sum(D[p][w]["tage_wrong"] for w in W)
    fw=sum(D[p][w]["final_wrong"] for w in W)
    fx=sum(D[p][w]["fixes"] for w in W)
    br=sum(D[p][w]["breaks"] for w in W)
    print(
      f"{p:10s} {(rg5-1)*100:+11.5f} {(rg7-1)*100:+11.5f} "
      f"{100*total_elig/total_cond:9.3f} {tw:11d} {fw:11d} {fx:9d} {br:9d}"
    )

print()
print("=== per-workload V1 ===")
print(f"{'workload':18s} {'vsG5%':>9s} {'vsG7%':>9s} {'act%':>8s} {'TAGE MPKI':>10s} {'final MPKI':>11s} {'fix':>7s} {'break':>7s}")
for w in W:
    d=D["v1"][w]
    print(
      f"{w:18s} {(d['cycles']/B[w]['g5']-1)*100:9.3f} "
      f"{(d['cycles']/B[w]['g7']-1)*100:9.3f} {d['activation']:8.3f} "
      f"{1000*d['tage_wrong']/d['inst']:10.4f} {d['final_mpki']:11.4f} "
      f"{d['fixes']:7d} {d['breaks']:7d}"
    )

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
      "profile","workload","cycles","g5Cycles","g7Cycles","activationPct",
      "tageWrong","finalWrong","finalMPKI","fixes","breaks","overrides","trainings"
    ])
    for p in P:
        for w in W:
            d=D[p][w]
            wr.writerow([
              p,w,d["cycles"],B[w]["g5"],B[w]["g7"],
              f"{d['activation']:.9f}",d["tage_wrong"],d["final_wrong"],
              f"{d['final_mpki']:.9f}",d["fixes"],d["breaks"],
              d["overrides"],d["trainings"]
            ])

print()
print("BPU_B6_STORAGE_GATE=PASS")
print("BPU_B6_FINAL_ERROR_RECONCILIATION=PASS")
print("BPU_B6_SEED_FULL19=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-6_perceptron_seed_full19"
  echo "base=G5-45K"
  echo "perceptron_entries=64"
  echo "perceptron_history=24"
  echo "perceptron_weight_bits=6"
  echo "perceptron_train_threshold=60"
  echo "perceptron_override_threshold=0"
  echo "profiles=v1,wm,always"
  echo "v1_gate=weak_or_medium_or_strength5"
  echo "perceptron_weight_state_bits=9600"
  echo "combined_state_bits=55336"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B6_PROVENANCE=PASS"
