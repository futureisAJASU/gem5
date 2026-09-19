#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-rv64_cache_l2_final_sanity}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"
CC="${RISCV64_CC:-riscv64-linux-gnu-gcc}"
SRC="$ROOT/benchmarks/src/rv64_l2_12stream_ws.c"

BIN128="$ROOT/benchmarks/bin/rv64_l2_ws128"
BIN1024="$ROOT/benchmarks/bin/rv64_l2_ws1024"
BIN2048="$ROOT/benchmarks/bin/rv64_l2_ws2048"

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Build three RV64 working-set binaries"
mkdir -p benchmarks/bin
for spec in "128:$BIN128" "1024:$BIN1024" "2048:$BIN2048"; do
  ws="${spec%%:*}"
  out="${spec#*:}"
  "$CC" \
    -O2 -static -fno-tree-vectorize \
    -march=rv64imafd -mabi=lp64d \
    -DWS_LINES="$ws" \
    -Wall -Wextra \
    -o "$out" "$SRC"
  file "$out"
done

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

COMMON=(
  --cores 4
  --clock 1.4GHz
  --width 3
  --fetch-width 3
  --decode-width 3
  --commit-width 3
  --rob 80
  --iq 40
  --lq 12
  --sq 16

  --l1i-size-kib 32
  --l1d-size-kib 64
  --l1d-mshrs 20
  --l1d-demand-mshr-reserve 0
  --cache-load-ports 2
  --cache-store-ports 1
  --l1d-tag-latency 2
  --l1d-data-latency 2

  --cache-prefetch l1d
  --prefetch-degree 4
  --prefetch-pf-hit on
  --prefetch-rate-limit on
  --prefetch-rate-bucket 4096
  --prefetch-rate-refill-cycles 24

  --l2-mshrs 32
  --l2-demand-mshr-reserve 0
  --l2-xbar-header-latency 1
  --membus-width 64
  --l2-tag-latency 8
  --l2-data-latency 8
  --l2-data-banks 0

  --bp-inst-shift 1
)

pattern_bins() {
  local pattern="$1"
  case "$pattern" in
    pair_asym)
      printf '%s\n' "$BIN2048" "$BIN128" "$BIN2048" "$BIN128"
      ;;
    high_full)
      printf '%s\n' "$BIN2048" "$BIN2048" "$BIN2048" "$BIN2048"
      ;;
    *)
      echo "ERROR: unknown pattern $pattern" >&2
      return 2
      ;;
  esac
}

run_one() {
  local pattern="$1"
  local profile="$2"
  local suffix="${3:-main}"
  local topology size assoc xbar
  local -a bins=()
  local -a core_args=()

  case "$profile" in
    private4_2p0)
      topology=private4; size=4096; assoc=8; xbar=16 ;;
    pair2_2p0)
      topology=pair2; size=4096; assoc=8; xbar=32 ;;
    shared4_2p0)
      topology=shared4; size=4096; assoc=8; xbar=64 ;;
    pair2_1p75)
      topology=pair2; size=3584; assoc=7; xbar=32 ;;
    *)
      echo "ERROR: unknown profile $profile" >&2
      exit 3
      ;;
  esac

  mapfile -t bins < <(pattern_bins "$pattern")
  for b in "${bins[@]}"; do
    core_args+=(--core-binary "$b")
  done

  local out="$OUT_ROOT/$pattern/$profile/$suffix"
  mkdir -p "$(dirname "$out")"

  "$GEM5" --outdir="$out" "$CFG" \
    --binary "${bins[0]}" \
    "${core_args[@]}" \
    "${COMMON[@]}" \
    --l2-topology "$topology" \
    --l2-size-kib "$size" \
    --l2-assoc "$assoc" \
    --l2-xbar-width "$xbar" \
    >"$out.stdout" 2>"$out.stderr"

  if ! grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout"; then
    echo "ERROR: simulation failed: $pattern/$profile/$suffix" >&2
    cat "$out.stdout" >&2
    cat "$out.stderr" >&2
    exit 4
  fi
}

echo "[2/5] Run compact 8-point topology/capacity matrix"
for pattern in pair_asym high_full; do
  for profile in private4_2p0 pair2_2p0 shared4_2p0 pair2_1p75; do
    echo "  $pattern / $profile"
    run_one "$pattern" "$profile"
  done
done

