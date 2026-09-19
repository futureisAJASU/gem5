#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_embench_screen}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
HIST="$ROOT/benchmarks/results/nskip_embench_realistic_full.csv"
WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

echo "[0/3] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/3] Prepare exact Embench RV64 binaries"
bash scripts/rv64_embench_prepare.sh

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

echo "[2/3] Run centralized stock vs N4 screen (12 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  echo "  $w / stock"
  run_one "$w" stock
  echo "  $w / N4"
  run_one "$w" N4
done

echo "[3/3] Summarize first-ROI results"
python3 - "$OUT_ROOT" "$HIST" <<'PY'
import csv
import math
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
hist_path = pathlib.Path(sys.argv[2])
workloads = [
    "matmult-int",
    "nettle-sha256",
    "nettle-aes",
    "sglib-combined",
    "wikisort",
    "picojpeg",
]

def read_stats(path):
    vals = {}
    lines = path.read_text().splitlines()
    for line in lines:
        p = line.split()
        if len(p) < 2:
            continue
        key = p[0]
        val = p[1]
        if key == "simTicks":
            vals["simTicks"] = int(val)
        elif key == "simInsts":
            vals["simInsts"] = int(val)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            try:
                vals.setdefault("cycles", int(float(val)))
            except ValueError:
                pass
        elif key.endswith(".nSkipHeadIssued"):
            vals["head"] = vals.get("head", 0) + int(float(val))
        elif key.endswith(".nSkipBypassIssued"):
            vals["bypass"] = vals.get("bypass", 0) + int(float(val))
        elif ".nSkipIssuedOffset::" in key:
            name = key.rsplit("::", 1)[-1]
            if name.isdigit() and float(val) > 0:
                vals["maxOff"] = max(vals.get("maxOff", 0), int(name))
    if "simTicks" not in vals or "simInsts" not in vals:
        raise RuntimeError(f"missing core ROI stats in {path}")
    if "cycles" not in vals:
        # Exact modeled conversion: 1.4 GHz at 1e12 ticks/s.
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)
    vals.setdefault("head", 0)
    vals.setdefault("bypass", 0)
    vals.setdefault("maxOff", 0)
    return vals

a64 = {}
if hist_path.exists():
    with hist_path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["workload"] in workloads and row["config"].lower() == "n4":
                a64[row["workload"]] = float(row["gapToStockPct"])

rows = []
print()
print("=== RV64 Embench centralized stock vs N4 screen ===")
print(f"{'workload':18s} {'stock_cy':>11s} {'N4_cy':>11s} {'RV64_N4%':>10s} {'A64_N4%':>10s} {'delta_pp':>10s} {'inst_match':>10s} {'maxOff':>7s}")
for w in workloads:
    stock = read_stats(root / w / "stock" / "roi.stats")
    n4 = read_stats(root / w / "N4" / "roi.stats")
    gap = (n4["cycles"] / stock["cycles"] - 1.0) * 100.0
    old = a64.get(w, float("nan"))
    delta = gap - old if math.isfinite(old) else float("nan")
    match = stock["simInsts"] == n4["simInsts"]
    print(
        f"{w:18s} {stock['cycles']:11d} {n4['cycles']:11d} "
        f"{gap:10.3f} {old:10.3f} {delta:10.3f} {str(match):>10s} {n4['maxOff']:7d}"
    )
    rows.append((w, stock, n4, gap, old, delta, match))

ratios = [1.0 + r[3] / 100.0 for r in rows]
gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
a64_ratios = [1.0 + r[4] / 100.0 for r in rows if math.isfinite(r[4])]
a64_gm = math.exp(sum(math.log(x) for x in a64_ratios) / len(a64_ratios)) if a64_ratios else float("nan")
print()
print(f"RV64 N4 geomean cycle ratio vs stock: {gm:.9f} ({(gm-1)*100:+.3f}%)")
if math.isfinite(a64_gm):
    print(f"A64 historical N4 geomean ratio:       {a64_gm:.9f} ({(a64_gm-1)*100:+.3f}%)")

bad = [r[0] for r in rows if not r[6]]
if bad:
    raise SystemExit("ERROR: simInsts mismatch stock vs N4: " + ", ".join(bad))
if any(r[2]["maxOff"] > 4 for r in rows):
    raise SystemExit("ERROR: N4 issued beyond Head+4")

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","stock_cycles","n4_cycles","rv64_n4_gap_pct",
        "a64_historical_n4_gap_pct","delta_pp","simInsts_match",
        "n4_head","n4_bypass","n4_max_offset"
    ])
    for w, stock, n4, gap, old, delta, match in rows:
        wr.writerow([
            w, stock["cycles"], n4["cycles"], f"{gap:.9f}",
            f"{old:.9f}" if math.isfinite(old) else "",
            f"{delta:.9f}" if math.isfinite(delta) else "",
            int(match), n4["head"], n4["bypass"], n4["maxOff"]
        ])

print()
print("All 12 ROI runs verified; stock/N4 simInsts match for all six workloads; N4 max offset <= 4.")
print(f"CSV: {root / 'summary.csv'}")
PY

{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "bp_inst_shift=1"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
  echo "warmup_heat=1"
  "${RISCV64_CC:-riscv64-linux-gnu-gcc}" --version | head -n 1 | sed 's/^/compiler=/'
  for w in "${WORKLOADS[@]}"; do
    bin="$EMBENCH_BUILD/src/$w/$w"
    echo "$w=$(sha256sum "$bin" | awk '{print $1}')"
  done
} >"$OUT_ROOT/manifest.txt"

echo "Manifest: $OUT_ROOT/manifest.txt"
