#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b1_embench_shift_audit}"
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
SHIFTS=(0 1 2)

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

echo "[2/5] Static RVC/branch-PC audit"
OBJDUMP="${RISCV64_OBJDUMP:-riscv64-linux-gnu-objdump}"
command -v "$OBJDUMP" >/dev/null 2>&1 || {
  echo "ERROR: $OBJDUMP not found" >&2
  exit 2
}

{
  echo "workload,insn16_lines,control_pc_bit1_set"
  for w in "${WORKLOADS[@]}"; do
    bin="$EMBENCH_BUILD/src/$w/$w"
    insn16="$("$OBJDUMP" -d "$bin" | awk '
      /^[[:space:]]*[0-9a-f]+:[[:space:]]+[0-9a-f]{4}[[:space:]]/ { n++ }
      END { print n+0 }
    ')"
    ctrl_bit1="$("$OBJDUMP" -d "$bin" | awk '
      /^[[:space:]]*[0-9a-f]+:/ {
        addr=$1
        sub(/:$/, "", addr)
        mnem=$3
        if (mnem ~ /^(b(eq|ne|lt|ge|ltu|geu)|beqz|bnez|c\.beqz|c\.bnez|j|jal|jr|jalr|c\.j|c\.jal|c\.jr|c\.jalr)$/) {
          last=substr(addr, length(addr), 1)
          if (last ~ /^[2367abefABEF]$/) n++
        }
      }
      END { print n+0 }
    ')"
    echo "$w,$insn16,$ctrl_bit1"
  done
} | tee "$OUT_ROOT.static.tmp"
mkdir -p "$OUT_ROOT"
mv "$OUT_ROOT.static.tmp" "$OUT_ROOT/static_rvc_audit.csv"

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

echo "[3/5] Run TournamentBP shift0/1/2 across six fixed Embench workloads (18 ROI runs)"
rm -rf "$OUT_ROOT/runs"
for w in "${WORKLOADS[@]}"; do
  for shift in "${SHIFTS[@]}"; do
    echo "  $w / shift$shift"
    run_one "$w" "$shift"
  done
done

echo "[4/5] Summarize cycle + conditional-prediction behavior"
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
shifts = [0, 1, 2]

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

    required = ["simTicks", "simInsts", "condPredicted", "condIncorrect"]
    missing = [k for k in required if k not in vals]
    if missing:
        raise RuntimeError(f"{path}: missing {missing}")

    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)

    vals["condMPKI"] = vals["condIncorrect"] / vals["simInsts"] * 1000.0
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

print()
print("=== BPU-1 RV64/RVC PC-index shift audit (TournamentBP) ===")
print(
    f"{'workload':18s} {'s0 cyc':>11s} {'s1 cyc':>11s} {'s2 cyc':>11s} "
    f"{'s0/s1%':>9s} {'s2/s1%':>9s} {'MPKI0':>9s} {'MPKI1':>9s} {'MPKI2':>9s}"
)
for w in workloads:
    d0, d1, d2 = data[w][0], data[w][1], data[w][2]
    g0 = (d0["cycles"] / d1["cycles"] - 1.0) * 100.0
    g2 = (d2["cycles"] / d1["cycles"] - 1.0) * 100.0
    print(
        f"{w:18s} {d0['cycles']:11d} {d1['cycles']:11d} {d2['cycles']:11d} "
        f"{g0:9.4f} {g2:9.4f} "
        f"{d0['condMPKI']:9.4f} {d1['condMPKI']:9.4f} {d2['condMPKI']:9.4f}"
    )

print()
print("=== geomean cycle ratio vs shift1 ===")
for s in (0, 2):
    ratios = [data[w][s]["cycles"] / data[w][1]["cycles"] for w in workloads]
    gm = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
    print(f"shift{s}/shift1: {gm:.9f} ({(gm-1.0)*100:+.5f}%)")

print()
print("=== aggregate conditional direction statistics ===")
for s in shifts:
    pred = sum(data[w][s]["condPredicted"] for w in workloads)
    bad = sum(data[w][s]["condIncorrect"] for w in workloads)
    inst = sum(data[w][s]["simInsts"] for w in workloads)
    mpki = bad / inst * 1000.0
    acc = (1.0 - bad / pred) * 100.0 if pred else 100.0
    print(
        f"shift{s}: condPredicted={pred} condIncorrect={bad} "
        f"condMPKI={mpki:.6f} condAccuracy={acc:.6f}%"
    )

# Same binary/ROI semantics must produce the same committed ROI instruction
# count regardless of branch-predictor indexing.
for w in workloads:
    insts = {data[w][s]["simInsts"] for s in shifts}
    if len(insts) != 1:
        raise SystemExit(f"ERROR: simInsts mismatch across shifts for {w}: {insts}")

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","shift","cycles","simTicks","simInsts",
        "condPredicted","condIncorrect","condMPKI","condAccuracy",
        "btbLookups","btbHits","btbHitRate"
    ])
    for w in workloads:
        for s in shifts:
            d = data[w][s]
            wr.writerow([
                w,s,d["cycles"],d["simTicks"],d["simInsts"],
                d["condPredicted"],d["condIncorrect"],
                f"{d['condMPKI']:.9f}",f"{d['condAcc']:.9f}",
                d.get("btbLookups",""),d.get("btbHits",""),
                f"{d['btbHitRate']:.9f}" if math.isfinite(d["btbHitRate"]) else "",
            ])

print()
print("BPU_B1_EMBENCH_SHIFT_AUDIT=PASS")
print("BPU_SHIFT_POLICY_DECISION=DEFER_TO_EVIDENCE_REVIEW")
print(f"CSV: {root / 'summary.csv'}")
PY

echo "[5/5] Emit provenance manifest"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "modeled_clock=1.4GHz"
  echo "rv64_isa=rv64imafd"
  echo "predictor=tournament"
  echo "shifts=0,1,2"
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

echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B1_EMBENCH_SHIFT_PROVENANCE=PASS"
