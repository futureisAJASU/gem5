#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-a64_embench_p21313_replay}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-a64-gem5}"
GEM5="$ROOT/build/ARM/gem5.opt"
CFG="$ROOT/configs/01_little_v052_proxy.py"
AARCH64_CC="${AARCH64_CC:-aarch64-linux-gnu-gcc}"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

# R2 control matrix:
#   central_s0  : historical predictor-index control, stock/N4
#   central_s2  : current AArch64 predictor control, stock/N4
#   p21313_s2   : intended distributed scheduler, stock/N4/N5
PROFILES=(central_s0 central_s2 p21313_s2)

P21313_COMMON=(
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
)

echo "[0/4] Build current gem5/ARM"
scons build/ARM/gem5.opt -j"$JOBS"

echo "[1/4] Rebuild exact Embench revision for AArch64"
AARCH64_CC="$AARCH64_CC" \
EMBENCH_DIR="$EMBENCH_DIR" \
EMBENCH_BUILD="$EMBENCH_BUILD" \
bash scripts/a64_embench_prepare.sh

if [[ "$(git -C "$EMBENCH_DIR" rev-parse HEAD)" != "0466a18e4f6b47e19598d7c6ba72916d54b68f65" ]]; then
  echo "ERROR: Embench source revision changed after preparation" >&2
  exit 3
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
  local profile="$2"
  local mode="$3"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/$workload/$profile/$mode"
  local args=()
  local narg=()

  case "$profile" in
    central_s0)
      args=(--bp-inst-shift 0)
      ;;
    central_s2)
      args=(--bp-inst-shift 2)
      ;;
    p21313_s2)
      args=(--bp-inst-shift 2 "${P21313_COMMON[@]}")
      ;;
    *)
      echo "ERROR: unknown profile $profile" >&2
      exit 2
      ;;
  esac

  case "$mode" in
    stock) ;;
    N4) narg=(--n-skip 4) ;;
    N5) narg=(--n-skip 5) ;;
    *)
      echo "ERROR: unknown mode $mode" >&2
      exit 2
      ;;
  esac

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" \
    "$CFG" \
    --binary "$bin" \
    "${args[@]}" \
    "${narg[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $workload/$profile/$mode failed benchmark verification" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 5
  fi

  extract_first_roi "$out/stats.txt" "$out/roi.stats"

  if [[ "$profile" == "p21313_s2" && "$mode" != "stock" ]]; then
    if ! grep -q 'nSkipLocalHiddenReadySamples' "$out/roi.stats"; then
      echo "ERROR: local N-SKIP visibility stats missing for $workload/$profile/$mode" >&2
      exit 6
    fi
  fi
}

echo "[2/4] Run 42-point AArch64 control/replay matrix"
for w in "${WORKLOADS[@]}"; do
  echo "  $w / central_s0 / stock"
  run_one "$w" central_s0 stock
  echo "  $w / central_s0 / N4"
  run_one "$w" central_s0 N4

  echo "  $w / central_s2 / stock"
  run_one "$w" central_s2 stock
  echo "  $w / central_s2 / N4"
  run_one "$w" central_s2 N4

  echo "  $w / p21313_s2 / stock"
  run_one "$w" p21313_s2 stock
  echo "  $w / p21313_s2 / N4"
  run_one "$w" p21313_s2 N4
  echo "  $w / p21313_s2 / N5"
  run_one "$w" p21313_s2 N5
done

echo "[3/4] Validate, compare controls, and summarize"
python3 - "$OUT_ROOT" <<'PY'
import csv
import hashlib
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
profiles = {
    "central_s0": ["stock", "N4"],
    "central_s2": ["stock", "N4"],
    "p21313_s2": ["stock", "N4", "N5"],
}
bounds = {"N4": 4, "N5": 5}

historical_n4_pct = {
    "matmult-int": 0.000,
    "nettle-sha256": -0.001,
    "nettle-aes": 3.355,
    "sglib-combined": 0.786,
    "wikisort": 0.601,
    "picojpeg": 8.033,
}
historical_hashes = {
    "matmult-int": "36320e01eaf9d3e25cd38f7df0c9c76f545e220c5f6b3b6c8b936e92a727121b",
    "nettle-sha256": "51088858a0a0295686b60f35a9e84b681ca12ec164bba26a49748fa7de349522",
    "nettle-aes": "4068e98af7e7bd8c0af288b0b2d2749d1bac593e594ed6cb9853a5434abf9f59",
    "sglib-combined": "cb2af7a528b057427570f9a42bb18077a9dd89deced2597f8126f7b613531d6b",
    "wikisort": "0276133fe4dd6e23b9a2be118e713ba9677fefbca341ca63916c1a7832285fe2",
    "picojpeg": "4e73fa6bee08d2c327fe2554ae1d0ed104830643593bd8c34de84ca5cc89b28d",
}

def read_stats(path):
    vals = {}
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        key, raw = p[0], p[1]
        try:
            val = float(raw)
        except ValueError:
            continue

        if key == "simTicks":
            vals["simTicks"] = int(val)
        elif key == "simInsts":
            vals["simInsts"] = int(val)
        elif key.endswith(".numCycles") and "cores0.core" in key:
            vals.setdefault("cycles", int(val))
        elif key.endswith(".nSkipLocalHiddenReadySamples"):
            vals["hidden"] = vals.get("hidden", 0) + int(val)
        elif key.endswith(".nSkipLocalNoVisibleReadyCycles"):
            vals["noVis"] = vals.get("noVis", 0) + int(val)
        elif ".nSkipIssuedOffset::" in key:
            name = key.rsplit("::", 1)[-1]
            if name.isdigit() and val > 0:
                vals["maxOff"] = max(vals.get("maxOff", 0), int(name))

    if "simTicks" not in vals or "simInsts" not in vals:
        raise RuntimeError(f"missing required ROI stats in {path}")
    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)
    vals.setdefault("hidden", 0)
    vals.setdefault("noVis", 0)
    vals.setdefault("maxOff", 0)
    return vals

