#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_p21313_steering_recovery}"
BASE_ROOT="${BASE_ROOT:-rv64_p21313_writecap_control}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)
POLICIES=(least-used round-robin int1-first)
MODES=(stock N4)

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
  --bp-inst-shift 1
)

echo "[0/4] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/4] Verify baseline R3 exists and refresh exact RV64 Embench"
[[ -f "$BASE_ROOT/summary.csv" ]] || {
  echo "ERROR: missing baseline $BASE_ROOT/summary.csv; run R3 first" >&2
  exit 2
}
EMBENCH_DIR="$EMBENCH_DIR" EMBENCH_BUILD="$EMBENCH_BUILD" \
  bash scripts/rv64_embench_prepare.sh

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
  local w="$1" policy="$2" mode="$3"
  local bin="$EMBENCH_BUILD/src/$w/$w"
  local out="$OUT_ROOT/$w/$policy/$mode"
  local narg=()
  [[ "$mode" == "N4" ]] && narg=(--n-skip 4)

  mkdir -p "$(dirname "$out")"
  "$GEM5" --outdir="$out" "$CFG" \
    --binary "$bin" \
    "${COMMON[@]}" \
    --int-steering "$policy" \
    "${narg[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: failed $w/$policy/$mode" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 3
  }
  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/4] Run 36-point P21313 steering recovery matrix"
for w in "${WORKLOADS[@]}"; do
  for p in "${POLICIES[@]}"; do
    for m in "${MODES[@]}"; do
      echo "  $w / $p / $m"
      run_one "$w" "$p" "$m"
    done
  done
done

echo "[3/4] Validate and summarize"
python3 - "$OUT_ROOT" "$BASE_ROOT" <<'PY'
import csv, math, pathlib, sys

root=pathlib.Path(sys.argv[1])
base=pathlib.Path(sys.argv[2])
workloads=["matmult-int","nettle-sha256","nettle-aes","sglib-combined","wikisort","picojpeg"]
policies=["least-used","round-robin","int1-first"]
modes=["stock","N4"]

def read(path):
    d={"maxOff":0,"dispatch":[0]*5,"alu":[0]*5,"mul":[0]*5,"w1":[0]*5,"w2":[0]*5,"w3":[0]*5}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        k,v=p[0],p[1]
        try: x=float(v)
        except: continue
        if k=="simInsts": d["insts"]=int(x)
        elif k=="simTicks": d["ticks"]=int(x)
        elif k.endswith(".numCycles") and "cores0.core" in k: d.setdefault("cycles",int(x))
        elif ".nSkipIssuedOffset::" in k:
            o=k.rsplit("::",1)[-1]
            if o.isdigit() and x>0: d["maxOff"]=max(d["maxOff"],int(o))
        else:
            for i in range(5):
                s=f"::IQ{i}"
                if k.endswith(".steerDispatches"+s): d["dispatch"][i]+=int(x)
                elif k.endswith(".steerIntAluDispatches"+s): d["alu"][i]+=int(x)
                elif k.endswith(".steerIntMultDispatches"+s): d["mul"][i]+=int(x)
                elif k.endswith(".dispatchWrite1Cycles"+s): d["w1"][i]+=int(x)
                elif k.endswith(".dispatchWrite2Cycles"+s): d["w2"][i]+=int(x)
                elif k.endswith(".dispatchWrite3PlusCycles"+s): d["w3"][i]+=int(x)
    if "cycles" not in d: d["cycles"]=round(d["ticks"]*1.4e9/1e12)
    return d

data={w:{p:{m:read(root/w/p/m/"roi.stats") for m in modes} for p in policies} for w in workloads}

# Load R3 first-fit P21313 + 33313 references.
refs={}
with (base/"summary.csv").open() as f:
    for row in csv.DictReader(f):
        w=row["workload"]; p=row["profile"]; m=row["mode"]
        refs.setdefault(w,{}).setdefault(p,{})[m]={
            "cycles":int(row["cycles"]), "insts":int(row["simInsts"])
        }

