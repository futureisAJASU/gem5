#!/usr/bin/env bash
set -euo pipefail

mkdir -p benchmarks/bin

CC="${RISCV64_CC:-riscv64-linux-gnu-gcc}"
COMMON=(
  -O2
  -static
  -march=rv64imafd
  -mabi=lp64d
  -Wall
  -Wextra
)

"${CC}" "${COMMON[@]}" \
  -o benchmarks/bin/independent_int_rv64 \
  benchmarks/src/independent_int.c

"${CC}" "${COMMON[@]}" \
  -o benchmarks/bin/rv64_intdiv_smoke \
  benchmarks/src/rv64_intdiv_smoke.S

file benchmarks/bin/independent_int_rv64
file benchmarks/bin/rv64_intdiv_smoke


"${CC}" \
  -O2 \
  -static \
  -nostdlib \
  -nostartfiles \
  -march=rv64imafd \
  -mabi=lp64d \
  -Wl,-e,_start \
  -o benchmarks/bin/rv64_div_fairness \
  benchmarks/src/rv64_div_fairness.S

file benchmarks/bin/rv64_div_fairness


for gap in 0 1 2 3 4 5 6 7 8; do
  "${CC}" \
    -O2 \
    -static \
    -nostdlib \
    -nostartfiles \
    -march=rv64imafd \
    -mabi=lp64d \
    -DGAP="${gap}" \
    -Wl,-e,_start \
    -o "benchmarks/bin/rv64_gap_${gap}" \
    benchmarks/src/rv64_gap_sweep.S
done

file benchmarks/bin/rv64_gap_0
file benchmarks/bin/rv64_gap_8


"${CC}" \
  -O2 \
  -static \
  -nostdlib \
  -nostartfiles \
  -march=rv64imafd \
  -mabi=lp64d \
  -Wl,-e,_start \
  -o benchmarks/bin/rv64_fma16_stress \
  benchmarks/src/rv64_fma16_stress.S

file benchmarks/bin/rv64_fma16_stress

OBJDUMP="${RISCV64_OBJDUMP:-riscv64-linux-gnu-objdump}"
fma_static_count="$("$OBJDUMP" -d benchmarks/bin/rv64_fma16_stress | awk '
  /[[:space:]]fmadd[.]d[[:space:]]/ { count++ }
  END { print count + 0 }
')"
echo "rv64_fma16_stress static fmadd.d count: $fma_static_count"
if [[ "$fma_static_count" -ne 16 ]]; then
  echo "ERROR: expected 16 static fmadd.d instructions, saw $fma_static_count" >&2
  exit 4
fi

if file benchmarks/bin/rv64_fma16_stress | grep -q 'RVC'; then
  echo "ERROR: rv64_fma16_stress unexpectedly advertises RVC" >&2
  exit 4
fi


# Historical AArch64 VMAC/SIMD experiment dimensions reconstructed for RV64:
# nominal densities 25%, 37.5%, 43.75%; burst persistence 16..8192.
for spec in "d25:2500" "d37p5:3750" "d43p75:4375"; do
  tag="${spec%%:*}"
  density_bp="${spec##*:}"

  for burst in 16 32 64 128 256 512 1024 2048 4096 8192; do
    out="benchmarks/bin/rv64_fma_bd_${tag}_b${burst}"

    "${CC}" \
      -O2 \
      -static \
      -nostdlib \
      -nostartfiles \
      -march=rv64imafd \
      -mabi=lp64d \
      -DBURST="${burst}" \
      -DDENSITY_BP="${density_bp}" \
      -Wl,-e,_start \
      -o "${out}" \
      benchmarks/src/rv64_fma_burst_density.S

    if file "${out}" | grep -q 'RVC'; then
      echo "ERROR: ${out} unexpectedly advertises RVC" >&2
      exit 4
    fi
  done
done

echo "Built 30 RV64 FMA burst-density binaries (3 densities x 10 burst sizes)."
file benchmarks/bin/rv64_fma_bd_d25_b16
file benchmarks/bin/rv64_fma_bd_d43p75_b8192
