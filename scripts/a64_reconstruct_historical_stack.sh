#!/usr/bin/env bash
set -euo pipefail

SOURCE_REPO="/home/ubuntu/gem5"
HIST_COMMIT="547a4323adefdff81e490caa5a5e00dc4cd7126d"
HIST_ROOT="${HIST_ROOT:-$HOME/gem5-r2-historical-547a4323}"
EXPECTED_GEM5_SHA="0b5f20709d8f94cf568f2899d5794e89bd8f729d7bfef421d5f6b70c4f9ba0d0"
EXPECTED_CONFIG_SHA="db7d16fe6c6ddcb70c78b8dd9080a85968173f2d06021580106468a4b8f4b570"
JOBS="${JOBS:-2}"
HOST_CC="${HOST_CC:-$(command -v gcc-14 || command -v gcc)}"
HOST_CXX="${HOST_CXX:-$(command -v g++-14 || command -v g++)}"
CLEAN_HIST_BUILD="${CLEAN_HIST_BUILD:-1}"

echo "=== RECONSTRUCT HISTORICAL A64 GEM5 STACK ==="
echo "source_repo=$SOURCE_REPO"
echo "historical_commit=$HIST_COMMIT"
echo "worktree=$HIST_ROOT"

git -C "$SOURCE_REPO" cat-file -e "$HIST_COMMIT^{commit}"
git -C "$SOURCE_REPO" worktree prune

if [[ -e "$HIST_ROOT" ]]; then
  if [[ ! -d "$HIST_ROOT/.git" && ! -f "$HIST_ROOT/.git" ]]; then
    echo "ERROR: $HIST_ROOT exists but is not a git worktree" >&2
    exit 2
  fi
  got="$(git -C "$HIST_ROOT" rev-parse HEAD)"
  if [[ "$got" != "$HIST_COMMIT" ]]; then
    echo "ERROR: existing historical worktree is at $got, expected $HIST_COMMIT" >&2
    exit 2
  fi
  echo "historical_worktree=reuse"
else
  git -C "$SOURCE_REPO" worktree add --detach "$HIST_ROOT" "$HIST_COMMIT"
  echo "historical_worktree=created"
fi

cfg="$HIST_ROOT/configs/01_little_v052_proxy.py"
cfg_sha="$(sha256sum "$cfg" | awk '{print $1}')"
echo "config_sha=$cfg_sha"
echo "config_sha_expected=$EXPECTED_CONFIG_SHA"
if [[ "$cfg_sha" != "$EXPECTED_CONFIG_SHA" ]]; then
  echo "ERROR: config at exact commit does not match archived manifest" >&2
  exit 3
fi
echo "config_exact=YES"

echo "=== BUILD ARM GEM5 AT EXACT HISTORICAL COMMIT ==="
echo "host_cc=$HOST_CC ($($HOST_CC --version | head -n 1))"
echo "host_cxx=$HOST_CXX ($($HOST_CXX --version | head -n 1))"
if [[ "$CLEAN_HIST_BUILD" == "1" ]]; then
  echo "historical_build_tree=clean"
  rm -rf "$HIST_ROOT/build/ARM"
fi
# IMPORTANT: gem5's SConstruct resolves relative build targets against
# SCons GetLaunchDir(), not merely the directory selected by -C.
# Therefore invoke scons *from inside* the historical worktree; using
# "scons -C $HIST_ROOT build/ARM/gem5.opt" can place the artifact in the
# caller's build/ directory.
(
  cd "$HIST_ROOT"
  scons build/ARM/gem5.opt -j"$JOBS" CC="$HOST_CC" CXX="$HOST_CXX"
)

gem5="$HIST_ROOT/build/ARM/gem5.opt"
if [[ ! -x "$gem5" ]]; then
  echo "ERROR: historical build completed but expected artifact is missing: $gem5" >&2
  echo "Nearby gem5.opt candidates:" >&2
  find "$HIST_ROOT" -maxdepth 4 -type f -name gem5.opt -print >&2 || true
  exit 4
fi
gem5_sha="$(sha256sum "$gem5" | awk '{print $1}')"
echo "gem5_sha=$gem5_sha"
echo "gem5_sha_expected=$EXPECTED_GEM5_SHA"
if [[ "$gem5_sha" == "$EXPECTED_GEM5_SHA" ]]; then
  echo "gem5_binary_exact=YES"
else
  echo "gem5_binary_exact=NO"
  echo "NOTE: source/config are exact; byte mismatch can still be build-environment metadata/toolchain related."
  echo "NOTE: the subsequent historical cycle-exact replay is the behavioral equivalence gate."
fi

echo "historical_head=$(git -C "$HIST_ROOT" rev-parse HEAD)"
echo "historical_status=$(git -C "$HIST_ROOT" status --porcelain | wc -l)"
echo "HIST_ROOT=$HIST_ROOT"
echo "HIST_GEM5=$gem5"
echo "HIST_CFG=$cfg"
