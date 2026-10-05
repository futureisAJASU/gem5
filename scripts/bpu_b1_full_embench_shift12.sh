#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b1_full_embench_shift12}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
OBJDUMP="${RISCV64_OBJDUMP:-riscv64-linux-gnu-objdump}"

WORKLOADS=(
  aha-mont64
  crc32
  cubic
  edn
  huffbench
  matmult-int
  minver
  nbody
  nettle-aes
  nettle-sha256
  nsichneu
  picojpeg
  qrduino
  sglib-combined
  slre
  st
  statemate
  ud
  wikisort
)
SHIFTS=(1 2)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Ensure exact RV64 Embench binaries exist"
missing=0
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || missing=1
done
if (( missing )); then
  bash scripts/rv64_embench_prepare.sh
fi

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

echo "[2/5] Static branch-PC bit1 audit across full Embench corpus"
{
  echo "workload,insn16_lines,control_total,control_pc_bit1_set,control_pc_bit1_set_pct"
  for w in "${WORKLOADS[@]}"; do
    bin="$EMBENCH_BUILD/src/$w/$w"
    insn16="$("$OBJDUMP" -d "$bin" | awk '
      /^[[:space:]]*[0-9a-f]+:[[:space:]]+[0-9a-f]{4}[[:space:]]/ { n++ }
      END { print n+0 }
    ')"
    read -r ctrl_total ctrl_bit1 < <("$OBJDUMP" -d "$bin" | awk '
      function isctrl(m) {
        return (
          m ~ /^b(eq|ne|lt|ge|ltu|geu)$/ ||
          m ~ /^(beqz|bnez)$/ ||
          m ~ /^c\.(beqz|bnez)$/ ||
          m ~ /^(j|jal|jr|jalr)$/ ||
          m ~ /^c\.(j|jal|jr|jalr)$/ ||
          m == "ret" || m == "call" || m == "tail"
        )
      }
      /^[[:space:]]*[0-9a-f]+:/ {
        addr=$1
        sub(/:$/, "", addr)
        mnem=$3
        if (isctrl(mnem)) {
          total++
          last=tolower(substr(addr, length(addr), 1))
          if (last ~ /^[2367abef]$/) bit1++
        }
      }
      END { print total+0, bit1+0 }
    ')
    pct="$(python3 - "$ctrl_total" "$ctrl_bit1" <<'PY'
import sys
t=int(sys.argv[1]); b=int(sys.argv[2])
print(f"{(100.0*b/t if t else 0.0):.6f}")
PY
)"
    echo "$w,$insn16,$ctrl_total,$ctrl_bit1,$pct"
  done
} | tee "$OUT_ROOT/static_branch_pc_audit.csv"

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
  local shift="$2"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/shift$shift"

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out"     "$CFG"     --binary "$bin"     --bp-type tournament     --bp-inst-shift "$shift"     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $workload/shift$shift failed benchmark verification" >&2
    cat "$out.stdout" >&2
    exit 5
  fi

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
}

echo "[3/5] Run full Embench TournamentBP shift1/shift2 comparison (38 ROI runs)"
for w in "${WORKLOADS[@]}"; do
  for shift in "${SHIFTS[@]}"; do
    echo "  $w / shift$shift"
    run_one "$w" "$shift"
  done
done

echo "[4/5] Summarize and freeze a predictor-sweep workload subset candidate"
python3 - "$OUT_ROOT" <<'PY'
import csv
import math
import pathlib
import statistics
import sys

root = pathlib.Path(sys.argv[1])
workloads = [
    "aha-mont64","crc32","cubic","edn","huffbench","matmult-int",
    "minver","nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg",
    "qrduino","sglib-combined","slre","st","statemate","ud","wikisort",
]
shifts = [1, 2]

def read_stats(path):
    vals = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, val = p[0], p[1]
        try:
            fv = float(val)
        except ValueError:
            continue
        if key == "simTicks":
            vals["simTicks"] = int(fv)
        elif key == "simInsts":
            vals["simInsts"] = int(fv)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            vals.setdefault("cycles", int(fv))
        elif key.endswith(".condPredicted"):
            vals["condPredicted"] = int(fv)
        elif key.endswith(".condIncorrect"):
            vals["condIncorrect"] = int(fv)
        elif key.endswith(".BTBLookups"):
            vals["btbLookups"] = int(fv)
        elif key.endswith(".BTBHits"):
            vals["btbHits"] = int(fv)

    required = ["simTicks","simInsts","condPredicted","condIncorrect"]
    missing = [k for k in required if k not in vals]
    if missing:
        raise RuntimeError(f"{path}: missing {missing}")
    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)

    vals["condMPKI"] = vals["condIncorrect"] / vals["simInsts"] * 1000.0
    vals["condPredPKI"] = vals["condPredicted"] / vals["simInsts"] * 1000.0
    vals["condAcc"] = (
        1.0 - vals["condIncorrect"] / vals["condPredicted"]
        if vals["condPredicted"] else 1.0
    )
    vals["btbHitRate"] = (
        vals.get("btbHits", 0) / vals.get("btbLookups", 1)
        if vals.get("btbLookups", 0) else float("nan")
    )
    return vals

