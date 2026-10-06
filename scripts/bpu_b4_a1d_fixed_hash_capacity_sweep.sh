#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b4a1d_fixed_hash_capacity}"
NATIVE_A1="${NATIVE_A1:-bpu_b4a1_tagged_entries_sweep}"
NATIVE_EXT="${NATIVE_EXT:-bpu_b4a1_extension_2048}"
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
ENTRIES=(512 1024 2048)
FIXED_HASH_LOG=11

echo "[0/6] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/6] Verify native A1 evidence and frozen-subset binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing Embench binary for $w" >&2
    exit 2
  }
  [[ -f "$NATIVE_A1/$w/e512/roi.stats" ]] || {
    echo "ERROR: missing native e512 ROI for $w" >&2
    exit 2
  }
  [[ -f "$NATIVE_A1/$w/e1024/roi.stats" ]] || {
    echo "ERROR: missing native e1024 ROI for $w" >&2
    exit 2
  }
  [[ -f "$NATIVE_EXT/$w/e2048/roi.stats" ]] || {
    echo "ERROR: missing native e2048 ROI for $w" >&2
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
  local entries="$2"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/e$entries"
  mkdir -p "$out"

  echo "  $workload / entries=$entries / fixed-hash-log=$FIXED_HASH_LOG"

  set +e
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type micro-tage     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --micro-tage-tagged-entries "$entries"     --micro-tage-fixed-index-hash-log "$FIXED_HASH_LOG"     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  local rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $workload/e$entries fixed-hash gem5 exited rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: $workload/e$entries benchmark verification failed" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/6] Run fixed-11 hash capacity sweep (3 points x 6 workloads = 18 ROI)"
for w in "${WORKLOADS[@]}"; do
  for e in "${ENTRIES[@]}"; do
    run_one "$w" "$e"
  done
done

echo "[3/6] Validate controlled geometry and 2048 positive-control convergence"
python3 - "$OUT_ROOT" "$NATIVE_A1" "$NATIVE_EXT" <<'PY'
import configparser
import csv
import math
import pathlib
import sys

root=pathlib.Path(sys.argv[1])
native_a1=pathlib.Path(sys.argv[2])
native_ext=pathlib.Path(sys.argv[3])

workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
entries=[512,1024,2048]
expected_bits={512:24166,1024:45670,2048:88678}
expected_logs={512:[11,9,9,9],1024:[11,10,10,10],2048:[11,11,11,11]}

def parse(path):
    scalars={}
    vectors={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        try:
            value=float(p[1])
        except ValueError:
            continue
        scalars[p[0]]=value
        if "::" in p[0]:
            base,idx=p[0].rsplit("::",1)
            if idx.isdigit():
                vectors.setdefault(base,{})[int(idx)]=value
    return scalars,vectors

def scalar(s,suffix):
    h=[v for k,v in s.items() if k.endswith(suffix)]
    if len(h)!=1:
        raise RuntimeError(f"{suffix}: expected one scalar, got {len(h)}")
    return h[0]

def vector(v,suffix):
    h=[x for k,x in v.items() if k.endswith(suffix)]
    if len(h)!=1:
        raise RuntimeError(f"{suffix}: expected one vector, got {len(h)}")
    return h[0]

def vec(raw):
    return [int(x) for x in raw.replace("[","").replace("]","").replace(","," ").split()]

def gm(xs):
    return math.exp(sum(math.log(x) for x in xs)/len(xs))

def native_path(w,e):
    if e == 2048:
        return native_ext/w/"e2048"/"roi.stats"
    return native_a1/w/f"e{e}"/"roi.stats"

D={}
rows=[]

for w in workloads:
    D[w]={}
    for e in entries:
        out=root/w/f"e{e}"
        s,v=parse(out/"roi.stats")

        cp=configparser.ConfigParser(strict=False)
        cp.optionxform=str
        cp.read(out/"config.ini")
        hits=[sec for sec in cp.sections()
              if sec.endswith(".branchPred.conditionalBranchPred.tage")]
        if len(hits)!=1:
            raise SystemExit(f"ERROR {w}/e{e}: TAGE config sections {hits}")
        sec=cp[hits[0]]

        if vec(sec["logTagTableSizes"]) != expected_logs[e]:
            raise SystemExit(
                f"ERROR {w}/e{e}: physical log sizes "
                f"{vec(sec['logTagTableSizes'])} != {expected_logs[e]}"
            )
        if int(sec["fixedIndexHashLogSize"]) != 11:
            raise SystemExit(
                f"ERROR {w}/e{e}: fixedIndexHashLogSize="
                f"{sec['fixedIndexHashLogSize']} != 11"
            )
        if vec(sec["explicitHistLengths"]) != [8,24,64]:
            raise SystemExit(f"ERROR {w}/e{e}: history lengths changed")
        if vec(sec["tagTableTagWidths"]) != [0,8,9,10]:
            raise SystemExit(f"ERROR {w}/e{e}: tag widths changed")
        if int(sec["nHistoryTables"]) != 3:
            raise SystemExit(f"ERROR {w}/e{e}: table count changed")
        if int(sec["instShiftAmt"]) != 1:
            raise SystemExit(f"ERROR {w}/e{e}: conditional shift changed")

        bits=int(scalar(s,"storageBits"))
        if bits != expected_bits[e]:
            raise SystemExit(
                f"ERROR {w}/e{e}: storage {bits} != {expected_bits[e]}"
            )

        cycles=round(scalar(s,"simTicks")*1.4e9/1e12)
        inst=int(scalar(s,"simInsts"))
        wrong=int(scalar(s,"committedConditionalWrong"))
        committed=int(scalar(s,"committedConditionalPredictions"))
        correct=int(scalar(s,"committedConditionalCorrect"))
        restores=int(scalar(s,"historyStateRestores"))
        restore_checks=int(scalar(s,"historyRestoreChecks"))
        metadata_checks=int(scalar(s,"predictionMetadataChecks"))
        if restore_checks != restores:
            raise SystemExit(
                f"ERROR {w}/e{e}: restore checks {restore_checks} != "
                f"restores {restores}"
            )
        if metadata_checks != committed:
            raise SystemExit(
                f"ERROR {w}/e{e}: metadata checks {metadata_checks} != "
                f"committed {committed}"
            )
        banks=vector(v,"selectedProviderBank")
        conf=vector(v,"providerConfidence")

        D[w][e]={
            "cycles":cycles,
            "inst":inst,
            "wrong":wrong,
            "committed":committed,
            "correct":correct,
            "banks":banks,
            "conf":conf,
            "mpki":1000.0*wrong/inst,
            "bits":bits,
        }

# Positive control: fixed-11 at physical 2048 must exactly match native 2048
# on all deterministic predictor/result metrics.
for w in workloads:
    ns,nv=parse(native_path(w,2048))
    c=D[w][2048]
    checks={
        "cycles":round(scalar(ns,"simTicks")*1.4e9/1e12),
        "inst":int(scalar(ns,"simInsts")),
        "wrong":int(scalar(ns,"committedConditionalWrong")),
        "committed":int(scalar(ns,"committedConditionalPredictions")),
        "correct":int(scalar(ns,"committedConditionalCorrect")),
    }
    for k,expected in checks.items():
        if c[k] != expected:
            raise SystemExit(
                f"ERROR positive-control {w}: controlled e2048 {k}={c[k]} "
                f"!= native e2048 {expected}"
            )
    if c["banks"] != vector(nv,"selectedProviderBank"):
        raise SystemExit(
            f"ERROR positive-control {w}: selectedProviderBank differs"
        )
    if c["conf"] != vector(nv,"providerConfidence"):
        raise SystemExit(
            f"ERROR positive-control {w}: providerConfidence differs"
        )

print("BPU_B4_A1D_2048_NATIVE_CONVERGENCE=PASS")

print()
print("=== BPU-4 A1D fixed-11 hash capacity sweep ===")
print(
    f"{'workload':18s} "
    f"{'e512 cyc':>10s} {'MPKI':>8s} "
    f"{'e1024 cyc':>10s} {'vs512%':>9s} {'MPKI':>8s} "
    f"{'e2048 cyc':>10s} {'vs1024%':>10s} {'MPKI':>8s}"
)
for w in workloads:
    a,b,c=D[w][512],D[w][1024],D[w][2048]
    print(
        f"{w:18s} "
        f"{a['cycles']:10d} {a['mpki']:8.4f} "
        f"{b['cycles']:10d} {(b['cycles']/a['cycles']-1)*100:9.3f} {b['mpki']:8.4f} "
        f"{c['cycles']:10d} {(c['cycles']/b['cycles']-1)*100:10.3f} {c['mpki']:8.4f}"
    )

ctrl_1024_512=gm([D[w][1024]["cycles"]/D[w][512]["cycles"] for w in workloads])
ctrl_2048_1024=gm([D[w][2048]["cycles"]/D[w][1024]["cycles"] for w in workloads])

native={}
for w in workloads:
    native[w]={}
    for e in entries:
        s,_=parse(native_path(w,e))
        native[w][e]=round(scalar(s,"simTicks")*1.4e9/1e12)

nat_1024_512=gm([native[w][1024]/native[w][512] for w in workloads])
nat_2048_1024=gm([native[w][2048]/native[w][1024] for w in workloads])

print()
print("=== controlled capacity effect vs native geometry effect ===")
print(
    f"512 -> 1024 controlled fixed-hash: "
    f"{(ctrl_1024_512-1)*100:+.5f}% cycles"
)
print(
    f"512 -> 1024 native geometry:       "
    f"{(nat_1024_512-1)*100:+.5f}% cycles"
)
print(
    f"1024 -> 2048 controlled fixed-hash: "
    f"{(ctrl_2048_1024-1)*100:+.5f}% cycles"
)
print(
    f"1024 -> 2048 native geometry:        "
    f"{(nat_2048_1024-1)*100:+.5f}% cycles"
)

print()
print("=== native-vs-controlled mapping sensitivity at equal capacity ===")
print(
    f"{'workload':18s} "
    f"{'e512 ctrl/native%':>18s} "
    f"{'e1024 ctrl/native%':>20s} "
    f"{'e2048 ctrl/native%':>20s}"
)
for w in workloads:
    vals=[]
    for e in entries:
        vals.append((D[w][e]["cycles"]/native[w][e]-1)*100)
    print(
        f"{w:18s} {vals[0]:18.3f} {vals[1]:20.3f} {vals[2]:20.3f}"
    )

for e in entries:
    ratio=gm([D[w][e]["cycles"]/native[w][e] for w in workloads])
    print(
        f"e{e} controlled/native geomean = "
        f"{(ratio-1)*100:+.5f}%"
    )

with (root/"summary.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "workload","entriesPerTable","controlledCycles","nativeCycles",
        "controlledVsNativePct","controlledTageMPKI","storageBits"
    ])
    for w in workloads:
        for e in entries:
            d=D[w][e]
            wr.writerow([
                w,e,d["cycles"],native[w][e],
                f"{(d['cycles']/native[w][e]-1)*100:.9f}",
                f"{d['mpki']:.9f}",d["bits"]
            ])

(root/"interpretation_guardrails.txt").write_text(
    "controlled_hash_log=11\n"
    "physical_points=512,1024,2048\n"
    "hash_pc_mix=fixed\n"
    "hash_global_fold_width=fixed\n"
    "hash_path_mix=fixed\n"
    "final_physical_index_mask=varies_with_capacity\n"
    "allocation_residency_provider_dynamics=allowed_to_vary_as_capacity_effects\n"
    "native_2048_convergence=required\n"
    "note=controlled_vs_native differences are mapping sensitivity, not an additive causal decomposition\n"
)

print()
print("BPU_B4_A1D_FIXED_HASH_GEOMETRY_GATE=PASS")
print("BPU_B4_A1D_STORAGE_GATE=PASS")
print("BPU_B4_A1D_CAPACITY_ISOLATION_SWEEP=PASS")
PY

echo "[4/6] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "diagnostic=fixed_index_hash_capacity_isolation"
  echo "fixed_index_hash_log=11"
  echo "physical_entries_per_table=512,1024,2048"
  echo "fixed_bimodal_entries=2048"
  echo "fixed_tables=3"
  echo "fixed_histories=8,24,64"
  echo "fixed_tags=8,9,10"
  echo "conditional_shift=1"
  echo "btb_shift=2"
  echo "indirect_shift=1"
  echo "btb_entries=4096"
  echo "positive_control=fixed11_e2048_must_match_native_e2048"
  echo "workloads=statemate,crc32,nsichneu,slre,sglib-combined,qrduino"
} >"$OUT_ROOT/manifest.txt"

echo "[5/6] Show no-rerun native provider/confidence delta"
if [[ -f scripts/bpu_b4_a1_provider_confidence_delta.sh ]]; then
  bash scripts/bpu_b4_a1_provider_confidence_delta.sh
else
  echo "NOTE: provider/confidence postprocessor missing; skip"
fi

echo "[6/6] Done"
echo "CSV: $OUT_ROOT/summary.csv"
echo "Guardrails: $OUT_ROOT/interpretation_guardrails.txt"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B4_A1D_PROVENANCE=PASS"
