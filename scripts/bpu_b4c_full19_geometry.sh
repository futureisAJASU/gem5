#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4c_full19_geometry}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
TOURN_ROOT="${TOURN_ROOT:-bpu_b1_canonical_index_closure}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  aha-mont64
  crc32
  cubic
  edn
  huffbench
  matmult-int
  minver
  nbody
  nettle-aes
  nettle-sha256
  nsichneu
  picojpeg
  qrduino
  sglib-combined
  slre
  st
  statemate
  ud
  wikisort
)

PROFILES=(
  micro1024
  g5
  stock
  g7
  micro2048
)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify full Embench corpus binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing Embench binary for $w" >&2
    exit 2
  }
done

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
  local profile="$2"
  local out="$OUT_ROOT/$profile/$workload"
  mkdir -p "$out"

  local bp_type=""
  local extra=()
  case "$profile" in
    micro1024)
      bp_type="micro-tage"
      extra+=(--micro-tage-tagged-entries 1024)
      ;;
    g5)
      bp_type="tage5-iso45k"
      ;;
    stock)
      bp_type="tage"
      ;;
    g7)
      bp_type="tage7-iso65k"
      ;;
    micro2048)
      bp_type="micro-tage"
      extra+=(--micro-tage-tagged-entries 2048)
      ;;
    *)
      echo "ERROR: unknown profile $profile" >&2
      exit 3
      ;;
  esac

  echo "  $workload / $profile"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$EMBENCH_BUILD/src/$workload/$workload"     --bp-type "$bp_type"     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     "${extra[@]}"     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $workload/$profile rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: benchmark verification failed for $workload/$profile" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/5] Run 5 frozen predictor profiles x 19 workloads = 95 ROI"
for p in "${PROFILES[@]}"; do
  for w in "${WORKLOADS[@]}"; do
    run_one "$w" "$p"
  done
done

echo "[3/5] Validate state/correctness and summarize full-19 robustness"
python3 - "$OUT_ROOT" "$TOURN_ROOT" <<'PY'
import csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1])
tourn=pathlib.Path(sys.argv[2])

workloads=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
profiles=["micro1024","g5","stock","g7","micro2048"]
expected_bits={
  "micro1024":45670,
  "g5":45736,
  "stock":65192,
  "g7":65192,
  "micro2048":88678,
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
    if len(h)!=1:
        raise RuntimeError(f"{suf}: {h}")
    return h[0]

def cycles(s):
    return round(one(s,"simTicks")*1.4e9/1e12)

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))

D={p:{} for p in profiles}

for p in profiles:
    for w in workloads:
        s=parse(root/p/w/"roi.stats")
        bits=int(one(s,"storageBits"))
        if bits != expected_bits[p]:
            raise SystemExit(f"ERROR {p}/{w}: storage {bits} != {expected_bits[p]}")
        committed=int(one(s,"committedConditionalPredictions"))
        if int(one(s,"predictionMetadataChecks")) != committed:
            raise SystemExit(f"ERROR {p}/{w}: metadata checks")
        if int(one(s,"historyRestoreChecks")) != int(one(s,"historyStateRestores")):
            raise SystemExit(f"ERROR {p}/{w}: rollback checks")
        inst=int(one(s,"simInsts"))
        wrong=int(one(s,"committedConditionalWrong"))
        D[p][w]={
          "cycles":cycles(s),
          "inst":inst,
          "mpki":1000.0*wrong/inst,
          "cond":committed,
        }

for w in workloads:
    insts={D[p][w]["inst"] for p in profiles}
    if len(insts)!=1:
        raise SystemExit(f"ERROR {w}: simInsts differ across profiles: {insts}")

print()
print("=== BPU-4C full-19 geometry robustness ===")
print("bits: micro1024=45670 G5=45736 stock=65192 G7=65192 micro2048=88678")
print()
print(f"{'workload':18s} {'m3-45K':>10s} {'G5-45K':>10s} {'stock65K':>10s} {'G7-65K':>10s} {'m3-89K':>10s}")
for w in workloads:
    print(
      f"{w:18s} "
      f"{D['micro1024'][w]['cycles']:10d} "
      f"{D['g5'][w]['cycles']:10d} "
      f"{D['stock'][w]['cycles']:10d} "
      f"{D['g7'][w]['cycles']:10d} "
      f"{D['micro2048'][w]['cycles']:10d}"
    )