data = {}
for w in workloads:
    data[w] = {}
    for p, modes in profiles.items():
        data[w][p] = {}
        for m in modes:
            data[w][p][m] = read_stats(root / w / p / m / "roi.stats")

# Correctness/provenance invariants.
for w in workloads:
    all_points = [
        data[w][p][m]
        for p, modes in profiles.items()
        for m in modes
    ]
    committed = {d["simInsts"] for d in all_points}
    if len(committed) != 1:
        raise SystemExit(f"ERROR: cross-profile simInsts mismatch for {w}: {sorted(committed)}")

    for p, modes in profiles.items():
        for m in modes:
            if m in bounds and data[w][p][m]["maxOff"] > bounds[m]:
                raise SystemExit(
                    f"ERROR: {w}/{p}/{m} maxOff={data[w][p][m]['maxOff']} > {bounds[m]}"
                )

def gap(w, profile, mode):
    stock = data[w][profile]["stock"]["cycles"]
    return (data[w][profile][mode]["cycles"] / stock - 1.0) * 100.0

def ratio_gm(profile, mode):
    ratios = [
        data[w][profile][mode]["cycles"] / data[w][profile]["stock"]["cycles"]
        for w in workloads
    ]
    return math.exp(sum(math.log(x) for x in ratios) / len(ratios))

def arithmetic_gap(profile, mode):
    return sum(gap(w, profile, mode) for w in workloads) / len(workloads)

print()
print("=== AArch64 R2: predictor + topology controlled P21313 replay ===")
print(
    f"{'workload':18s} {'histN4%':>9s} {'C0_N4%':>9s} {'C2_N4%':>9s} "
    f"{'P2_N4%':>9s} {'P2_N5%':>9s} {'C2-P2':>9s} {'N4->N5':>9s} "
    f"{'P2stock/C2':>11s} {'P2N4/C2':>10s}"
)

