#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_embench_nskip_knee}"
SCREEN_ROOT="${SCREEN_ROOT:-rv64_embench_screen}"
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
MODES=(stock N4 N5 N6 N8)

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

  grep -q '^---------- Begin Simulation Statistics ----------' "$dst"
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
    N8) narg=(--n-skip 8) ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  mkdir -p "$(dirname "$out")"
  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-inst-shift 1     "${narg[@]}"     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $workload/$mode failed benchmark verification" >&2
    cat "$out.stdout" >&2
    exit 5
  fi

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[2/3] Run stock/N4/N5/N6/N8 knee sweep (30 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  for mode in "${MODES[@]}"; do
    echo "  $w / $mode"
    run_one "$w" "$mode"
  done
done

echo "[3/3] Validate reproducibility, bounds, and summarize"
python3 - "$OUT_ROOT" "$SCREEN_ROOT" <<'PY'
import csv
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
screen_root = pathlib.Path(sys.argv[2])
workloads = [
    "matmult-int",
    "nettle-sha256",
    "nettle-aes",
    "sglib-combined",
    "wikisort",
    "picojpeg",
]
modes = ["stock", "N4", "N5", "N6", "N8"]
bounds = {"N4":4, "N5":5, "N6":6, "N8":8}

def read_stats(path):
    vals = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, val = p[0], p[1]
        if key == "simTicks":
            vals["simTicks"] = int(val)
        elif key == "simInsts":
            vals["simInsts"] = int(val)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            try:
                vals.setdefault("cycles", int(float(val)))
            except ValueError:
                pass
        elif ".nSkipIssuedOffset::" in key:
            name = key.rsplit("::", 1)[-1]
            if name.isdigit() and float(val) > 0:
                vals["maxOff"] = max(vals.get("maxOff", 0), int(name))
    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)
    vals.setdefault("maxOff", 0)
    return vals

data = {
    w: {m: read_stats(root / w / m / "roi.stats") for m in modes}
    for w in workloads
}

# Architectural self-consistency.
for w in workloads:
    base_inst = data[w]["stock"]["simInsts"]
    for m in modes[1:]:
        if data[w][m]["simInsts"] != base_inst:
            raise SystemExit(f"ERROR: simInsts mismatch {w}/{m}")
        if data[w][m]["maxOff"] > bounds[m]:
            raise SystemExit(
                f"ERROR: {w}/{m} issued offset {data[w][m]['maxOff']} > {bounds[m]}"
            )

# Exact rerun reproducibility against the previous stock/N4 screen when present.
prev = {}
summary = screen_root / "summary.csv"
if summary.exists():
    with summary.open(newline="") as f:
        for row in csv.DictReader(f):
            prev[row["workload"]] = (
                int(row["stock_cycles"]),
                int(row["n4_cycles"]),
            )

print()
print("=== exact rerun reproducibility vs prior screen ===")
print(f"{'workload':18s} {'stock_old':>11s} {'stock_new':>11s} {'N4_old':>11s} {'N4_new':>11s} {'status':>9s}")
all_exact = True
for w in workloads:
    if w not in prev:
        print(f"{w:18s} {'-':>11s} {data[w]['stock']['cycles']:11d} {'-':>11s} {data[w]['N4']['cycles']:11d} {'NO_BASE':>9s}")
        all_exact = False
        continue
    so, no = prev[w]
    sn, nn = data[w]["stock"]["cycles"], data[w]["N4"]["cycles"]
    exact = (so == sn and no == nn)
    all_exact &= exact
    print(f"{w:18s} {so:11d} {sn:11d} {no:11d} {nn:11d} {('EXACT' if exact else 'DIFF'):>9s}")

print()
print("=== RV64 centralized N-SKIP near-knee sweep ===")
print(f"{'workload':18s} {'N4%':>9s} {'N5%':>9s} {'N6%':>9s} {'N8%':>9s} {'N4->N5':>10s}")
rows = []
for w in workloads:
    stock = data[w]["stock"]["cycles"]
    gaps = {}
    for m in modes[1:]:
        gaps[m] = (data[w][m]["cycles"] / stock - 1.0) * 100.0
    gain45 = gaps["N4"] - gaps["N5"]
    rows.append((w, gaps))
    print(
        f"{w:18s} {gaps['N4']:9.3f} {gaps['N5']:9.3f} "
        f"{gaps['N6']:9.3f} {gaps['N8']:9.3f} {gain45:10.3f}"
    )

print()
print("=== geomean cycle overhead vs stock ===")
for m in modes[1:]:
    ratios = [data[w][m]["cycles"] / data[w]["stock"]["cycles"] for w in workloads]
    gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
    print(f"{m}: {(gm - 1.0) * 100:+.3f}%")

print()
if prev:
    print("Repeatability:", "EXACT for all six stock/N4 pairs" if all_exact else "NOT exact; inspect before using knee data")
else:
    print("Repeatability: prior summary.csv not found; no exact cross-run comparison performed")
print("All 30 runs verified; simInsts match stock within each workload; issued offsets obey configured bounds.")

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["workload","mode","cycles","simInsts","gap_to_stock_pct","max_offset"])
    for w in workloads:
        stock = data[w]["stock"]["cycles"]
        for m in modes:
            d = data[w][m]
            gap = (d["cycles"] / stock - 1.0) * 100.0
            wr.writerow([w,m,d["cycles"],d["simInsts"],f"{gap:.9f}",d["maxOff"]])
PY

{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "bp_inst_shift=1"
  echo "configs=stock,N4,N5,N6,N8"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
