#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-a64_r2_historical_exact}"
HIST_ROOT="/home/ubuntu/gem5"
HIST_BUILD="/tmp/embench-aarch64-build"
HIST_GEM5="$HIST_ROOT/build/ARM/gem5.opt"
HIST_CFG="$HIST_ROOT/configs/01_little_v052_proxy.py"
CUR_GEM5="$ROOT/build/ARM/gem5.opt"
CUR_CFG="$ROOT/configs/01_little_v052_proxy.py"

EXPECTED_HIST_GEM5_SHA="0b5f20709d8f94cf568f2899d5794e89bd8f729d7bfef421d5f6b70c4f9ba0d0"
EXPECTED_HIST_CFG_SHA="db7d16fe6c6ddcb70c78b8dd9080a85968173f2d06021580106468a4b8f4b570"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

declare -A EXPECTED_BUILDID=(
  [matmult-int]="e976ee5ac66d37ce969cc7cf46127331d349fbba"
  [nettle-sha256]="7387e6292fe04229c91cca6e5d1a0b8dcbca68c3"
  [nettle-aes]="5dfdf7f839026be3e28834f83fb71a507864b98d"
  [sglib-combined]="0a6476e6c334807d25cd181e09c3a8a8ac65dfd0"
  [wikisort]="4328cd9b4158f4ba51e2c4b2dd04ea838a40b0f5"
  [picojpeg]="21ea195a1e9965226a73529b2a4eb6e0bec5c734"
)

declare -A HIST_STOCK_CYCLES=(
  [matmult-int]=1378554
  [nettle-sha256]=810409
  [nettle-aes]=1171939
  [sglib-combined]=1650077
  [wikisort]=216983
  [picojpeg]=1572159
)

declare -A HIST_N4_CYCLES=(
  [matmult-int]=1378554
  [nettle-sha256]=810401
  [nettle-aes]=1211262
  [sglib-combined]=1663043
  [wikisort]=218287
  [picojpeg]=1698448
)

build_id() {
  readelf -n "$1" 2>/dev/null | awk '/Build ID:/ {print $3; exit}'
}

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
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst"
}

read_cycle() {
  local stats="$1"
  awk '
    $1 ~ /cores0.core.numCycles$/ { print int($2); found=1; exit }
    END { if (!found) exit 1 }
  ' "$stats"
}

echo "=== A64 R2 HISTORICAL-EXACT REPLAY ==="

echo "[0/5] Verify surviving historical stack"
for f in "$HIST_GEM5" "$HIST_CFG"; do
  [[ -f "$f" ]] || { echo "ERROR: missing historical artifact: $f" >&2; exit 10; }
done

hist_gem5_sha="$(sha256sum "$HIST_GEM5" | awk '{print $1}')"
hist_cfg_sha="$(sha256sum "$HIST_CFG" | awk '{print $1}')"
if [[ "$hist_gem5_sha" != "$EXPECTED_HIST_GEM5_SHA" ]]; then
  echo "ERROR: historical gem5 SHA mismatch" >&2
  echo "got=$hist_gem5_sha expected=$EXPECTED_HIST_GEM5_SHA" >&2
  exit 10
fi
if [[ "$hist_cfg_sha" != "$EXPECTED_HIST_CFG_SHA" ]]; then
  echo "ERROR: historical config SHA mismatch" >&2
  echo "got=$hist_cfg_sha expected=$EXPECTED_HIST_CFG_SHA" >&2
  exit 10
fi

for w in "${WORKLOADS[@]}"; do
  bin="$HIST_BUILD/src/$w/$w"
  [[ -x "$bin" ]] || { echo "ERROR: missing historical binary $bin" >&2; exit 10; }
  bid="$(build_id "$bin")"
  if [[ "$bid" != "${EXPECTED_BUILDID[$w]}" ]]; then
    echo "ERROR: historical BuildID mismatch for $w" >&2
    echo "got=$bid expected=${EXPECTED_BUILDID[$w]}" >&2
    exit 10
  fi