for w in workloads:
    expected={refs[w]["P21313"][m]["insts"] for m in modes}
    for p in policies:
        for m in modes:
            expected.add(data[w][p][m]["insts"])
            if m=="N4" and data[w][p][m]["maxOff"]>4:
                raise SystemExit(f"ERROR: offset>{4}: {w}/{p}")
    if len(expected)!=1:
        raise SystemExit(f"ERROR: simInsts mismatch {w}: {sorted(expected)}")

def pct(a,b): return (a/b-1)*100
def gm(vals): return math.exp(sum(math.log(x) for x in vals)/len(vals))

print()
print("=== RV64 R3b: P21313 steering recovery ===")
hdr=f"{'workload':18s} {'FFstock':>9s} {'LU%':>8s} {'RR%':>8s} {'I1F%':>8s} {'333%':>8s} {'FFN4%':>8s} {'LU_N4%':>8s} {'RR_N4%':>8s} {'I1F_N4%':>9s}"
print(hdr)

for w in workloads:
    ff=refs[w]["P21313"]["stock"]["cycles"]
    c3=refs[w]["C33313"]["stock"]["cycles"]
    ffn4=refs[w]["P21313"]["N4"]["cycles"]
    vals={p:data[w][p]["stock"]["cycles"] for p in policies}
    n4={p:data[w][p]["N4"]["cycles"] for p in policies}
    print(
        f"{w:18s} {ff:9d} "
        f"{pct(vals['least-used'],ff):8.3f} {pct(vals['round-robin'],ff):8.3f} {pct(vals['int1-first'],ff):8.3f} "
        f"{pct(c3,ff):8.3f} {pct(ffn4,ff):8.3f} "
        f"{pct(n4['least-used'],vals['least-used']):8.3f} "
        f"{pct(n4['round-robin'],vals['round-robin']):8.3f} "
        f"{pct(n4['int1-first'],vals['int1-first']):9.3f}"
    )

print()
print("=== Geomean vs P21313 first-fit stock ===")
for p in policies:
    ratio=gm([data[w][p]["stock"]["cycles"]/refs[w]["P21313"]["stock"]["cycles"] for w in workloads])
    n4res=gm([data[w][p]["N4"]["cycles"]/data[w][p]["stock"]["cycles"] for w in workloads])
    vs333=gm([data[w][p]["stock"]["cycles"]/refs[w]["C33313"]["stock"]["cycles"] for w in workloads])
    print(f"{p:12s}: stock delta={pct(ratio,1):+7.3f}%  N4 residual={pct(n4res,1):+7.3f}%  vs333={pct(vs333,1):+7.3f}%")

print()
print("=== Matmult routing diagnostic (stock) ===")
w="matmult-int"
for p in policies:
    d=data[w][p]["stock"]
    total_alu=d["alu"][0]+d["alu"][1]
    i0=100*d["alu"][0]/total_alu if total_alu else 0
    i1=100*d["alu"][1]/total_alu if total_alu else 0
    print(
        f"{p:12s}: cycles={d['cycles']} INT0_ALU={d['alu'][0]} ({i0:.1f}%) "
        f"INT1_ALU={d['alu'][1]} ({i1:.1f}%) INT0_MUL={d['mul'][0]} "
        f"INT0_2write_cycles={d['w2'][0]} INT1_1write_cycles={d['w1'][1]}"
    )

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","policy","mode","cycles","simInsts","maxOffset",
                 "INT0_ALU","INT1_ALU","INT0_MUL","INT0_w2","INT1_w1"])
    for w in workloads:
        for p in policies:
            for m in modes:
                d=data[w][p][m]
                wr.writerow([w,p,m,d["cycles"],d["insts"],d["maxOff"],
                             d["alu"][0],d["alu"][1],d["mul"][0],d["w2"][0],d["w1"][1]])

print()
print("All 36 recovery runs verified; simInsts match baseline and N4 offsets obey <=4.")
PY

echo "[4/4] Write manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "baseline=$BASE_ROOT"
  echo "caps=P21313:2,1,3,1,3"
  echo "queues=10,6,12,4,6"
  echo "policies=least-used,round-robin,int1-first"
  echo "modes=stock,N4"
  echo "purpose=diagnose first-fit x asymmetric write-cap interaction; no final retune implied until measured"
} >"$OUT_ROOT/manifest.txt"

echo "Summary: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
