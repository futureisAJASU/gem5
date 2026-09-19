#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_p21313_writecap_control}"
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

PROFILES=(P21313 C33313)
MODES=(stock N4)

COMMON=(
  --distributed-iq
  --local-iq-picker
  --int-steering first-fit
  --dist-int0 10
  --dist-int1 6
  --dist-mem 12
  --dist-div 4
  --dist-fpsimd 6
  --bp-inst-shift 1
)

P21313_CAPS=(
  --dist-int0-write-cap 2
  --dist-int1-write-cap 1
  --dist-mem-write-cap 3
  --dist-div-write-cap 1
  --dist-fpsimd-write-cap 3
)

# With per-core dispatch width = 3, explicit 3/3/3/1/3 removes the
# INT0/INT1 ingress restriction while retaining the architecturally
# one-wide DIV domain. This is the historical "33313" control.
C33313_CAPS=(
  --dist-int0-write-cap 3
  --dist-int1-write-cap 3
  --dist-mem-write-cap 3
  --dist-div-write-cap 1
  --dist-fpsimd-write-cap 3
)

echo "[0/4] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/4] Rebuild exact RV64 Embench provenance"
EMBENCH_DIR="$EMBENCH_DIR" \
EMBENCH_BUILD="$EMBENCH_BUILD" \
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

run_embench() {
  local workload="$1"
  local profile="$2"
  local mode="$3"
  local bin="$EMBENCH_BUILD/src/$workload/$workload"
  local out="$OUT_ROOT/embench/$workload/$profile/$mode"
  local caps=()
  local narg=()

  case "$profile" in
    P21313) caps=("${P21313_CAPS[@]}") ;;
    C33313) caps=("${C33313_CAPS[@]}") ;;
    *) echo "ERROR: unknown profile $profile" >&2; exit 2 ;;
  esac

  case "$mode" in
    stock) ;;
    N4) narg=(--n-skip 4) ;;
    *) echo "ERROR: unknown mode $mode" >&2; exit 2 ;;
  esac

  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" \
    "$CFG" \
    --binary "$bin" \
    "${COMMON[@]}" \
    "${caps[@]}" \
    "${narg[@]}" \
    >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: $workload/$profile/$mode failed benchmark verification" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 5
  fi

  extract_first_roi "$out/stats.txt" "$out/roi.stats"

  if [[ "$mode" == "N4" ]] && ! grep -q 'nSkipLocalHiddenReadySamples' "$out/roi.stats"; then
    echo "ERROR: N-SKIP local visibility stats missing for $workload/$profile/$mode" >&2
    exit 6
  fi
}

echo "[2/4] Run 24-point write-cap control matrix"
for w in "${WORKLOADS[@]}"; do
  for p in "${PROFILES[@]}"; do
    for m in "${MODES[@]}"; do
      echo "  $w / $p / $m"
      run_embench "$w" "$p" "$m"
    done
  done
done

echo "[3/4] Validate and summarize"
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
profiles = ["P21313", "C33313"]
modes = ["stock", "N4"]
iq_names = ["INT0", "INT1", "MEM", "DIV", "FP_SIMD"]

def read_stats(path):
    vals = {
        "hidden": 0,
        "noVis": 0,
        "maxOff": 0,
        "writes1": [0] * 5,
        "writes2": [0] * 5,
        "writes3p": [0] * 5,
        "dispatches": [0] * 5,
    }
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
            vals["hidden"] += int(val)
        elif key.endswith(".nSkipLocalNoVisibleReadyCycles"):
            vals["noVis"] += int(val)
        elif ".nSkipIssuedOffset::" in key:
            name = key.rsplit("::", 1)[-1]
            if name.isdigit() and val > 0:
                vals["maxOff"] = max(vals["maxOff"], int(name))
        else:
            for idx in range(5):
                suffix = f"::IQ{idx}"
                if key.endswith(".dispatchWrite1Cycles" + suffix):
                    vals["writes1"][idx] += int(val)
                elif key.endswith(".dispatchWrite2Cycles" + suffix):
                    vals["writes2"][idx] += int(val)
                elif key.endswith(".dispatchWrite3PlusCycles" + suffix):
                    vals["writes3p"][idx] += int(val)
                elif key.endswith(".steerDispatches" + suffix):
                    vals["dispatches"][idx] += int(val)

    if "simTicks" not in vals or "simInsts" not in vals:
        raise RuntimeError(f"missing required stats in {path}")
    if "cycles" not in vals:
        vals["cycles"] = round(vals["simTicks"] * 1.4e9 / 1.0e12)
    return vals

