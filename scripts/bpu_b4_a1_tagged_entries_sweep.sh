#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1_tagged_entries_sweep}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
TOURN_ROOT="${TOURN_ROOT:-bpu_b1_canonical_index_closure}"
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
ENTRIES=(256 512 1024)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Ensure frozen-subset Embench binaries exist"
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

run_one() {
  local workload="$1"
  local entries="$2"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/e$entries"
  mkdir -p "$out"

  echo "  $workload / entries=$entries"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --micro-tage-tagged-entries "$entries"     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  local rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $workload/e$entries gem5 exited rc=$rc" >&2
    tail -n 120 "$out.stdout" >&2 || true
    tail -n 120 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $workload/e$entries benchmark verification failed" >&2
    tail -n 120 "$out.stdout" >&2 || true
    tail -n 120 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/5] Run 3 tagged-entry points x 6 frozen workloads (18 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  for e in "${ENTRIES[@]}"; do
    run_one "$w" "$e"
  done
done

echo "[3/5] Verify emitted geometry and summarize A1"
python3 - "$OUT_ROOT" "$TOURN_ROOT" <<'PY'
import configparser
import csv
import math
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
tourn_root=pathlib.Path(sys.argv[2])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
entries=[256,512,1024]

KNEE_GEOMEAN_THRESHOLD=0.005
PER_WORKLOAD_GUARDRAIL=0.020

def parse_stats(path):
    s={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        try:
            s[p[0]]=float(p[1])
        except ValueError:
            pass
    return s

def scalar_suffix(s,suffix):
    h=[(k,v) for k,v in s.items() if k.endswith(suffix)]
    if len(h)!=1:
        raise RuntimeError(f"{suffix}: expected 1 hit, got {h}")
    return h[0][1]

def vec(raw):
    return [int(x) for x in raw.replace("[","").replace("]","").replace(","," ").split()]

def gm(vals):
    return math.exp(sum(math.log(x) for x in vals)/len(vals))

D={}
rows=[]
expected_bits={256:13414,512:24166,1024:45670}

for w in workloads:
    D[w]={}
    for e in entries:
        out=root/w/f"e{e}"
        s=parse_stats(out/"roi.stats")
        cycles=round(scalar_suffix(s,"simTicks")*1.4e9/1e12)
        inst=int(scalar_suffix(s,"simInsts"))
        wrong=int(scalar_suffix(s,"committedConditionalWrong"))
        storage=int(scalar_suffix(s,"storageBits"))
        mpki=1000.0*wrong/inst

        cp=configparser.ConfigParser(strict=False)
        cp.optionxform=str
        cp.read(out/"config.ini")
        hits=[sec for sec in cp.sections()
              if sec.endswith(".branchPred.conditionalBranchPred.tage")]
        if len(hits)!=1:
            raise SystemExit(f"ERROR {w}/e{e}: TAGE config sections {hits}")
        sec=cp[hits[0]]
        logs=vec(sec["logTagTableSizes"])
        tags=vec(sec["tagTableTagWidths"])
        hist=vec(sec["explicitHistLengths"])

        elog=e.bit_length()-1
        expected_logs=[11,elog,elog,elog]
        if logs != expected_logs:
            raise SystemExit(
                f"ERROR {w}/e{e}: logTagTableSizes={logs}, expected {expected_logs}"
            )
        if tags != [0,8,9,10]:
            raise SystemExit(f"ERROR {w}/e{e}: tag widths changed: {tags}")
        if hist != [8,24,64]:
            raise SystemExit(f"ERROR {w}/e{e}: history changed: {hist}")
        if int(sec["nHistoryTables"]) != 3:
            raise SystemExit(f"ERROR {w}/e{e}: table count changed")
        if int(sec["instShiftAmt"]) != 1:
            raise SystemExit(f"ERROR {w}/e{e}: conditional shift changed")
        if storage != expected_bits[e]:
            raise SystemExit(
                f"ERROR {w}/e{e}: storage={storage}, expected={expected_bits[e]}"
            )

        D[w][e]={"cycles":cycles,"inst":inst,"wrong":wrong,"mpki":mpki,"bits":storage}

for w in workloads:
    if len({D[w][e]["inst"] for e in entries}) != 1:
        raise SystemExit(f"ERROR {w}: simInsts differs across entry points")

print()
print("=== BPU-4 A1 tagged entries/table sweep ===")
print(
    f"{'workload':18s} "
    f"{'e256 cyc':>10s} {'vs512%':>8s} {'MPKI':>8s} "
    f"{'e512 cyc':>10s} {'MPKI':>8s} "
    f"{'e1024 cyc':>10s} {'vs512%':>8s} {'MPKI':>8s}"
)
for w in workloads:
    d256,d512,d1024=D[w][256],D[w][512],D[w][1024]
    print(
        f"{w:18s} "
        f"{d256['cycles']:10d} {(d256['cycles']/d512['cycles']-1)*100:8.3f} {d256['mpki']:8.4f} "
        f"{d512['cycles']:10d} {d512['mpki']:8.4f} "
        f"{d1024['cycles']:10d} {(d1024['cycles']/d512['cycles']-1)*100:8.3f} {d1024['mpki']:8.4f}"
    )

r256_512=gm([D[w][256]["cycles"]/D[w][512]["cycles"] for w in workloads])
r1024_512=gm([D[w][1024]["cycles"]/D[w][512]["cycles"] for w in workloads])
r512_256=1.0/r256_512
r1024_from512=r1024_512

improve_256_to_512=1.0-r512_256
improve_512_to_1024=1.0-r1024_from512
max_reg_256=max(D[w][256]["cycles"]/D[w][512]["cycles"]-1 for w in workloads)
max_reg_512=max(D[w][512]["cycles"]/D[w][1024]["cycles"]-1 for w in workloads)

print()
print("=== geomean ===")
print(f"e256/e512 = {r256_512:.9f} ({(r256_512-1)*100:+.5f}%)")
print(f"e1024/e512 = {r1024_512:.9f} ({(r1024_512-1)*100:+.5f}%)")
print(f"benefit e256 -> e512 = {improve_256_to_512*100:+.5f}%")
print(f"benefit e512 -> e1024 = {improve_512_to_1024*100:+.5f}%")
print(f"max workload regression e256 vs e512 = {max_reg_256*100:+.5f}%")
print(f"max workload regression e512 vs e1024 = {max_reg_512*100:+.5f}%")

print()
print("=== exact persistent state ===")
for e in entries:
    print(f"{e:4d} entries/table : {expected_bits[e]:6d} bits = {expected_bits[e]/8192:.4f} KiB")

# Predeclared sequential knee logic.
decision=""
if (
    improve_256_to_512 < KNEE_GEOMEAN_THRESHOLD
    and max_reg_256 < PER_WORKLOAD_GUARDRAIL
):
    decision="256"
elif (
    improve_512_to_1024 < KNEE_GEOMEAN_THRESHOLD
    and max_reg_512 < PER_WORKLOAD_GUARDRAIL
):
    decision="512"
else:
    decision="EXTEND_ABOVE_1024_REQUIRED"

print()
print("=== A1 knee rule ===")
print("geomean threshold = 0.5%")
print("per-workload next-larger guardrail = 2.0%")
print(f"BPU_B4_A1_DECISION={decision}")

# Tournament reference visibility only; not part of A1 knee arithmetic.
if all((tourn_root/w/"btb2"/"roi.stats").exists() for w in workloads):
    print()
    print("=== visibility vs Tournament canonical (not knee criterion) ===")
    for e in entries:
        ratios=[]
        worst=(-1e9,None)
        for w in workloads:
            ts=parse_stats(tourn_root/w/"btb2"/"roi.stats")
            tc=round(scalar_suffix(ts,"simTicks")*1.4e9/1e12)
            r=D[w][e]["cycles"]/tc
            ratios.append(r)
            if r-1>worst[0]:
                worst=(r-1,w)
        gr=gm(ratios)
        print(
            f"e{e}: geomean {(gr-1)*100:+.5f}% vs Tournament; "
            f"worst {worst[1]} {worst[0]*100:+.5f}%"
        )

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["workload","entriesPerTable","cycles","simInsts","tageWrong","tageMPKI","storageBits"])
    for w in workloads:
        for e in entries:
            d=D[w][e]
            wr.writerow([w,e,d["cycles"],d["inst"],d["wrong"],f"{d['mpki']:.9f}",d["bits"]])

(root/"decision.txt").write_text(
    "axis=tagged_entries_per_table\n"
    "points=256,512,1024\n"
    "geomean_knee_threshold=0.005\n"
    "per_workload_next_larger_guardrail=0.020\n"
    f"decision={decision}\n"
)

print()
print("BPU_B4_A1_GEOMETRY_GATE=PASS")
print("BPU_B4_A1_STORAGE_GATE=PASS")
print("BPU_B4_A1_KNEE_EVALUATION=PASS")
PY

echo "[4/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "axis=tagged_entries_per_table"
  echo "points=256,512,1024"
  echo "fixed_bimodal_entries=2048"
  echo "fixed_tables=3"
  echo "fixed_histories=8,24,64"
  echo "fixed_tags=8,9,10"
  echo "conditional_shift=1"
  echo "btb_shift=2"
  echo "indirect_shift=1"
  echo "btb_entries=4096"
  echo "geomean_knee_threshold=0.005"
  echo "per_workload_next_larger_guardrail=0.020"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Decision: $OUT_ROOT/decision.txt"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4_A1_PROVENANCE=PASS"