done

echo "historical_stack_exact=YES"

echo "[1/5] Build current gem5/ARM"
scons build/ARM/gem5.opt -j"$JOBS"

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

run_hist() {
  local w="$1"
  local mode="$2"
  local n=-1
  [[ "$mode" == "N4" ]] && n=4
  local bin="$HIST_BUILD/src/$w/$w"
  local out="$OUT_ROOT/historical/$w/$mode"
  mkdir -p "$(dirname "$out")"

  "$HIST_GEM5" -d "$out" \
    "$HIST_CFG" \
    --binary "$bin" \
    --clock 1.4GHz \
    --width 3 \
    --commit-width 3 \
    --rob 80 \
    --iq 40 \
    --lq 12 \
    --sq 16 \
    --n-skip "$n" \
    >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: historical run failed $w/$mode" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 11
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats" || {
    echo "ERROR: failed ROI extraction $w/$mode" >&2
    exit 11
  }
}

echo "[2/5] Replay archived 12-point historical baseline with exact old stack"
for w in "${WORKLOADS[@]}"; do
  echo "  historical $w / stock"
  run_hist "$w" stock
  echo "  historical $w / N4"
  run_hist "$w" N4
done

echo "[3/5] Require cycle-exact historical reproduction"
for w in "${WORKLOADS[@]}"; do
  s="$(read_cycle "$OUT_ROOT/historical/$w/stock/roi.stats")"
  n="$(read_cycle "$OUT_ROOT/historical/$w/N4/roi.stats")"
  echo "$w stock=$s expected=${HIST_STOCK_CYCLES[$w]} N4=$n expected=${HIST_N4_CYCLES[$w]}"
  [[ "$s" -eq "${HIST_STOCK_CYCLES[$w]}" ]] || {
    echo "ERROR: historical stock cycle mismatch for $w" >&2
    exit 12
  }
  [[ "$n" -eq "${HIST_N4_CYCLES[$w]}" ]] || {
    echo "ERROR: historical N4 cycle mismatch for $w" >&2
    exit 12
  }
done
echo "historical_cycle_exact=YES"

P21313_COMMON=(
  --distributed-iq
  --local-iq-picker
  --int-steering first-fit
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
)

run_current() {
  local w="$1"
  local profile="$2"
  local mode="$3"
  local bin="$HIST_BUILD/src/$w/$w"
  local out="$OUT_ROOT/current/$w/$profile/$mode"
  local args=(--bp-inst-shift 2)
  local narg=()

  if [[ "$profile" == "p21313_s2" ]]; then
    args+=("${P21313_COMMON[@]}")
  elif [[ "$profile" != "central_s2" ]]; then
    echo "ERROR: bad profile $profile" >&2
    exit 2
  fi

  case "$mode" in
    stock) ;;
    N4) narg=(--n-skip 4) ;;
    N5) narg=(--n-skip 5) ;;
    *) echo "ERROR: bad mode $mode" >&2; exit 2 ;;
  esac

  mkdir -p "$(dirname "$out")"
  "$CUR_GEM5" --outdir="$out" \
    "$CUR_CFG" \
    --binary "$bin" \
    --clock 1.4GHz \
    --width 3 \
    --commit-width 3 \
    --rob 80 \
    --iq 40 \
    --lq 12 \
    --sq 16 \
    "${args[@]}" \
    "${narg[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: current run failed $w/$profile/$mode" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 13
  }
  extract_first_roi "$out/stats.txt" "$out/roi.stats" || exit 13
}

echo "[4/5] Run current central/P21313 using the exact historical binaries"
for w in "${WORKLOADS[@]}"; do
  for m in stock N4; do
    echo "  current $w / central_s2 / $m"
    run_current "$w" central_s2 "$m"
  done
  for m in stock N4 N5; do
    echo "  current $w / p21313_s2 / $m"
    run_current "$w" p21313_s2 "$m"
  done
