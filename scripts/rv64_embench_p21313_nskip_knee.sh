#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_embench_p21313_nskip_knee}"
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
MODES=(stock N4 N5 N6)

COMMON=(
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
  --bp-inst-shift 1
)

echo "[0/3] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/3] Ensure exact RV64 Embench binaries exist"
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

  if ! grep -q '^---------- Begin Simulation Statistics ----------' "$dst"; then
    echo "ERROR: failed to extract first ROI from $src" >&2
    exit 4
  fi
}

run_one() {
  local workload="$1"
  local mode="$2"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/$mode"
  local narg=()

  case "$mode" in
    stock) ;;
    N4) narg=(--n-skip 4) ;;
    N5) narg=(--n-skip 5) ;;
    N6) narg=(--n-skip 6) ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     "${COMMON[@]}"     "${narg[@]}"     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $workload/$mode failed benchmark verification" >&2
    cat "$out.stdout" >&2
    exit 5
  fi

  extract_first_roi "$out/stats.txt" "$out/roi.stats"

  if [[ "$mode" != "stock" ]] &&
     ! grep -q 'nSkipLocalHiddenReadySamples' "$out/roi.stats"; then
    echo "ERROR: local N-SKIP stats missing for $workload/$mode" >&2
    exit 6
  fi
}

echo "[2/3] Run P21313 distributed stock/N4/N5/N6 screen (24 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  for mode in "${MODES[@]}"; do
    echo "  $w / $mode"
    run_one "$w" "$mode"
  done
done

echo "[3/3] Validate and summarize"
python3 - "$OUT_ROOT" <<'PY'
import csv
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
workloads = [
    "matmult-int",
    "nettle-sha256",
    "nettle-aes",
    "sglib-combined",
    "wikisort",
    "picojpeg",
]
modes = ["stock", "N4", "N5", "N6"]
bounds = {"N4": 4, "N5": 5, "N6": 6}

def read_stats(path):
    vals = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, val = p[0], p[1]
        try:
            num = float(val)
        except ValueError:
            continue

        if key == "simTicks":
            vals["simTicks"] = int(num)
        elif key == "simInsts":
            vals["simInsts"] = int(num)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            vals.setdefault("cycles", int(num))
        elif key.endswith(".nSkipLocalHiddenReadySamples"):
            vals["hidden"] = vals.get("hidden", 0) + int(num)
        elif key.endswith(".nSkipLocalNoVisibleReadyCycles"):
            vals["noVis"] = vals.get("noVis", 0) + int(num)
        elif ".nSkipIssuedOffset::" in key:
            name = key.rsplit("::", 1)[-1]
            if name.isdigit() and num > 0:
                vals["maxOff"] = max(vals.get("maxOff", 0), int(name))

    if "simTicks" not in vals or "simInsts" not in vals:
        raise RuntimeError(f"missing ROI stats in {path}")
    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)
    vals.setdefault("hidden", 0)
    vals.setdefault("noVis", 0)
    vals.setdefault("maxOff", 0)
    return vals

data = {
    w: {m: read_stats(root / w / m / "roi.stats") for m in modes}
    for w in workloads
}

for w in workloads:
    insts = data[w]["stock"]["simInsts"]
    for m in modes[1:]:
        d = data[w][m]
        if d["simInsts"] != insts:
            raise SystemExit(f"ERROR: simInsts mismatch {w}/{m}")
        if d["maxOff"] > bounds[m]:
            raise SystemExit(
                f"ERROR: {w}/{m} maxOff={d['maxOff']} > N={bounds[m]}"
            )

print()
print("=== RV64 P21313 distributed Embench N-SKIP knee ===")
print(
    f"{'workload':18s} "
    f"{'N4%':>9s} {'N5%':>9s} {'N6%':>9s} "
    f"{'N4->N5':>10s} {'N5->N6':>10s} "
    f"{'N4_hidden':>12s} {'N5_hidden':>12s} "
    f"{'N4_noVis':>11s} {'N5_noVis':>11s}"
)

rows = []
for w in workloads:
    stock = data[w]["stock"]["cycles"]
    gaps = {
        m: (data[w][m]["cycles"] / stock - 1.0) * 100.0
        for m in modes[1:]
    }
    print(
        f"{w:18s} "
        f"{gaps['N4']:9.3f} {gaps['N5']:9.3f} {gaps['N6']:9.3f} "
        f"{(gaps['N4']-gaps['N5']):10.3f} "
        f"{(gaps['N5']-gaps['N6']):10.3f} "
        f"{data[w]['N4']['hidden']:12d} {data[w]['N5']['hidden']:12d} "
        f"{data[w]['N4']['noVis']:11d} {data[w]['N5']['noVis']:11d}"
    )
    rows.append((w, gaps))

print()
print("=== P21313 geomean cycle overhead vs distributed stock ===")
for m in modes[1:]:
    ratios = [
        data[w][m]["cycles"] / data[w]["stock"]["cycles"]
        for w in workloads
    ]
    gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
    print(f"{m}: {(gm - 1.0) * 100:+.3f}%")

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","mode","cycles","simInsts","gap_to_stock_pct",
        "max_offset","hidden_ready_samples","no_visible_ready_cycles"
    ])
    for w in workloads:
        stock = data[w]["stock"]["cycles"]
        for m in modes:
            d = data[w][m]
            gap = (d["cycles"] / stock - 1.0) * 100.0
            wr.writerow([
                w,m,d["cycles"],d["simInsts"],f"{gap:.9f}",
                d["maxOff"],d["hidden"],d["noVis"]
            ])

print()
print("All 24 runs verified; simInsts match stock within each workload; issued offsets obey configured bounds.")
print(f"CSV: {root / 'summary.csv'}")
PY

{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "bp_inst_shift=1"
  echo "scheduler=P21313 distributed local picker"
  echo "queues=INT0:10/2,INT1:6/1,MEM:12/3,DIV:4/1,FP_SIMD:6/3"
  echo "configs=stock,N4,N5,N6"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
} >"$OUT_ROOT/manifest.txt"

echo "Manifest: $OUT_ROOT/manifest.txt"
