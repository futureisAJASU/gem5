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