rows = []
for w in workloads:
    c0n4 = gap(w, "central_s0", "N4")
    c2n4 = gap(w, "central_s2", "N4")
    p2n4 = gap(w, "p21313_s2", "N4")
    p2n5 = gap(w, "p21313_s2", "N5")
    topo_reduction = c2n4 - p2n4
    n45 = p2n4 - p2n5

    c2_stock = data[w]["central_s2"]["stock"]["cycles"]
    p2_stock = data[w]["p21313_s2"]["stock"]["cycles"]
    p2_n4_cycles = data[w]["p21313_s2"]["N4"]["cycles"]
    p2_stock_vs_c2 = (p2_stock / c2_stock - 1.0) * 100.0
    p2_n4_vs_c2 = (p2_n4_cycles / c2_stock - 1.0) * 100.0

    print(
        f"{w:18s} {historical_n4_pct[w]:9.3f} {c0n4:9.3f} {c2n4:9.3f} "
        f"{p2n4:9.3f} {p2n5:9.3f} {topo_reduction:9.3f} {n45:9.3f} "
        f"{p2_stock_vs_c2:11.3f} {p2_n4_vs_c2:10.3f}"
    )
    rows.append((w, c0n4, c2n4, p2n4, p2n5))

print()
print("=== Aggregate normalized overhead vs each profile's full-visibility stock ===")
for profile, mode in [
    ("central_s0", "N4"),
    ("central_s2", "N4"),
    ("p21313_s2", "N4"),
    ("p21313_s2", "N5"),
]:
    gm = ratio_gm(profile, mode)
    am = arithmetic_gap(profile, mode)
    print(
        f"{profile:13s} {mode:5s}: "
        f"geomean={(gm - 1.0) * 100:+.3f}%  arithmetic_mean={am:+.3f}%"
    )

# Aggregate absolute comparison to current central shift2 full visibility.
p2_stock_ratios = [
    data[w]["p21313_s2"]["stock"]["cycles"] /
    data[w]["central_s2"]["stock"]["cycles"]
    for w in workloads
]
p2_n4_ratios = [
    data[w]["p21313_s2"]["N4"]["cycles"] /
    data[w]["central_s2"]["stock"]["cycles"]
    for w in workloads
]
p2_stock_gm = math.exp(sum(math.log(x) for x in p2_stock_ratios) / len(p2_stock_ratios))
p2_n4_gm = math.exp(sum(math.log(x) for x in p2_n4_ratios) / len(p2_n4_ratios))

print()
print("=== Absolute topology comparison vs central_s2 full visibility ===")
print(f"P21313 shift2 stock geomean delta: {(p2_stock_gm - 1.0) * 100:+.3f}%")
print(f"P21313 shift2 N4    geomean delta: {(p2_n4_gm - 1.0) * 100:+.3f}%")

# Worst local N4 residual.
worst = max(workloads, key=lambda w: gap(w, "p21313_s2", "N4"))
print()
print(
    f"Worst P21313 shift2 N4 residual: {worst} "
    f"{gap(worst, 'p21313_s2', 'N4'):+.3f}%"
)
print(
    "All 42 ROI runs verified; committed simInsts match across every profile/mode "
    "within each workload; N-SKIP issued offsets obey configured bounds."
)

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","profile","mode","cycles","simInsts",
        "gap_to_profile_stock_pct","max_offset",
        "hidden_ready_samples","no_visible_ready_cycles",
    ])
    for w in workloads:
        for p, modes in profiles.items():
            stock = data[w][p]["stock"]["cycles"]
            for m in modes:
                d = data[w][p][m]
                gp = (d["cycles"] / stock - 1.0) * 100.0
                wr.writerow([
                    w,p,m,d["cycles"],d["simInsts"],f"{gp:.9f}",
                    d["maxOff"],d["hidden"],d["noVis"],
                ])