comparisons=[
 ("G5/micro1024","g5","micro1024"),
 ("G7/stock","g7","stock"),
 ("G5/stock","g5","stock"),
 ("G7/micro1024","g7","micro1024"),
 ("G7/micro2048","g7","micro2048"),
 ("stock/micro2048","stock","micro2048"),
]

print()
print("=== full-19 geomean ratios ===")
for label,a,b in comparisons:
    r=gm([D[a][w]["cycles"]/D[b][w]["cycles"] for w in workloads])
    wins=sum(D[a][w]["cycles"] < D[b][w]["cycles"] for w in workloads)
    losses=sum(D[a][w]["cycles"] > D[b][w]["cycles"] for w in workloads)
    ties=len(workloads)-wins-losses
    print(f"{label:20s} = {r:.9f} ({(r-1)*100:+.5f}%) W/L/T={wins}/{losses}/{ties}")

if all((tourn/w/"btb2"/"roi.stats").exists() for w in workloads):
    print()
    print("=== full-19 vs Tournament canonical ===")
    T={}
    for w in workloads:
        T[w]=cycles(parse(tourn/w/"btb2"/"roi.stats"))
    for p in profiles:
        r=gm([D[p][w]["cycles"]/T[w] for w in workloads])
        worst=max(workloads,key=lambda w:D[p][w]["cycles"]/T[w]-1)
        worstpct=(D[p][worst]["cycles"]/T[worst]-1)*100
        print(f"{p:12s}: geomean {(r-1)*100:+.5f}% ; worst {worst} {worstpct:+.5f}%")

print()
print("=== largest G5-vs-micro1024 deltas ===")
delta5=sorted(
    ((D["g5"][w]["cycles"]/D["micro1024"][w]["cycles"]-1,w) for w in workloads)
)
for d,w in delta5[:5]:
    print(f"best  {w:18s} {d*100:+.5f}%")
for d,w in reversed(delta5[-5:]):
    print(f"worst {w:18s} {d*100:+.5f}%")

print()
print("=== largest G7-vs-stock deltas ===")
delta7=sorted(
    ((D["g7"][w]["cycles"]/D["stock"][w]["cycles"]-1,w) for w in workloads)
)
for d,w in delta7[:5]:
    print(f"best  {w:18s} {d*100:+.5f}%")
for d,w in reversed(delta7[-5:]):
    print(f"worst {w:18s} {d*100:+.5f}%")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
      "workload","micro1024Cycles","micro1024MPKI",
      "g5Cycles","g5MPKI","stockCycles","stockMPKI",
      "g7Cycles","g7MPKI","micro2048Cycles","micro2048MPKI"
    ])
    for w in workloads:
        wr.writerow([
          w,
          D["micro1024"][w]["cycles"],f"{D['micro1024'][w]['mpki']:.9f}",
          D["g5"][w]["cycles"],f"{D['g5'][w]['mpki']:.9f}",
          D["stock"][w]["cycles"],f"{D['stock'][w]['mpki']:.9f}",
          D["g7"][w]["cycles"],f"{D['g7'][w]['mpki']:.9f}",
          D["micro2048"][w]["cycles"],f"{D['micro2048'][w]['mpki']:.9f}",
        ])

print()
print("BPU_B4C_FULL19_STORAGE_GATE=PASS")
print("BPU_B4C_FULL19_CORRECTNESS_GATE=PASS")
print("BPU_B4C_FULL19_ROBUSTNESS=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-4C_full19_geometry_robustness"
  echo "profiles=micro1024,g5,stock,g7,micro2048"
  echo "condition=cond1,btb2,indirect1,btb4096_direct_proxy"
  echo "workloads=aha-mont64,crc32,cubic,edn,huffbench,matmult-int,minver,nbody,nettle-aes,nettle-sha256,nsichneu,picojpeg,qrduino,sglib-combined,slre,st,statemate,ud,wikisort"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4C_FULL19_PROVENANCE=PASS"