data = {
    w: {
        p: {
            m: read_stats(root / "embench" / w / p / m / "roi.stats")
            for m in modes
        }
        for p in profiles
    }
    for w in workloads
}

# Correctness and N4 bound.
for w in workloads:
    insts = {
        data[w][p][m]["simInsts"]
        for p in profiles
        for m in modes
    }
    if len(insts) != 1:
        raise SystemExit(f"ERROR: simInsts mismatch for {w}: {sorted(insts)}")
    for p in profiles:
        if data[w][p]["N4"]["maxOff"] > 4:
            raise SystemExit(
                f"ERROR: {w}/{p}/N4 maxOff={data[w][p]['N4']['maxOff']} > 4"
            )

def gap_within(w, p):
    return (data[w][p]["N4"]["cycles"] / data[w][p]["stock"]["cycles"] - 1.0) * 100.0

def cap_delta(w, mode):
    return (
        data[w]["P21313"][mode]["cycles"] /
        data[w]["C33313"][mode]["cycles"] - 1.0
    ) * 100.0

def gm_ratio(numer_profile, denom_profile, mode):
    ratios = [
        data[w][numer_profile][mode]["cycles"] /
        data[w][denom_profile][mode]["cycles"]
        for w in workloads
    ]
    return math.exp(sum(math.log(x) for x in ratios) / len(ratios))

def gm_n4(profile):
    ratios = [
        data[w][profile]["N4"]["cycles"] /
        data[w][profile]["stock"]["cycles"]
        for w in workloads
    ]
    return math.exp(sum(math.log(x) for x in ratios) / len(ratios))

print()
print("=== RV64 R3: P21313 vs explicit 33313 write-cap control ===")
print(
    f"{'workload':18s} {'Pstock':>10s} {'Cstock':>10s} {'capS%':>8s} "
    f"{'PN4%':>8s} {'CN4%':>8s} {'capN4%':>8s} "
    f"{'P_INT0_2w':>10s} {'C_INT0_3+w':>11s} "
    f"{'P_INT1_1w':>10s} {'C_INT1_2+w':>11s}"
)

rows = []
for w in workloads:
    ps = data[w]["P21313"]["stock"]
    cs = data[w]["C33313"]["stock"]
    pn = data[w]["P21313"]["N4"]
    cn = data[w]["C33313"]["N4"]

    cap_s = cap_delta(w, "stock")
    p_n4 = gap_within(w, "P21313")
    c_n4 = gap_within(w, "C33313")
    cap_n4 = cap_delta(w, "N4")

    # Pressure observables:
    # P21313 INT0 cap=2 => exactly-two-write cycles sit at the cap.
    # C33313 INT0 cap=3 => 3+-write cycles show demand beyond P21313's cap.
    # P21313 INT1 cap=1 => every one-write cycle sits at the cap.
    # C33313 INT1 2+/3+ cycles show demand beyond P21313's cap.
    p_int0_2w = pn["writes2"][0]
    c_int0_3p = cn["writes3p"][0]
    p_int1_1w = pn["writes1"][1]
    c_int1_2p = cn["writes2"][1] + cn["writes3p"][1]

    print(
        f"{w:18s} {ps['cycles']:10d} {cs['cycles']:10d} {cap_s:8.3f} "
        f"{p_n4:8.3f} {c_n4:8.3f} {cap_n4:8.3f} "
        f"{p_int0_2w:10d} {c_int0_3p:11d} "
        f"{p_int1_1w:10d} {c_int1_2p:11d}"
    )
    rows.append((w, cap_s, p_n4, c_n4, cap_n4))

gm_cap_stock = gm_ratio("P21313", "C33313", "stock")
gm_cap_n4 = gm_ratio("P21313", "C33313", "N4")
gm_p_n4 = gm_n4("P21313")
gm_c_n4 = gm_n4("C33313")