echo "[3/5] Deterministic repeat of safe baseline under high pressure"
run_one high_full pair2_2p0 repeat

echo "[4/5] Validate work parity, geometry, and summarize"
python3 - "$OUT_ROOT" <<'PY'
import csv
import math
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
patterns = ["pair_asym", "high_full"]
profiles = ["private4_2p0", "pair2_2p0", "shared4_2p0", "pair2_1p75"]

def read_stats(path):
    d = {
        "l2_overall_misses": 0,
        "l2_demand_misses": 0,
        "l2_overall_accesses": 0,
    }
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) < 2:
            continue
        k, raw = p[0], p[1]
        try:
            x = int(float(raw))
        except ValueError:
            continue

        kl = k.lower()
        if k == "simTicks":
            d["ticks"] = x
        elif k == "simInsts":
            d["insts"] = x
        elif "l2" in kl and k.endswith(".overallMisses::total"):
            d["l2_overall_misses"] += x
        elif "l2" in kl and k.endswith(".demandMisses::total"):
            d["l2_demand_misses"] += x
        elif "l2" in kl and k.endswith(".overallAccesses::total"):
            d["l2_overall_accesses"] += x

    if "ticks" not in d or "insts" not in d:
        raise RuntimeError(f"missing simTicks/simInsts in {path}")
    return d

data = {
    pat: {
        prof: read_stats(root/pat/prof/"main"/"stats.txt")
        for prof in profiles
    }
    for pat in patterns
}
repeat = read_stats(root/"high_full"/"pair2_2p0"/"repeat"/"stats.txt")

# Work parity across topology/capacity profiles for the same multicore workload.
for pat in patterns:
    insts = {data[pat][p]["insts"] for p in profiles}
    if len(insts) != 1:
        raise SystemExit(
            f"ERROR: simInsts mismatch across R5 profiles for {pat}: {sorted(insts)}"
        )

# Deterministic replay of architectural safe baseline.
main = data["high_full"]["pair2_2p0"]
for k in [
    "ticks", "insts", "l2_overall_misses",
    "l2_demand_misses", "l2_overall_accesses",
]:
    if main[k] != repeat[k]:
        raise SystemExit(
            f"ERROR: high_full pair2_2p0 repeat mismatch for {k}: "
            f"main={main[k]} repeat={repeat[k]}"
        )

# Constant-set geometry check for the PAIR2 capacity comparison.
line_bytes = 64
per_pair_2p0 = 2048 * 1024
per_pair_1p75 = 1792 * 1024
sets_2p0 = per_pair_2p0 // (8 * line_bytes)
sets_1p75 = per_pair_1p75 // (7 * line_bytes)
if sets_2p0 != 4096 or sets_1p75 != 4096:
    raise SystemExit(
        f"ERROR: constant-set geometry violated: "
        f"2p0={sets_2p0}, 1p75={sets_1p75}"
    )

def pct(a,b):
    return (a/b - 1.0) * 100.0

print()
print("=== RV64 R5: cache/L2 final sanity ===")
print(
    f"{'pattern':10s} {'profile':14s} {'ticks':>13s} {'insts':>11s} "
    f"{'vsP2_2.0':>10s} {'L2miss':>12s} {'L2dmiss':>12s} {'L2acc':>12s}"
)
for pat in patterns:
    base = data[pat]["pair2_2p0"]["ticks"]
    for prof in profiles:
        d = data[pat][prof]
        print(
            f"{pat:10s} {prof:14s} {d['ticks']:13d} {d['insts']:11d} "
            f"{pct(d['ticks'],base):+10.3f}% "
            f"{d['l2_overall_misses']:12d} {d['l2_demand_misses']:12d} "
            f"{d['l2_overall_accesses']:12d}"
        )

print()
print("=== PAIR2 1.75 MiB/pair sensitivity vs 2.00 MiB/pair ===")
for pat in patterns:
    a=data[pat]["pair2_1p75"]["ticks"]
    b=data[pat]["pair2_2p0"]["ticks"]
    print(f"{pat:10s}: {pct(a,b):+.6f}%")