data = {
    w: {s: read_stats(root / w / f"shift{s}" / "roi.stats") for s in shifts}
    for w in workloads
}

for w in workloads:
    if data[w][1]["simInsts"] != data[w][2]["simInsts"]:
        raise SystemExit(f"ERROR: simInsts mismatch across shifts for {w}")

print()
print("=== Full Embench TournamentBP shift1 vs shift2 ===")
print(
    f"{'workload':18s} {'s1 cyc':>11s} {'s2 cyc':>11s} {'s2/s1%':>9s} "
    f"{'MPKI1':>9s} {'MPKI2':>9s} {'cond/kI':>9s}"
)
wins = losses = ties = 0
for w in workloads:
    d1, d2 = data[w][1], data[w][2]
    gap = (d2["cycles"] / d1["cycles"] - 1.0) * 100.0
    if d2["cycles"] < d1["cycles"]:
        wins += 1
    elif d2["cycles"] > d1["cycles"]:
        losses += 1
    else:
        ties += 1
    print(
        f"{w:18s} {d1['cycles']:11d} {d2['cycles']:11d} {gap:9.4f} "
        f"{d1['condMPKI']:9.4f} {d2['condMPKI']:9.4f} "
        f"{d1['condPredPKI']:9.3f}"
    )

ratios = [data[w][2]["cycles"] / data[w][1]["cycles"] for w in workloads]
gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
print()
print(f"shift2/shift1 geomean cycle ratio: {gm:.9f} ({(gm-1.0)*100:+.5f}%)")
print(f"shift2 workload cycle wins/losses/ties: {wins}/{losses}/{ties}")

for s in shifts:
    pred = sum(data[w][s]["condPredicted"] for w in workloads)
    bad = sum(data[w][s]["condIncorrect"] for w in workloads)
    inst = sum(data[w][s]["simInsts"] for w in workloads)
    print(
        f"shift{s}: condPredicted={pred} condIncorrect={bad} "
        f"condMPKI={bad/inst*1000.0:.6f} "
        f"condAccuracy={(1.0-bad/pred)*100.0:.6f}%"
    )

# Predeclared subset rule for subsequent proposed-predictor geometry sweeps:
# rank by baseline (TournamentBP, shift1) conditional MPKI and select
# two lowest, two nearest the median rank, and two highest.
ranked = sorted(workloads, key=lambda w: (data[w][1]["condMPKI"], w))
n = len(ranked)
low = ranked[:2]
high = ranked[-2:]
mid_center = n // 2
mid = ranked[mid_center-1:mid_center+1]
subset = low + mid + high

print()
print("=== fixed future geometry-sweep subset candidate ===")
print("Rule: TournamentBP shift1 conditional-MPKI rank -> 2 low + 2 median + 2 high")
for role, ws in (("low", low), ("mid", mid), ("high", high)):
    for w in ws:
        d = data[w][1]
        print(
            f"{role:4s} {w:18s} condMPKI={d['condMPKI']:.6f} "
            f"condPred/kI={d['condPredPKI']:.6f}"
        )
print("BPU_SWEEP_SUBSET=" + ",".join(subset))

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","shift","cycles","simTicks","simInsts",
        "condPredicted","condIncorrect","condMPKI","condPredPKI",
        "condAccuracy","btbLookups","btbHits","btbHitRate"
    ])
    for w in workloads:
        for s in shifts:
            d = data[w][s]
            wr.writerow([
                w,s,d["cycles"],d["simTicks"],d["simInsts"],
                d["condPredicted"],d["condIncorrect"],
                f"{d['condMPKI']:.9f}",f"{d['condPredPKI']:.9f}",
                f"{d['condAcc']:.9f}",d.get("btbLookups",""),
                d.get("btbHits",""),
                f"{d['btbHitRate']:.9f}" if math.isfinite(d["btbHitRate"]) else "",
            ])

with (root / "sweep_subset.txt").open("w") as f:
    f.write("selection_basis=TournamentBP_shift1_conditional_MPKI\n")
    f.write("selection_rule=2_low+2_median+2_high\n")
    f.write("workloads=" + ",".join(subset) + "\n")

print()
print("BPU_B1_FULL_EMBENCH_SHIFT12=PASS")
print("BPU_SWEEP_SUBSET_SELECTION=PASS")
PY

echo "[5/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "predictor=tournament"
  echo "shifts=1,2"
  echo "btb_entries=4096"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
  "${RISCV64_CC:-riscv64-linux-gnu-gcc}" --version | head -n 1 | sed 's/^/compiler=/'
  for w in "${WORKLOADS[@]}"; do
    bin="$EMBENCH_BUILD/src/$w/$w"
    echo "$w=$(sha256sum "$bin" | awk '{print $1}')"
  done
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Subset: $OUT_ROOT/sweep_subset.txt"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B1_FULL_EMBENCH_PROVENANCE=PASS"