print()
print("=== Aggregate ===")
print(f"P21313 vs 33313 full-visibility geomean penalty: {(gm_cap_stock - 1.0) * 100:+.3f}%")
print(f"P21313 vs 33313 N4 geomean penalty:              {(gm_cap_n4 - 1.0) * 100:+.3f}%")
print(f"P21313 N4 residual vs P21313 stock:              {(gm_p_n4 - 1.0) * 100:+.3f}%")
print(f"33313   N4 residual vs 33313 stock:              {(gm_c_n4 - 1.0) * 100:+.3f}%")

worst_stock = max(workloads, key=lambda w: cap_delta(w, "stock"))
worst_n4 = max(workloads, key=lambda w: cap_delta(w, "N4"))
print(
    f"Worst cap penalty, stock: {worst_stock} "
    f"{cap_delta(worst_stock, 'stock'):+.3f}%"
)
print(
    f"Worst cap penalty, N4:    {worst_n4} "
    f"{cap_delta(worst_n4, 'N4'):+.3f}%"
)

with (root / "summary.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload","profile","mode","cycles","simInsts",
        "gap_to_profile_stock_pct","max_offset",
        "hidden_ready_samples","no_visible_ready_cycles",
        "INT0_write1_cycles","INT0_write2_cycles","INT0_write3plus_cycles",
        "INT1_write1_cycles","INT1_write2_cycles","INT1_write3plus_cycles",
        "INT0_dispatches","INT1_dispatches",
    ])
    for w in workloads:
        for p in profiles:
            stock = data[w][p]["stock"]["cycles"]
            for m in modes:
                d = data[w][p][m]
                gp = (d["cycles"] / stock - 1.0) * 100.0
                wr.writerow([
                    w,p,m,d["cycles"],d["simInsts"],f"{gp:.9f}",
                    d["maxOff"],d["hidden"],d["noVis"],
                    d["writes1"][0],d["writes2"][0],d["writes3p"][0],
                    d["writes1"][1],d["writes2"][1],d["writes3p"][1],
                    d["dispatches"][0],d["dispatches"][1],
                ])

with (root / "comparison.csv").open("w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow([
        "workload",
        "p21313_vs_33313_stock_pct",
        "p21313_n4_residual_pct",
        "33313_n4_residual_pct",
        "p21313_vs_33313_n4_pct",
    ])
    for w in workloads:
        wr.writerow([
            w,
            f"{cap_delta(w, 'stock'):.9f}",
            f"{gap_within(w, 'P21313'):.9f}",
            f"{gap_within(w, 'C33313'):.9f}",
            f"{cap_delta(w, 'N4'):.9f}",
        ])

print()
print("All 24 Embench ROI runs verified; simInsts match across both cap profiles and both visibility modes; N4 issued offsets obey <=4.")
PY

echo "[4/4] Write provenance"
for w in "${WORKLOADS[@]}"; do
  sha256sum "$EMBENCH_BUILD/src/$w/$w"
done >"$OUT_ROOT/binary_sha256.txt"

{
  echo "gem5_branch=$(git branch --show-current)"
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_binary_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "config=$CFG"
  echo "config_sha256=$(sha256sum "$CFG" | awk '{print $1}')"
  echo "runner_sha256=$(sha256sum scripts/rv64_p21313_writecap_control.sh | awk '{print $1}')"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "compiler=$(riscv64-linux-gnu-gcc --version | head -n 1)"
  echo "isa_flags=-march=rv64imafd -mabi=lp64d"
  echo "link=static GNU/Linux"
  echo "modeled_clock=1.4GHz"
  echo "bp_inst_shift=1"
  echo "roi_start=m5_reset_stats(0,0)"
  echo "roi_stop=m5_dump_stats(0,0)"
  echo "roi_stats_section=first"
  echo "scheduler=distributed local picker, first-fit"
  echo "queues=INT0:10,INT1:6,MEM:12,DIV:4,FP_SIMD:6"
  echo "P21313_caps=2,1,3,1,3"
  echo "C33313_caps=3,3,3,1,3"
  echo "control_note=per-core dispatch width is 3; explicit 33313 removes INT0/INT1 ingress restriction while retaining one-wide DIV"
  echo "modes=stock,N4"
} >"$OUT_ROOT/manifest.txt"

echo
echo "CSV: $OUT_ROOT/summary.csv"
echo "Comparison: $OUT_ROOT/comparison.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "Binary hashes: $OUT_ROOT/binary_sha256.txt"
