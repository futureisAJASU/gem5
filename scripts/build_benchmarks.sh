#!/usr/bin/env bash
set -euo pipefail

mkdir -p benchmarks/bin

aarch64-linux-gnu-gcc \
  -O2 \
  -static \
  -march=armv8-a \
  -Wall \
  -Wextra \
  -o benchmarks/bin/independent_int \
  benchmarks/src/independent_int.c

file benchmarks/bin/independent_int
