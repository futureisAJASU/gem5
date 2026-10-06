#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1_extension_2048}"
PRIOR_ROOT="${PRIOR_ROOT:-bpu_b4a1_tagged_entries_sweep}"
TOURN_ROOT="${TOURN_ROOT:-bpu_b1_canonical_index_closure}"
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

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify prior 1024-point evidence and Embench binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing Embench binary for $w" >&2
    exit 2
  }
  [[ -f "$PRIOR_ROOT/$w/e1024/roi.stats" ]] || {
    echo "ERROR: missing prior A1 e1024 ROI for $w" >&2
    echo "Expected: $PRIOR_ROOT/$w/e1024/roi.stats" >&2
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

echo "[2/5] Run 2048-entry extension point on frozen six-workload subset"
for w in "${WORKLOADS[@]}"; do
  bin="$EMBENCH_BUILD/src/$w/$w"
  out="$OUT_ROOT/$w/e2048"
  mkdir -p "$out"
  echo "  $w / entries=2048"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --micro-tage-tagged-entries 2048     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $w/e2048 gem5 exited rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $w/e2048 benchmark verification failed" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
done

echo "[3/5] Compare 1024 -> 2048 and evaluate endpoint rule"
python3 - "$OUT_ROOT" "$PRIOR_ROOT" "$TOURN_ROOT" <<'PY'
import configparser
import csv
import math
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
prior=pathlib.Path(sys.argv[2])
tourn=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]

KNEE=0.005
GUARD=0.020
BITS_1024=45670
BITS_2048=88678

def parse(path):
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

def one(s,suffix):
    h=[v for k,v in s.items() if k.endswith(suffix)]
    if len(h)!=1:
        raise RuntimeError(f"{suffix}: {len(h)} hits")
    return h[0]

def vec(raw):
    return [int(x) for x in raw.replace("[","").replace("]","").replace(","," ").split()]

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))

D={}
print()
print("=== BPU-4 A1 endpoint extension: 1024 -> 2048 entries/table ===")
print(
    f"{'workload':18s} {'e1024 cyc':>11s} {'MPKI':>9s} "
    f"{'e2048 cyc':>11s} {'vs1024%':>9s} {'MPKI':>9s}"
)