print()
print("=== Frozen geometry / interconnect controls ===")
print("L1I=32 KiB, L1D=64 KiB, L1D MSHR=20/core")
print("L1D tag/data proxy=2/2; logical LSQ cache ports=2 load + 1 store")
print("L1D PF admission bucket=C4096, refill=1/24 cycles, demand reserve=0")
print("Frontend=F3D3")
print("L2 latency proxy=8/8 for all topology references")
print("Total L2 MSHRs=32: PRIVATE4 8/cache, PAIR2 16/cache, SHARED4 32/cache")
print("Aggregate L2 XBar payload=64 B/cy: 4x16 / 2x32 / 1x64, H1")
print("Common downstream membus=64 B/cy")
print("PAIR2 2.00 MiB/pair: total4096 KiB, assoc8, sets/pair=4096")
print("PAIR2 1.75 MiB/pair: total3584 KiB, assoc7, sets/pair=4096")
print()
print("=== Deterministic repeat ===")
print(
    f"high_full/pair2_2p0 ticks={main['ticks']} repeated exactly; "
    "selected cache counters identical."
)
print()
print(
    "R5 PASS gates satisfied: all 9 runs exited cleanly, work parity held "
    "within each workload pattern, constant-set PAIR2 geometry was verified, "
    "and the safe-baseline high-pressure repeat was deterministic."
)
print(
    "Topology rankings and the 1.75-vs-2.00 delta here are RV64 sanity data, "
    "not a replacement for the frozen AArch64 topology/capacity evidence."
)

with (root/"summary.csv").open("w", newline="") as f:
    wr=csv.writer(f)
    wr.writerow([
        "pattern","profile","ticks","simInsts",
        "delta_vs_pair2_2p0_pct",
        "l2_overall_misses","l2_demand_misses","l2_overall_accesses",
    ])
    for pat in patterns:
        base=data[pat]["pair2_2p0"]["ticks"]
        for prof in profiles:
            d=data[pat][prof]
            wr.writerow([
                pat,prof,d["ticks"],d["insts"],
                f"{pct(d['ticks'],base):.9f}",
                d["l2_overall_misses"],d["l2_demand_misses"],
                d["l2_overall_accesses"],
            ])
PY

echo "[5/5] Write provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "gem5_sha256=$(sha256sum "$GEM5" | awk '{print $1}')"
  echo "config_sha256=$(sha256sum "$CFG" | awk '{print $1}')"
  echo "runner_sha256=$(sha256sum scripts/rv64_cache_l2_final_sanity.sh | awk '{print $1}')"
  echo "source_sha256=$(sha256sum "$SRC" | awk '{print $1}')"
  echo "ws128_sha256=$(sha256sum "$BIN128" | awk '{print $1}')"
  echo "ws1024_sha256=$(sha256sum "$BIN1024" | awk '{print $1}')"
  echo "ws2048_sha256=$(sha256sum "$BIN2048" | awk '{print $1}')"
  echo "compiler=$($CC --version | head -n 1)"
  echo "guest_isa=rv64imafd"
  echo "scope=separate_4core_frontend_cache_cluster_sanity"
  echo "cores=4"
  echo "frontend=F3D3"
  echo "l1i=32KiB"
  echo "l1d=64KiB"
  echo "l1d_mshrs=20_per_core"
  echo "l1d_tag_data_proxy=2/2"
  echo "logical_cache_ports=2L+1S_per_cycle"
  echo "l1d_prefetch=l1d_stride_degree4_pfhit_on"
  echo "l1d_prefetch_bucket=4096"
  echo "l1d_prefetch_refill=1_per_24_cycles"
  echo "l1d_demand_mshr_reserve=0"
  echo "l2_latency_proxy=8/8"
  echo "l2_mshrs_total=32"
  echo "l2_xbar_header_latency=1"
  echo "l2_xbar_aggregate_payload=64B_per_cycle"
  echo "private4_xbar=4x16B"
  echo "pair2_xbar=2x32B"
  echo "shared4_xbar=1x64B"
  echo "membus=64B_per_cycle"
  echo "safe_baseline=PAIR2_4096KiB_total_2048KiB_per_pair_assoc8_4096sets_per_pair"
  echo "ppa_candidate=PAIR2_3584KiB_total_1792KiB_per_pair_assoc7_4096sets_per_pair"
  echo "physical_choice=RTL_SRAM_PPA_DEPENDENT"
  echo "patterns=pair_asym(L2048,L128,L2048,L128);high_full(L2048x4)"
  echo "claim_boundary=RV64_sanity_not_replacement_for_A64_topology_capacity_sweep"
} >"$OUT_ROOT/manifest.txt"

echo "CSV: $OUT_ROOT/summary.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
