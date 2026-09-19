#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HIST_ROOT="${HIST_ROOT:-/tmp/gem5-r2-historical-547a4323}"
HIST_BUILD="${HIST_BUILD:-/tmp/embench-aarch64-build}"
OUT="${OUT:-/tmp/a64-r2-portable-bundle}"
JOBS="${JOBS:-$(nproc)}"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

echo "=== PREPARE PORTABLE A64 R2 BUNDLE ==="

[[ -x "$HIST_ROOT/build/ARM/gem5.opt" ]] || {
  echo "ERROR: historical gem5 missing: $HIST_ROOT/build/ARM/gem5.opt" >&2
  exit 2
}
[[ -f "$HIST_ROOT/configs/01_little_v052_proxy.py" ]] || {
  echo "ERROR: historical config missing" >&2
  exit 2
}

echo "[1/4] Rebuild current ARM gem5 with this server's known-good toolchain"
scons build/ARM/gem5.opt -j"$JOBS"

echo "[2/4] Verify historical benchmark ELF set"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$HIST_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing historical ELF: $w" >&2
    exit 3
  }
done

echo "[3/4] Stage artifacts"
rm -rf "$OUT"
mkdir -p "$OUT/historical" "$OUT/current" "$OUT/embench/src"

cp "$HIST_ROOT/build/ARM/gem5.opt" "$OUT/historical/gem5.opt"
cp "$HIST_ROOT/configs/01_little_v052_proxy.py" "$OUT/historical/01_little_v052_proxy.py"
cp "$ROOT/build/ARM/gem5.opt" "$OUT/current/gem5.opt"

for w in "${WORKLOADS[@]}"; do
  mkdir -p "$OUT/embench/src/$w"
  cp "$HIST_BUILD/src/$w/$w" "$OUT/embench/src/$w/$w"
done

{
  echo "source_repo=$ROOT"
  echo "source_head=$(git rev-parse HEAD)"
  echo "historical_head=$(git -C "$HIST_ROOT" rev-parse HEAD)"
  echo "historical_gem5_sha=$(sha256sum "$OUT/historical/gem5.opt" | awk '{print $1}')"
  echo "historical_config_sha=$(sha256sum "$OUT/historical/01_little_v052_proxy.py" | awk '{print $1}')"
  echo "current_gem5_sha=$(sha256sum "$OUT/current/gem5.opt" | awk '{print $1}')"
  echo "host_gcc=$(gcc --version | head -n 1)"
  echo "host_gxx=$(g++ --version | head -n 1)"
  for w in "${WORKLOADS[@]}"; do
    echo "elf_sha_$w=$(sha256sum "$OUT/embench/src/$w/$w" | awk '{print $1}')"
  done
} >"$OUT/manifest.txt"

echo "[4/4] Pack bundle"
tar -C "$(dirname "$OUT")" -czf "$OUT.tar.gz" "$(basename "$OUT")"

echo "bundle_dir=$OUT"
echo "bundle_tar=$OUT.tar.gz"
echo "bundle_sha256=$(sha256sum "$OUT.tar.gz" | awk '{print $1}')"