for w in workloads:
    s1=parse(prior/w/"e1024"/"roi.stats")
    s2=parse(root/w/"e2048"/"roi.stats")

    c1=round(one(s1,"simTicks")*1.4e9/1e12)
    c2=round(one(s2,"simTicks")*1.4e9/1e12)
    i1=int(one(s1,"simInsts"))
    i2=int(one(s2,"simInsts"))
    w1=int(one(s1,"committedConditionalWrong"))
    w2=int(one(s2,"committedConditionalWrong"))
    b1=int(one(s1,"storageBits"))
    b2=int(one(s2,"storageBits"))

    if i1 != i2:
        raise SystemExit(f"ERROR {w}: simInsts changed {i1} -> {i2}")
    if b1 != BITS_1024:
        raise SystemExit(f"ERROR {w}: prior e1024 storage {b1} != {BITS_1024}")
    if b2 != BITS_2048:
        raise SystemExit(f"ERROR {w}: e2048 storage {b2} != {BITS_2048}")

    cp=configparser.ConfigParser(strict=False)
    cp.optionxform=str
    cp.read(root/w/"e2048"/"config.ini")
    hits=[sec for sec in cp.sections()
          if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(hits)!=1:
        raise SystemExit(f"ERROR {w}: TAGE config sections {hits}")
    sec=cp[hits[0]]
    if vec(sec["logTagTableSizes"]) != [11,11,11,11]:
        raise SystemExit(
            f"ERROR {w}: unexpected e2048 logTagTableSizes "
            f"{vec(sec['logTagTableSizes'])}"
        )
    if vec(sec["explicitHistLengths"]) != [8,24,64]:
        raise SystemExit(f"ERROR {w}: history axis changed")
    if vec(sec["tagTableTagWidths"]) != [0,8,9,10]:
        raise SystemExit(f"ERROR {w}: tag-width axis changed")
    if int(sec["nHistoryTables"]) != 3:
        raise SystemExit(f"ERROR {w}: table count changed")
    if int(sec["instShiftAmt"]) != 1:
        raise SystemExit(f"ERROR {w}: conditional shift changed")

    m1=1000.0*w1/i1
    m2=1000.0*w2/i2
    D[w]={"c1024":c1,"c2048":c2,"m1024":m1,"m2048":m2}

    print(
        f"{w:18s} {c1:11d} {m1:9.4f} "
        f"{c2:11d} {(c2/c1-1)*100:9.3f} {m2:9.4f}"
    )

ratio=gm([D[w]["c2048"]/D[w]["c1024"] for w in workloads])
benefit=1.0-ratio
max_small_reg=max(D[w]["c1024"]/D[w]["c2048"]-1.0 for w in workloads)
worst_small=max(
    workloads,
    key=lambda w: D[w]["c1024"]/D[w]["c2048"]-1.0
)

print()
print("=== extension geomean / guardrail ===")
print(f"e2048/e1024 = {ratio:.9f} ({(ratio-1)*100:+.5f}%)")
print(f"benefit e1024 -> e2048 = {benefit*100:+.5f}%")
print(
    f"max workload regression of e1024 vs e2048 = "
    f"{max_small_reg*100:+.5f}% ({worst_small})"
)

if benefit < KNEE and max_small_reg < GUARD:
    decision="1024"
else:
    decision="EXTEND_ABOVE_2048_REQUIRED"

print()
print("=== A1 endpoint decision ===")
print("geomean threshold = 0.5%")
print("per-workload next-larger guardrail = 2.0%")
print(f"BPU_B4_A1_FINAL_DECISION={decision}")

print()
print("=== exact persistent state ===")
print(f"1024 entries/table : {BITS_1024} bits = {BITS_1024/8192:.4f} KiB")
print(f"2048 entries/table : {BITS_2048} bits = {BITS_2048/8192:.4f} KiB")
print(
    f"storage growth 1024 -> 2048 = "
    f"{(BITS_2048/BITS_1024-1)*100:+.2f}%"
)

if all((tourn/w/"btb2"/"roi.stats").exists() for w in workloads):
    print()
    print("=== 2048 visibility vs Tournament canonical ===")
    ratios=[]
    worst=(-1e9,None)
    for w in workloads:
        ts=parse(tourn/w/"btb2"/"roi.stats")
        tc=round(one(ts,"simTicks")*1.4e9/1e12)
        r=D[w]["c2048"]/tc
        ratios.append(r)
        if r-1>worst[0]:
            worst=(r-1,w)
    gr=gm(ratios)
    print(f"e2048 geomean vs Tournament = {(gr-1)*100:+.5f}%")
    print(f"e2048 worst vs Tournament = {worst[1]} {worst[0]*100:+.5f}%")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "workload","e1024_cycles","e1024_tageMPKI",
        "e2048_cycles","e2048_tageMPKI","e2048_vs_e1024_pct"
    ])
    for w in workloads:
        d=D[w]
        wr.writerow([
            w,d["c1024"],f"{d['m1024']:.9f}",
            d["c2048"],f"{d['m2048']:.9f}",
            f"{(d['c2048']/d['c1024']-1)*100:.9f}"
        ])

(root/"decision.txt").write_text(
    "axis=tagged_entries_per_table\n"
    "prior_endpoint=1024\n"
    "extension_point=2048\n"
    "geomean_knee_threshold=0.005\n"
    "per_workload_next_larger_guardrail=0.020\n"
    f"decision={decision}\n"
)

print()
print("BPU_B4_A1_EXTENSION_GEOMETRY_GATE=PASS")
print("BPU_B4_A1_EXTENSION_STORAGE_GATE=PASS")
print("BPU_B4_A1_EXTENSION_KNEE_EVALUATION=PASS")
PY

echo "[4/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "axis=tagged_entries_per_table"
  echo "prior_endpoint=1024"
  echo "extension_point=2048"
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
echo "BPU_B4_A1_EXTENSION_PROVENANCE=PASS"
