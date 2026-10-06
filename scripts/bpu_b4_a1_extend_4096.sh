#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1_extension_4096}"
PRIOR_ROOT="${PRIOR_ROOT:-bpu_b4a1_extension_2048}"
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

echo "[1/5] Verify prior 2048-point evidence and Embench binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing Embench binary for $w" >&2
    exit 2
  }
  [[ -f "$PRIOR_ROOT/$w/e2048/roi.stats" ]] || {
    echo "ERROR: missing prior A1 e2048 ROI for $w" >&2
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

echo "[2/5] Run 4096-entry native extension point on frozen six-workload subset"
for w in "${WORKLOADS[@]}"; do
  bin="$EMBENCH_BUILD/src/$w/$w"
  out="$OUT_ROOT/$w/e4096"
  mkdir -p "$out"
  echo "  $w / entries=4096"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --micro-tage-tagged-entries 4096     --micro-tage-fixed-index-hash-log 0     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $w/e4096 gem5 exited rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $w/e4096 benchmark verification failed" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
done

echo "[3/5] Compare 2048 -> 4096 and evaluate endpoint rule"
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
BITS_2048=88678
BITS_4096=174694

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
print("=== BPU-4 A1 native endpoint extension: 2048 -> 4096 entries/table ===")
print(
    f"{'workload':18s} {'e2048 cyc':>11s} {'MPKI':>9s} "
    f"{'e4096 cyc':>11s} {'vs2048%':>9s} {'MPKI':>9s}"
)

for w in workloads:
    s1=parse(prior/w/"e2048"/"roi.stats")
    s2=parse(root/w/"e4096"/"roi.stats")

    c1=round(one(s1,"simTicks")*1.4e9/1e12)
    c2=round(one(s2,"simTicks")*1.4e9/1e12)
    i1=int(one(s1,"simInsts"))
    i2=int(one(s2,"simInsts"))
    w1=int(one(s1,"committedConditionalWrong"))
    w2=int(one(s2,"committedConditionalWrong"))
    b1=int(one(s1,"storageBits"))
    b2=int(one(s2,"storageBits"))
    committed2=int(one(s2,"committedConditionalPredictions"))
    metadata2=int(one(s2,"predictionMetadataChecks"))
    restores2=int(one(s2,"historyStateRestores"))
    restore_checks2=int(one(s2,"historyRestoreChecks"))

    if i1 != i2:
        raise SystemExit(f"ERROR {w}: simInsts changed {i1} -> {i2}")
    if b1 != BITS_2048:
        raise SystemExit(f"ERROR {w}: prior e2048 storage {b1} != {BITS_2048}")
    if b2 != BITS_4096:
        raise SystemExit(f"ERROR {w}: e4096 storage {b2} != {BITS_4096}")
    if metadata2 != committed2:
        raise SystemExit(f"ERROR {w}: metadata checks != committed conditionals")
    if restore_checks2 != restores2:
        raise SystemExit(f"ERROR {w}: restore checks != restores")

    cp=configparser.ConfigParser(strict=False)
    cp.optionxform=str
    cp.read(root/w/"e4096"/"config.ini")
    hits=[sec for sec in cp.sections()
          if sec.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(hits)!=1:
        raise SystemExit(f"ERROR {w}: TAGE config sections {hits}")
    sec=cp[hits[0]]

    if vec(sec["logTagTableSizes"]) != [11,12,12,12]:
        raise SystemExit(
            f"ERROR {w}: unexpected e4096 logTagTableSizes "
            f"{vec(sec['logTagTableSizes'])}"
        )
    if int(sec["fixedIndexHashLogSize"]) != 0:
        raise SystemExit(f"ERROR {w}: e4096 must be native hash mode")
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
    D[w]={"c2048":c1,"c4096":c2,"m2048":m1,"m4096":m2}

    print(
        f"{w:18s} {c1:11d} {m1:9.4f} "
        f"{c2:11d} {(c2/c1-1)*100:9.3f} {m2:9.4f}"
    )

ratio=gm([D[w]["c4096"]/D[w]["c2048"] for w in workloads])
benefit=1.0-ratio
max_small_reg=max(D[w]["c2048"]/D[w]["c4096"]-1.0 for w in workloads)
worst_small=max(
    workloads,
    key=lambda w: D[w]["c2048"]/D[w]["c4096"]-1.0
)

print()
print("=== extension geomean / guardrail ===")
print(f"e4096/e2048 = {ratio:.9f} ({(ratio-1)*100:+.5f}%)")
print(f"benefit e2048 -> e4096 = {benefit*100:+.5f}%")
print(
    f"max workload regression of e2048 vs e4096 = "
    f"{max_small_reg*100:+.5f}% ({worst_small})"
)

if benefit < KNEE and max_small_reg < GUARD:
    decision="2048"
else:
    decision="EXTEND_ABOVE_4096_REQUIRED"

print()
print("=== A1 endpoint decision ===")
print("geomean threshold = 0.5%")
print("per-workload next-larger guardrail = 2.0%")
print(f"BPU_B4_A1_FINAL_DECISION={decision}")

print()
print("=== exact persistent state ===")
print(f"2048 entries/table : {BITS_2048} bits = {BITS_2048/8192:.4f} KiB")
print(f"4096 entries/table : {BITS_4096} bits = {BITS_4096/8192:.4f} KiB")
print(
    f"storage growth 2048 -> 4096 = "
    f"{(BITS_4096/BITS_2048-1)*100:+.2f}%"
)

if all((tourn/w/"btb2"/"roi.stats").exists() for w in workloads):
    print()
    print("=== 4096 visibility vs Tournament canonical ===")
    ratios=[]
    worst=(-1e9,None)
    for w in workloads:
        ts=parse(tourn/w/"btb2"/"roi.stats")
        tc=round(one(ts,"simTicks")*1.4e9/1e12)
        r=D[w]["c4096"]/tc
        ratios.append(r)
        if r-1>worst[0]:
            worst=(r-1,w)
    gr=gm(ratios)
    print(f"e4096 geomean vs Tournament = {(gr-1)*100:+.5f}%")
    print(f"e4096 worst vs Tournament = {worst[1]} {worst[0]*100:+.5f}%")

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "workload","e2048_cycles","e2048_tageMPKI",
        "e4096_cycles","e4096_tageMPKI","e4096_vs_e2048_pct"
    ])
    for w in workloads:
        d=D[w]
        wr.writerow([
            w,d["c2048"],f"{d['m2048']:.9f}",
            d["c4096"],f"{d['m4096']:.9f}",
            f"{(d['c4096']/d['c2048']-1)*100:.9f}"
        ])

(root/"decision.txt").write_text(
    "axis=tagged_entries_per_table\n"
    "prior_endpoint=2048\n"
    "extension_point=4096\n"
    "geomean_knee_threshold=0.005\n"
    "per_workload_next_larger_guardrail=0.020\n"
    f"decision={decision}\n"
)

print()
print("BPU_B4_A1_4096_GEOMETRY_GATE=PASS")
print("BPU_B4_A1_4096_STORAGE_GATE=PASS")
print("BPU_B4_A1_4096_KNEE_EVALUATION=PASS")
PY

echo "[4/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "axis=tagged_entries_per_table"
  echo "prior_endpoint=2048"
  echo "extension_point=4096"
  echo "native_index_hash=on"
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
echo "BPU_B4_A1_4096_PROVENANCE=PASS"
