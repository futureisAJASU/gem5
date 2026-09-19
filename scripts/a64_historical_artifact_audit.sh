#!/usr/bin/env bash
set -euo pipefail

CURRENT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HIST_ROOT="/home/ubuntu/gem5"
HIST_EMBENCH="/tmp/embench-iot-1.0"
HIST_BUILD="/tmp/embench-aarch64-build"
CURRENT_BUILD="$CURRENT_ROOT/benchmarks/external/embench-iot/bd-a64-gem5"

WORKLOADS=(
  matmult-int
  nettle-sha256
  nettle-aes
  sglib-combined
  wikisort
  picojpeg
)

declare -A EXPECTED_BUILDID=(
  [matmult-int]="e976ee5ac66d37ce969cc7cf46127331d349fbba"
  [nettle-sha256]="7387e6292fe04229c91cca6e5d1a0b8dcbca68c3"
  [nettle-aes]="5dfdf7f839026be3e28834f83fb71a507864b98d"
  [sglib-combined]="0a6476e6c334807d25cd181e09c3a8a8ac65dfd0"
  [wikisort]="4328cd9b4158f4ba51e2c4b2dd04ea838a40b0f5"
  [picojpeg]="21ea195a1e9965226a73529b2a4eb6e0bec5c734"
)

EXPECTED_HIST_HEAD="547a4323adefdff81e490caa5a5e00dc4cd7126d"
EXPECTED_EMBENCH_HEAD="0466a18e4f6b47e19598d7c6ba72916d54b68f65"
EXPECTED_GEM5_SHA="0b5f20709d8f94cf568f2899d5794e89bd8f729d7bfef421d5f6b70c4f9ba0d0"
EXPECTED_CONFIG_SHA="db7d16fe6c6ddcb70c78b8dd9080a85968173f2d06021580106468a4b8f4b570"
EXPECTED_MATMULT_SHA="36320e01eaf9d3e25cd38f7df0c9c76f545e220c5f6b3b6c8b936e92a727121b"

build_id() {
  local f="$1"
  # Do not exit awk early: with pipefail that can SIGPIPE readelf and
  # terminate the script at the first ELF.
  readelf -n "$f" 2>/dev/null |
    awk '/Build ID:/ && !seen {print $3; seen=1}'
}

compiler_comment() {
  local f="$1"
  readelf -p .comment "$f" 2>/dev/null |
    sed -n 's/.*]  //p' |
    head -n 1
}

echo "=== A64 HISTORICAL ARTIFACT AUDIT ==="
echo "current_root=$CURRENT_ROOT"
echo "current_head=$(git -C "$CURRENT_ROOT" rev-parse HEAD)"
echo "host_compiler=$(aarch64-linux-gnu-gcc --version | head -n 1 || true)"
echo

echo "=== 1. HISTORICAL REPO / GEM5 ==="
if [[ -d "$HIST_ROOT/.git" ]]; then
  hh="$(git -C "$HIST_ROOT" rev-parse HEAD)"
  echo "hist_repo=FOUND"
  echo "hist_head=$hh"
  echo "hist_head_expected=$EXPECTED_HIST_HEAD"
  [[ "$hh" == "$EXPECTED_HIST_HEAD" ]] && echo "hist_head_match=YES" || echo "hist_head_match=NO"
else
  echo "hist_repo=MISSING"
fi

hist_gem5="$HIST_ROOT/build/ARM/gem5.opt"
if [[ -f "$hist_gem5" ]]; then
  hs="$(sha256sum "$hist_gem5" | awk '{print $1}')"
  echo "hist_gem5=FOUND"
  echo "hist_gem5_sha=$hs"
  echo "hist_gem5_sha_expected=$EXPECTED_GEM5_SHA"
  [[ "$hs" == "$EXPECTED_GEM5_SHA" ]] && echo "hist_gem5_exact=YES" || echo "hist_gem5_exact=NO"
else
  echo "hist_gem5=MISSING"
fi

hist_cfg="$HIST_ROOT/configs/01_little_v052_proxy.py"
if [[ -f "$hist_cfg" ]]; then
  cs="$(sha256sum "$hist_cfg" | awk '{print $1}')"
  echo "hist_config=FOUND"
  echo "hist_config_sha=$cs"
  echo "hist_config_sha_expected=$EXPECTED_CONFIG_SHA"
  [[ "$cs" == "$EXPECTED_CONFIG_SHA" ]] && echo "hist_config_exact=YES" || echo "hist_config_exact=NO"
else
  echo "hist_config=MISSING"
fi