with (root / "comparison.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","historical_central_n4_pct",
        "current_central_shift0_n4_pct",
        "current_central_shift2_n4_pct",
        "p21313_shift2_n4_pct","p21313_shift2_n5_pct",
        "central_shift2_minus_p21313_n4_pp",
        "p21313_n4_minus_n5_pp",
        "p21313_shift2_stock_vs_central_shift2_stock_pct",
        "p21313_shift2_n4_vs_central_shift2_stock_pct",
    ])
    for w in workloads:
        c0n4 = gap(w, "central_s0", "N4")
        c2n4 = gap(w, "central_s2", "N4")
        p2n4 = gap(w, "p21313_s2", "N4")
        p2n5 = gap(w, "p21313_s2", "N5")
        c2stock = data[w]["central_s2"]["stock"]["cycles"]
        p2stock = data[w]["p21313_s2"]["stock"]["cycles"]
        p2n4cy = data[w]["p21313_s2"]["N4"]["cycles"]
        wr.writerow([
            w,f"{historical_n4_pct[w]:.9f}",
            f"{c0n4:.9f}",f"{c2n4:.9f}",
            f"{p2n4:.9f}",f"{p2n5:.9f}",
            f"{(c2n4-p2n4):.9f}",f"{(p2n4-p2n5):.9f}",
            f"{((p2stock/c2stock)-1)*100:.9f}",
            f"{((p2n4cy/c2stock)-1)*100:.9f}",
        ])
PY

echo "[4/4] Write hashes and reproducibility manifest"
for w in "${WORKLOADS[@]}"; do
  sha256sum "$EMBENCH_BUILD/src/$w/$w"
done >"$OUT_ROOT/binary_sha256.txt"

{
  echo "gem5_branch=$(git branch --show-current)"
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "config=$CFG"
  echo "config_sha256=$(sha256sum "$CFG" | awk '{print $1}')"
  echo "runner_sha256=$(sha256sum scripts/a64_embench_p21313_replay.sh | awk '{print $1}')"
  echo "prepare_sha256=$(sha256sum scripts/a64_embench_prepare.sh | awk '{print $1}')"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "compiler=$("$AARCH64_CC" --version | head -n 1)"
  echo "isa_flags=-march=armv8-a"
  echo "link=static GNU/Linux"
  echo "modeled_clock=1.4GHz"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
  echo "matrix=central_s0(stock,N4);central_s2(stock,N4);p21313_s2(stock,N4,N5)"
  echo "scheduler_p21313=INT0:10/2,INT1:6/1,MEM:12/3,DIV:4/1,FP_SIMD:6/3"
  echo "int_steering=first-fit"
  echo "local_iq_picker=enabled for p21313_s2"
  echo "historical_a64_central_source_head=547a4323adefdff81e490caa5a5e00dc4cd7126d"
  echo "historical_a64_config_sha256=db7d16fe6c6ddcb70c78b8dd9080a85968173f2d06021580106468a4b8f4b570"
  echo "historical_note=historical config predates explicit bp-inst-shift control; current config documents shift0 as historical/generic behavior"
} >"$OUT_ROOT/manifest.txt"

cat >"$OUT_ROOT/historical_binary_hash_reference.txt" <<'EOF'
matmult-int=36320e01eaf9d3e25cd38f7df0c9c76f545e220c5f6b3b6c8b936e92a727121b
nettle-sha256=51088858a0a0295686b60f35a9e84b681ca12ec164bba26a49748fa7de349522
nettle-aes=4068e98af7e7bd8c0af288b0b2d2749d1bac593e594ed6cb9853a5434abf9f59
sglib-combined=cb2af7a528b057427570f9a42bb18077a9dd89deced2597f8126f7b613531d6b
wikisort=0276133fe4dd6e23b9a2be118e713ba9677fefbca341ca63916c1a7832285fe2
picojpeg=4e73fa6bee08d2c327fe2554ae1d0ed104830643593bd8c34de84ca5cc89b28d
EOF

echo
echo "CSV: $OUT_ROOT/summary.csv"
echo "Comparison: $OUT_ROOT/comparison.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "Binary hashes: $OUT_ROOT/binary_sha256.txt"
echo "Historical hash reference: $OUT_ROOT/historical_binary_hash_reference.txt"