done

echo "[5/5] Validate and summarize exact-binary R2"
python3 - "$OUT_ROOT" <<'PY'
import csv
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
workloads = [
    "matmult-int","nettle-sha256","nettle-aes",
    "sglib-combined","wikisort","picojpeg",
]

hist_expected = {
    "matmult-int": (1378554,1378554),
    "nettle-sha256": (810409,810401),
    "nettle-aes": (1171939,1211262),
    "sglib-combined": (1650077,1663043),
    "wikisort": (216983,218287),
    "picojpeg": (1572159,1698448),
}

def read(path):
    d={"maxOff":0,"hidden":0,"noVis":0}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        k,v=p[0],p[1]
        try: x=float(v)
        except ValueError: continue
        if k=="simInsts": d["insts"]=int(x)
        elif k=="simTicks": d["ticks"]=int(x)
        elif k.endswith(".numCycles") and "cores0.core" in k:
            d.setdefault("cycles",int(x))
        elif k.endswith(".nSkipLocalHiddenReadySamples"):
            d["hidden"]+=int(x)
        elif k.endswith(".nSkipLocalNoVisibleReadyCycles"):
            d["noVis"]+=int(x)
        elif ".nSkipIssuedOffset::" in k:
            o=k.rsplit("::",1)[-1]
            if o.isdigit() and x>0: d["maxOff"]=max(d["maxOff"],int(o))
    if "cycles" not in d:
        d["cycles"]=round(d["ticks"]*1.4e9/1e12)
    return d

hist={}
cur={}
for w in workloads:
    hist[w]={
        m:read(root/"historical"/w/m/"roi.stats")
        for m in ["stock","N4"]
    }
    cur[w]={
        "central_s2":{
            m:read(root/"current"/w/"central_s2"/m/"roi.stats")
            for m in ["stock","N4"]
        },
        "p21313_s2":{
            m:read(root/"current"/w/"p21313_s2"/m/"roi.stats")
            for m in ["stock","N4","N5"]
        },
    }

for w in workloads:
    hs,hn=hist_expected[w]
    assert hist[w]["stock"]["cycles"]==hs
    assert hist[w]["N4"]["cycles"]==hn
    insts={cur[w][p][m]["insts"] for p in cur[w] for m in cur[w][p]}
    if len(insts)!=1:
        raise SystemExit(f"ERROR: current simInsts mismatch {w}: {sorted(insts)}")
    if cur[w]["central_s2"]["N4"]["maxOff"]>4: raise SystemExit(f"ERROR offset {w} central N4")
    if cur[w]["p21313_s2"]["N4"]["maxOff"]>4: raise SystemExit(f"ERROR offset {w} P N4")
    if cur[w]["p21313_s2"]["N5"]["maxOff"]>5: raise SystemExit(f"ERROR offset {w} P N5")

def gap(d,mode):
    return (d[mode]["cycles"]/d["stock"]["cycles"]-1)*100

def gm(vals):
    return math.exp(sum(math.log(x) for x in vals)/len(vals))

print()
print("=== A64 R2 EXACT-HISTORICAL-BINARY RESULT ===")
print(
    f"{'workload':18s} {'histN4%':>9s} {'C2_N4%':>9s} {'P2_N4%':>9s} "
    f"{'P2_N5%':>9s} {'C2-P2':>9s} {'N4->N5':>9s} "
    f"{'Pstock/C2':>10s} {'PN4/C2':>9s}"
)

