#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_ROOT="${OUT_ROOT:-rv64_p21313_i1f_n5_closeout}"
BASE_ROOT="${BASE_ROOT:-rv64_p21313_steering_recovery}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
SKIP_BUILD="${SKIP_BUILD:-1}"
JOBS="${JOBS:-$(nproc)}"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

COMMON=(
  --distributed-iq
  --local-iq-picker
  --dist-int0 10
  --dist-int1 6
  --dist-mem 12
  --dist-div 4
  --dist-fpsimd 6
  --dist-int0-write-cap 2
  --dist-int1-write-cap 1
  --dist-mem-write-cap 3
  --dist-div-write-cap 1
  --dist-fpsimd-write-cap 3
  --int-steering int1-first
  --bp-inst-shift 1
)

if [[ "$SKIP_BUILD" == "1" ]]; then
  echo "[0/4] Reuse current gem5/RISCV"
  [[ -x "$GEM5" ]] || {
    echo "ERROR: missing $GEM5; rerun with SKIP_BUILD=0" >&2
    exit 2
  }
else
  echo "[0/4] Build current gem5/RISCV"
  scons build/RISCV/gem5.opt -j"$JOBS"
fi

echo "[1/4] Verify R3b stock/N4 baseline and binaries"
[[ -f "$BASE_ROOT/summary.csv" ]] || {
  echo "ERROR: missing $BASE_ROOT/summary.csv" >&2
  exit 2
}

for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing RV64 Embench binary $EMBENCH_BUILD/src/$w/$w" >&2
    exit 2
  }
done

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1" dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ { section++; if (section==1) keep=1 }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst"
}

run_one() {
  local w="$1"
  local bin="$EMBENCH_BUILD/src/$w/$w"
  local out="$OUT_ROOT/$w/N5"
  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" "$CFG" \
    --binary "$bin" \
    "${COMMON[@]}" \
    --n-skip 5 \
    >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: failed $w/int1-first/N5" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 3
  }
  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/4] Run final 6-point RV64 int1-first N5 closeout"
for w in "${WORKLOADS[@]}"; do
  echo "  $w / int1-first / N5"
  run_one "$w"
done

echo "[3/4] Validate against R3b stock/N4 and summarize"
python3 - "$OUT_ROOT" "$BASE_ROOT" <<'PY'
import csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1])
base=pathlib.Path(sys.argv[2])
workloads=[
    "matmult-int","nettle-sha256","nettle-aes",
    "sglib-combined","wikisort","picojpeg",
]

def read_stats(path):
    d={"maxOff":0}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        k,v=p[0],p[1]
        try:
            x=float(v)
        except ValueError:
            continue
        if k=="simInsts":
            d["insts"]=int(x)
        elif k=="simTicks":
            d["ticks"]=int(x)
        elif k.endswith(".numCycles") and (
            "cores0.core" in k
            or "processor.cores0.core" in k
            or "processor.cores.core" in k
            or "cpu.numCycles" in k
        ):
            d.setdefault("cycles",int(x))
        elif ".nSkipIssuedOffset::" in k:
            off=k.rsplit("::",1)[-1]
            if off.isdigit() and x>0:
                d["maxOff"]=max(d["maxOff"],int(off))
    if "cycles" not in d:
        # RV64 R3b historically reported via ticks when no matching numCycles
        # counter was exported. Keep the same conversion convention here.
        d["cycles"]=round(d["ticks"]*1.4e9/1e12)
    return d

baseline={}
with (base/"summary.csv").open() as f:
    for row in csv.DictReader(f):
        if row["policy"]!="int1-first":
            continue
        baseline.setdefault(row["workload"],{})[row["mode"]]={
            "cycles":int(row["cycles"]),
            "insts":int(row["simInsts"]),
            "maxOff":int(row["maxOffset"]),
        }

for w in workloads:
    if set(baseline.get(w,{})) != {"stock","N4"}:
        raise SystemExit(f"ERROR: incomplete R3b int1-first baseline for {w}")

n5={w:read_stats(root/w/"N5"/"roi.stats") for w in workloads}

for w in workloads:
    expected={baseline[w]["stock"]["insts"], baseline[w]["N4"]["insts"], n5[w]["insts"]}
    if len(expected)!=1:
        raise SystemExit(f"ERROR: simInsts mismatch {w}: {sorted(expected)}")
    if baseline[w]["N4"]["maxOff"]>4:
        raise SystemExit(f"ERROR: existing N4 offset >4 for {w}")
    if n5[w]["maxOff"]>5:
        raise SystemExit(f"ERROR: N5 offset >5 for {w}")

def pct(a,b):
    return (a/b-1.0)*100.0

def gm(vals):
    return math.exp(sum(math.log(x) for x in vals)/len(vals))

print()
print("=== RV64 R3c: final int1-first N4/N5 closeout ===")
print(f"{'workload':18s} {'stock':>10s} {'N4%':>9s} {'N5%':>9s} {'N4->N5':>10s} {'N5off':>6s}")
for w in workloads:
    s=baseline[w]["stock"]["cycles"]
    n4=baseline[w]["N4"]["cycles"]
    v=n5[w]["cycles"]
    n4p=pct(n4,s)
    n5p=pct(v,s)
    print(f"{w:18s} {s:10d} {n4p:9.3f} {n5p:9.3f} {n4p-n5p:10.3f} {n5[w]['maxOff']:6d}")

n4_gm=gm([baseline[w]["N4"]["cycles"]/baseline[w]["stock"]["cycles"] for w in workloads])
n5_gm=gm([n5[w]["cycles"]/baseline[w]["stock"]["cycles"] for w in workloads])

print()
print("=== Aggregate ===")
print(f"int1-first N4 residual: {(n4_gm-1)*100:+.6f}%")
print(f"int1-first N5 residual: {(n5_gm-1)*100:+.6f}%")
print(f"N4 -> N5 geomean gain: {(n4_gm-n5_gm)*100:+.6f} percentage points")
print("All six N5 runs verified; simInsts match R3b and issued offsets obey <=5.")
print("This closes final-steering N4/N5 sensitivity; it does not redefine N-SKIP N4 as a universal optimum.")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","stock_cycles","N4_cycles","N5_cycles","N4_pct","N5_pct","N4_to_N5_pp","N5_max_offset","simInsts"])
    for w in workloads:
        s=baseline[w]["stock"]["cycles"]
        n4=baseline[w]["N4"]["cycles"]
        v=n5[w]["cycles"]
        wr.writerow([
            w,s,n4,v,
            f"{pct(n4,s):.9f}",
            f"{pct(v,s):.9f}",
            f"{pct(n4,s)-pct(v,s):.9f}",
            n5[w]["maxOff"],n5[w]["insts"],
        ])
PY

echo "[4/4] Write provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "config_sha256=$(sha256sum "$CFG" | awk '{print $1}')"
  echo "baseline=$BASE_ROOT"
  echo "queues=10,6,12,4,6"
  echo "caps=P21313:2,1,3,1,3"
  echo "steering=int1-first"
  echo "baseline_modes=stock,N4"
  echo "new_mode=N5"
  echo "purpose=close final-steering N4/N5 sensitivity before R6"
  echo "claim_boundary=evaluated_workloads_only;N4_not_universal_optimum"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