echo
echo "=== 2. HISTORICAL EMBENCH SOURCE / SUPPORT ==="
if [[ -d "$HIST_EMBENCH/.git" ]]; then
  eh="$(git -C "$HIST_EMBENCH" rev-parse HEAD)"
  echo "hist_embench=FOUND"
  echo "hist_embench_head=$eh"
  echo "hist_embench_head_expected=$EXPECTED_EMBENCH_HEAD"
  [[ "$eh" == "$EXPECTED_EMBENCH_HEAD" ]] && echo "hist_embench_exact=YES" || echo "hist_embench_exact=NO"
else
  echo "hist_embench=MISSING_OR_NOT_GIT"
fi

for p in \
  "$HIST_EMBENCH/config/native/boards/gem5/boardsupport.c" \
  "$HIST_EMBENCH/config/native/boards/gem5/boardsupport.h" \
  "$HIST_EMBENCH/config/native/chips/speed-test-gcc/chipsupport.c" \
  "$HIST_ROOT/util/m5/build/arm64/out/libm5.a"
do
  if [[ -f "$p" ]]; then
    echo "FOUND $p sha256=$(sha256sum "$p" | awk '{print $1}')"
  else
    echo "MISSING $p"
  fi
done

if [[ -f "$HIST_EMBENCH/config/native/boards/gem5/boardsupport.c" ]]; then
  echo "--- historical boardsupport.c ---"
  sed -n '1,80p' "$HIST_EMBENCH/config/native/boards/gem5/boardsupport.c"
fi

echo
echo "=== 3. HISTORICAL BINARIES ==="
all_buildid_exact=1
for w in "${WORKLOADS[@]}"; do
  f="$HIST_BUILD/src/$w/$w"
  echo "--- $w ---"
  if [[ ! -f "$f" ]]; then
    echo "status=MISSING"
    all_buildid_exact=0
    continue
  fi
  id="$(build_id "$f")"
  sha="$(sha256sum "$f" | awk '{print $1}')"
  echo "path=$f"
  echo "buildid=$id"
  echo "expected_buildid=${EXPECTED_BUILDID[$w]}"
  [[ "$id" == "${EXPECTED_BUILDID[$w]}" ]] && echo "buildid_exact=YES" || {
    echo "buildid_exact=NO"
    all_buildid_exact=0
  }
  echo "sha256=$sha"
  echo "compiler_comment=$(compiler_comment "$f")"
  if [[ "$w" == "matmult-int" ]]; then
    echo "expected_matmult_sha=$EXPECTED_MATMULT_SHA"
    [[ "$sha" == "$EXPECTED_MATMULT_SHA" ]] && echo "matmult_sha_exact=YES" || echo "matmult_sha_exact=NO"
  fi
done
echo "all_historical_buildids_exact=$([[ "$all_buildid_exact" -eq 1 ]] && echo YES || echo NO)"

echo
echo "=== 4. CURRENT R2 BINARIES ==="
for w in "${WORKLOADS[@]}"; do
  f="$CURRENT_BUILD/src/$w/$w"
  echo "--- $w ---"
  if [[ ! -f "$f" ]]; then
    echo "status=MISSING"
    continue
  fi
  echo "path=$f"
  echo "buildid=$(build_id "$f")"
  echo "sha256=$(sha256sum "$f" | awk '{print $1}')"
  echo "compiler_comment=$(compiler_comment "$f")"
done

echo
echo "=== 5. OLD-vs-CURRENT IDENTITY ==="
for w in "${WORKLOADS[@]}"; do
  old="$HIST_BUILD/src/$w/$w"
  cur="$CURRENT_BUILD/src/$w/$w"
  if [[ -f "$old" && -f "$cur" ]]; then
    if cmp -s "$old" "$cur"; then
      echo "$w byte_identical=YES"
    else
      echo "$w byte_identical=NO old_buildid=$(build_id "$old") current_buildid=$(build_id "$cur")"
    fi
  else
    echo "$w comparison=UNAVAILABLE"
  fi
done

echo
echo "=== 6. RECOMMENDED NEXT PATH ==="
if [[ -f "$hist_gem5" ]] &&
   [[ "$(sha256sum "$hist_gem5" | awk '{print $1}')" == "$EXPECTED_GEM5_SHA" ]] &&
   [[ -f "$hist_cfg" ]] &&
   [[ "$(sha256sum "$hist_cfg" | awk '{print $1}')" == "$EXPECTED_CONFIG_SHA" ]] &&
   [[ "$all_buildid_exact" -eq 1 ]]; then
  echo "HISTORICAL_STACK_EXACT=YES"
  echo "next=rerun archived stock/N4 with surviving exact gem5+config+binaries, then run the same exact binaries on current central/P21313 controls"
else
  echo "HISTORICAL_STACK_EXACT=NO"
  echo "next=reconstruct historical native/speed-test-gcc build recipe and/or exact historical gem5 worktree before accepting R2 baseline"
fi