for w in workloads:
    h=gap(hist[w],"N4")
    c=gap(cur[w]["central_s2"],"N4")
    p4=gap(cur[w]["p21313_s2"],"N4")
    p5=gap(cur[w]["p21313_s2"],"N5")
    cstock=cur[w]["central_s2"]["stock"]["cycles"]
    pstock=cur[w]["p21313_s2"]["stock"]["cycles"]
    pn4=cur[w]["p21313_s2"]["N4"]["cycles"]
    print(
        f"{w:18s} {h:9.3f} {c:9.3f} {p4:9.3f} {p5:9.3f} "
        f"{c-p4:9.3f} {p4-p5:9.3f} "
        f"{(pstock/cstock-1)*100:10.3f} {(pn4/cstock-1)*100:9.3f}"
    )

hist_gm=gm([hist[w]["N4"]["cycles"]/hist[w]["stock"]["cycles"] for w in workloads])
c_gm=gm([cur[w]["central_s2"]["N4"]["cycles"]/cur[w]["central_s2"]["stock"]["cycles"] for w in workloads])
p4_gm=gm([cur[w]["p21313_s2"]["N4"]["cycles"]/cur[w]["p21313_s2"]["stock"]["cycles"] for w in workloads])
p5_gm=gm([cur[w]["p21313_s2"]["N5"]["cycles"]/cur[w]["p21313_s2"]["stock"]["cycles"] for w in workloads])
pstock_abs=gm([cur[w]["p21313_s2"]["stock"]["cycles"]/cur[w]["central_s2"]["stock"]["cycles"] for w in workloads])
pn4_abs=gm([cur[w]["p21313_s2"]["N4"]["cycles"]/cur[w]["central_s2"]["stock"]["cycles"] for w in workloads])

print()
print("=== Aggregate ===")
print(f"historical exact old-stack N4:         {(hist_gm-1)*100:+.3f}%")
print(f"current central shift2 N4:             {(c_gm-1)*100:+.3f}%")
print(f"current P21313 shift2 N4:              {(p4_gm-1)*100:+.3f}%")
print(f"current P21313 shift2 N5:              {(p5_gm-1)*100:+.3f}%")
print(f"P21313 stock vs central shift2 stock:  {(pstock_abs-1)*100:+.3f}%")
print(f"P21313 N4 vs central shift2 stock:     {(pn4_abs-1)*100:+.3f}%")
print("historical_cycle_exact=YES")
print("current_exact_historical_binaries=YES")
print("All current simInsts match per workload; issued offsets obey N4/N5 bounds.")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","stack","profile","mode","cycles","simInsts","gap_pct","max_offset","hidden","noVis"])
    for w in workloads:
        for m in ["stock","N4"]:
            d=hist[w][m]
            wr.writerow([w,"historical","central",m,d["cycles"],d["insts"],f"{gap(hist[w],m):.9f}",d["maxOff"],d["hidden"],d["noVis"]])
        for p in ["central_s2","p21313_s2"]:
            for m,d in cur[w][p].items():
                wr.writerow([w,"current",p,m,d["cycles"],d["insts"],f"{gap(cur[w][p],m):.9f}",d["maxOff"],d["hidden"],d["noVis"]])
PY

for w in "${WORKLOADS[@]}"; do
  sha256sum "$HIST_BUILD/src/$w/$w"
done >"$OUT_ROOT/historical_binary_sha256.txt"

{
  echo "historical_gem5_sha=$EXPECTED_HIST_GEM5_SHA"
  echo "historical_config_sha=$EXPECTED_HIST_CFG_SHA"
  echo "current_head=$(git rev-parse HEAD)"
  echo "current_gem5_sha=$(sha256sum "$CUR_GEM5" | awk '{print $1}')"
  echo "current_config_sha=$(sha256sum "$CUR_CFG" | awk '{print $1}')"
  echo "historical_binary_source=$HIST_BUILD"
  echo "historical_cycle_exact=required"
  echo "current_runs_use_exact_historical_binaries=YES"
  echo "current_bp_inst_shift=2"
  echo "current_P21313=2,1,3,1,3"
  echo "roi=first stats section between historical embedded reset/dump triggers"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "Historical binary hashes: $OUT_ROOT/historical_binary_sha256.txt"
