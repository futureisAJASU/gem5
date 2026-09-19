#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_execution_tile_integration}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

DIV_BIN="$ROOT/benchmarks/bin/rv64_div_fairness"
FMA_BIN="$ROOT/benchmarks/bin/rv64_fma16_stress"

COMMON=(
  --cores 2
  --distributed-iq
  --local-iq-picker
  --int-steering int1-first
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
  --n-skip 4
  --pair-shared-div
  --pair-shared-fpsimd
  --div-reactive-power
  --div-idle-threshold 8
  --div-wake-latency 4
  --bp-inst-shift 1
)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Build directed RV64 workloads"
bash scripts/build_benchmarks_rv64.sh
[[ -x "$DIV_BIN" ]] || { echo "ERROR: missing $DIV_BIN" >&2; exit 2; }
[[ -x "$FMA_BIN" ]] || { echo "ERROR: missing $FMA_BIN" >&2; exit 2; }

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

run_case() {
  local pairing="$1"
  local wake="$2"
  local suffix="${3:-main}"
  local out="$OUT_ROOT/$pairing/$wake/$suffix"
  local core0 core1
  local wake_args=()

  case "$pairing" in
    divdiv) core0="$DIV_BIN"; core1="$DIV_BIN" ;;
    fmafma) core0="$FMA_BIN"; core1="$FMA_BIN" ;;
    divfma) core0="$DIV_BIN"; core1="$FMA_BIN" ;;
    *) echo "ERROR: unknown pairing $pairing" >&2; exit 3 ;;
  esac

  case "$wake" in
    B0) ;;
    B1) wake_args=(--div-decode-wake) ;;
    B2) wake_args=(--div-raw-wake) ;;
    *) echo "ERROR: unknown wake mode $wake" >&2; exit 3 ;;
  esac

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" "$CFG" \
    --binary "$core0" \
    --core-binary "$core0" \
    --core-binary "$core1" \
    "${COMMON[@]}" \
    "${wake_args[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: self-check failed: $pairing/$wake/$suffix" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 4
  fi
}

echo "[2/5] Run 9-point combined integration matrix"
for pairing in divdiv fmafma divfma; do
  for wake in B0 B1 B2; do
    echo "  $pairing / $wake"
    run_case "$pairing" "$wake"
  done
done

echo "[3/5] Deterministic repeat: mixed DIV/FMA under B2"
run_case divfma B2 repeat

echo "[4/5] Validate counters, bounds, fairness, and repeatability"
python3 - "$OUT_ROOT" <<'PY'
import csv
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
pairings = ["divdiv", "fmafma", "divfma"]
wakes = ["B0", "B1", "B2"]

def read_stats(path):
    d = {
        "maxOff": 0,
        "div_g": [0,0],
        "div_cg": [0,0],
        "div_contended": 0,
        "fp_g": [0,0],
        "fp_cg": [0,0],
        "fp_contended": 0,
        "blocked": 0,
        "reactive": 0,
        "decode": 0,
        "raw": 0,
        "decode_matched": 0,
        "decode_expired": 0,
        "raw_matched": 0,
        "raw_expired": 0,
    }
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        k,v=p[0],p[1]
        try:
            x=int(float(v))
        except ValueError:
            continue
        if k=="simTicks":
            d["ticks"]=x
        elif k=="simInsts":
            d["insts"]=x
        elif ".nSkipIssuedOffset::" in k:
            o=k.rsplit("::",1)[-1]
            if o.isdigit() and x>0:
                d["maxOff"]=max(d["maxOff"],int(o))
        elif k.endswith(".instQueues3.fuPool.pairRequesterGrants::requester0"):
            d["div_g"][0]+=x
        elif k.endswith(".instQueues3.fuPool.pairRequesterGrants::requester1"):
            d["div_g"][1]+=x
        elif k.endswith(".instQueues3.fuPool.pairContendedRequesterGrants::requester0"):
            d["div_cg"][0]+=x
        elif k.endswith(".instQueues3.fuPool.pairContendedRequesterGrants::requester1"):
            d["div_cg"][1]+=x
        elif k.endswith(".instQueues3.fuPool.pairContendedGrants"):
            d["div_contended"]+=x
        elif k.endswith(".instQueues4.fuPool.pairRequesterGrants::requester0"):
            d["fp_g"][0]+=x
        elif k.endswith(".instQueues4.fuPool.pairRequesterGrants::requester1"):
            d["fp_g"][1]+=x
        elif k.endswith(".instQueues4.fuPool.pairContendedRequesterGrants::requester0"):
            d["fp_cg"][0]+=x
        elif k.endswith(".instQueues4.fuPool.pairContendedRequesterGrants::requester1"):
            d["fp_cg"][1]+=x
        elif k.endswith(".instQueues4.fuPool.pairContendedGrants"):
            d["fp_contended"]+=x
        elif k.endswith(".instQueues3.fuPool.reactivePowerBlockedRequests"):
            d["blocked"]+=x
        elif k.endswith(".instQueues3.fuPool.reactiveWakeTransitions"):
            d["reactive"]+=x
        elif k.endswith(".instQueues3.fuPool.decodeWakeTransitions"):
            d["decode"]+=x
        elif k.endswith(".instQueues3.fuPool.rawWakeTransitions"):
            d["raw"]+=x
        elif k.endswith(".instQueues3.fuPool.decodeWakeDemandMatched"):
            d["decode_matched"]+=x
        elif k.endswith(".instQueues3.fuPool.decodeWakeExpired"):
            d["decode_expired"]+=x
        elif k.endswith(".instQueues3.fuPool.rawWakeDemandMatched"):
            d["raw_matched"]+=x
        elif k.endswith(".instQueues3.fuPool.rawWakeExpired"):
            d["raw_expired"]+=x
    if "ticks" not in d or "insts" not in d:
        raise RuntimeError(f"missing basic stats in {path}")
    return d

data={}
for pairing in pairings:
    data[pairing]={}
    for wake in wakes:
        data[pairing][wake]=read_stats(root/pairing/wake/"main"/"stats.txt")

repeat=read_stats(root/"divfma"/"B2"/"repeat"/"stats.txt")

# Core correctness/integration gates.
for pairing in pairings:
    insts={data[pairing][w]["insts"] for w in wakes}
    if len(insts)!=1:
        raise SystemExit(f"ERROR: simInsts changed across wake modes for {pairing}: {sorted(insts)}")
    for wake in wakes:
        d=data[pairing][wake]
        if d["maxOff"]>4:
            raise SystemExit(f"ERROR: N4 offset bound violated: {pairing}/{wake} maxOff={d['maxOff']}")

# Required domain activity.
for wake in wakes:
    d=data["divdiv"][wake]
    if d["div_g"][0]==0 or d["div_g"][1]==0:
        raise SystemExit(f"ERROR: DIV/DIV requester activity missing in {wake}")
    if d["div_contended"]==0:
        raise SystemExit(f"ERROR: DIV/DIV contention missing in {wake}")

    f=data["fmafma"][wake]
    if f["fp_g"][0]==0 or f["fp_g"][1]==0:
        raise SystemExit(f"ERROR: FMA/FMA requester activity missing in {wake}")
    if f["fp_contended"]==0:
        raise SystemExit(f"ERROR: FMA/FMA contention missing in {wake}")

    m=data["divfma"][wake]
    if sum(m["div_g"])==0 or sum(m["fp_g"])==0:
        raise SystemExit(f"ERROR: mixed run did not activate both shared domains in {wake}")

# Wake-mode semantics. B0 may reactive-wake; B1 must exercise decode; B2 raw.
if data["divdiv"]["B1"]["decode"]==0:
    raise SystemExit("ERROR: B1 decode wake was never exercised")
if data["divdiv"]["B2"]["raw"]==0:
    raise SystemExit("ERROR: B2 raw wake was never exercised")

# Deterministic replay gate on top-level and integration counters.
main=data["divfma"]["B2"]
keys=[
    "ticks","insts","maxOff","div_g","div_cg","div_contended",
    "fp_g","fp_cg","fp_contended","blocked","reactive","decode","raw",
    "decode_matched","decode_expired","raw_matched","raw_expired",
]
for k in keys:
    if main[k]!=repeat[k]:
        raise SystemExit(
            f"ERROR: B2 mixed repeat mismatch for {k}: main={main[k]} repeat={repeat[k]}"
        )

print()
print("=== RV64 R4: final-candidate execution-tile integration ===")
print(
    f"{'pairing':8s} {'wake':4s} {'ticks':>12s} {'insts':>10s} {'off':>4s} "
    f"{'DIV g0/g1':>17s} {'DIV cont':>9s} {'FP g0/g1':>17s} {'FP cont':>9s} "
    f"{'blocked':>8s} {'react':>7s} {'dec':>7s} {'raw':>7s}"
)
for pairing in pairings:
    for wake in wakes:
        d=data[pairing][wake]
        print(
            f"{pairing:8s} {wake:4s} {d['ticks']:12d} {d['insts']:10d} {d['maxOff']:4d} "
            f"{d['div_g'][0]:8d}/{d['div_g'][1]:8d} {d['div_contended']:9d} "
            f"{d['fp_g'][0]:8d}/{d['fp_g'][1]:8d} {d['fp_contended']:9d} "
            f"{d['blocked']:8d} {d['reactive']:7d} {d['decode']:7d} {d['raw']:7d}"
        )

print()
print("=== Wake deltas vs B0 ===")
for pairing in pairings:
    b0=data[pairing]["B0"]["ticks"]
    b1=data[pairing]["B1"]["ticks"]
    b2=data[pairing]["B2"]["ticks"]
    print(
        f"{pairing:8s}: B1-B0={(b1/b0-1)*100:+.4f}%  "
        f"B2-B0={(b2/b0-1)*100:+.4f}%  B2-B1={(b2/b1-1)*100:+.4f}%"
    )

d=data["divdiv"]["B2"]
print()
print("=== B2 DIV fairness diagnostic ===")
print(
    f"total grants: requester0={d['div_g'][0]} requester1={d['div_g'][1]} "
    f"abs_diff={abs(d['div_g'][0]-d['div_g'][1])}"
)
print(
    f"contended grants: requester0={d['div_cg'][0]} requester1={d['div_cg'][1]} "
    f"abs_diff={abs(d['div_cg'][0]-d['div_cg'][1])}"
)
print("No universal fairness theorem is implied; this is a directed service-count diagnostic.")

print()
print("=== Deterministic repeat ===")
print(f"divfma/B2 ticks={main['ticks']} repeated exactly; all selected counters identical.")
print()
print("R4 PASS gates satisfied: all 10 runs self-checked, N4 offsets <=4, both shared domains exercised, wake paths exercised, and B2 mixed repeat was deterministic.")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "pairing","wake","ticks","insts","maxOffset",
        "div_g0","div_g1","div_cg0","div_cg1","div_contended",
        "fp_g0","fp_g1","fp_cg0","fp_cg1","fp_contended",
        "blocked","reactive","decode","raw","decode_matched","decode_expired",
        "raw_matched","raw_expired",
    ])
    for pairing in pairings:
        for wake in wakes:
            d=data[pairing][wake]
            wr.writerow([
                pairing,wake,d["ticks"],d["insts"],d["maxOff"],
                *d["div_g"],*d["div_cg"],d["div_contended"],
                *d["fp_g"],*d["fp_cg"],d["fp_contended"],
                d["blocked"],d["reactive"],d["decode"],d["raw"],
                d["decode_matched"],d["decode_expired"],d["raw_matched"],d["raw_expired"],
            ])
PY

echo "[5/5] Write provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "config_sha256=$(sha256sum "$CFG" | awk '{print $1}')"
  echo "runner_sha256=$(sha256sum scripts/rv64_execution_tile_integration.sh | awk '{print $1}')"
  echo "div_binary_sha256=$(sha256sum "$DIV_BIN" | awk '{print $1}')"
  echo "fma_binary_sha256=$(sha256sum "$FMA_BIN" | awk '{print $1}')"
  echo "cores=2"
  echo "scheduler=P21313"
  echo "steering=int1-first"
  echo "local_picker=enabled"
  echo "n_skip=4"
  echo "visibility=Head..Head+4 (up to 5 positions)"
  echo "pair_shared_div=enabled"
  echo "pair_shared_fpsimd=enabled"
  echo "div_power=B0 reactive,B1 decode-predictive,B2 raw-predecode"
  echo "div_idle_threshold=8"
  echo "div_wake_latency=4"
  echo "bp_inst_shift=1"
  echo "pairings=DIV/DIV,FMA/FMA,DIV/FMA"
  echo "deterministic_repeat=DIV/FMA B2"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
