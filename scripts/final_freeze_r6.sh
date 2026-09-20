#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-2}"
OUT_ROOT="${OUT_ROOT:-final_freeze_r6}"
CLEAN_BUILD="${CLEAN_BUILD:-1}"
REUSE_BUILDS="${REUSE_BUILDS:-0}"
ALLOW_R2_ARM_ATTESTATION="${ALLOW_R2_ARM_ATTESTATION:-0}"
RUN_SMOKE="${RUN_SMOKE:-1}"

RISCV_GEM5="$ROOT/build/RISCV/gem5.opt"
ARM_GEM5="$ROOT/build/ARM/gem5.opt"

echo "=== R6 FINAL FREEZE / REPRODUCIBILITY PREFLIGHT ==="

echo "[0/7] Verify required closed-gate artifacts"
required=(
  "rv64_pair_shared_fma_burst_density/summary.csv"
  "rv64_pair_shared_fma_burst_density/manifest.txt"
  "a64_r2_historical_exact/summary.csv"
  "a64_r2_historical_exact/manifest.txt"
  "a64_r2_historical_exact/historical_binary_sha256.txt"
  "rv64_p21313_writecap_control/summary.csv"
  "rv64_p21313_steering_recovery/summary.csv"
  "rv64_p21313_i1f_n5_closeout/summary.csv"
  "rv64_p21313_i1f_n5_closeout/manifest.txt"
  "rv64_execution_tile_integration/summary.csv"
  "rv64_execution_tile_integration/manifest.txt"
  "rv64_cache_l2_final_sanity/summary.csv"
  "rv64_cache_l2_final_sanity/manifest.txt"
)
for f in "${required[@]}"; do
  [[ -s "$f" ]] || {
    echo "ERROR: required freeze artifact missing/empty: $f" >&2
    exit 10
  }
  echo "  OK $f"
done

echo "[1/7] Repository hygiene"
git diff --check
tracked_dirty="$(git status --porcelain --untracked-files=no)"
if [[ -n "$tracked_dirty" ]]; then
  echo "ERROR: tracked working tree is not clean:" >&2
  printf '%s\n' "$tracked_dirty" >&2
  exit 11
fi
echo "tracked_tree_clean=YES"
echo "head=$(git rev-parse HEAD)"
echo "branch=$(git rev-parse --abbrev-ref HEAD)"

if [[ "$REUSE_BUILDS" == "1" ]]; then
  echo "[2/7] Reuse already completed ISA build evidence"
  [[ -x "$RISCV_GEM5" ]] || { echo "ERROR: REUSE_BUILDS=1 but RISCV gem5.opt is missing" >&2; exit 12; }
  echo "riscv_build=REUSED"

  if [[ -x "$ARM_GEM5" ]]; then
    echo "arm_build=REUSED"
    ARM_SHA="$(sha256sum "$ARM_GEM5" | awk '{print $1}')"
    ARM_EVIDENCE="live_binary"
  elif [[ "$ALLOW_R2_ARM_ATTESTATION" == "1" ]]; then
    R2_MANIFEST="a64_r2_historical_exact/manifest.txt"
    [[ -s "$R2_MANIFEST" ]] || { echo "ERROR: missing R2 manifest for ARM attestation" >&2; exit 12; }

    R2_HEAD="$(awk -F= '$1=="current_head"{print $2}' "$R2_MANIFEST")"
    R2_ARM_SHA="$(awk -F= '$1=="current_gem5_sha"{print $2}' "$R2_MANIFEST")"
    R2_CFG_SHA="$(awk -F= '$1=="current_config_sha"{print $2}' "$R2_MANIFEST")"
    CUR_CFG_SHA="$(sha256sum configs/01_little_v052_proxy.py | awk '{print $1}')"

    [[ -n "$R2_HEAD" && -n "$R2_ARM_SHA" && -n "$R2_CFG_SHA" ]] || {
      echo "ERROR: incomplete R2 ARM attestation fields" >&2
      exit 12
    }
    [[ "$R2_CFG_SHA" == "$CUR_CFG_SHA" ]] || {
      echo "ERROR: current A64 config differs from R2-attested config" >&2
      exit 12
    }

    NON_SCRIPT_CHANGES="$(git diff --name-only "$R2_HEAD"..HEAD --       ':(exclude)scripts/**' || true)"
    if [[ -n "$NON_SCRIPT_CHANGES" ]]; then
      echo "ERROR: non-script files changed since R2 ARM validation:" >&2
      printf '%s\n' "$NON_SCRIPT_CHANGES" >&2
      exit 12
    fi

    ARM_SHA="$R2_ARM_SHA"
    ARM_EVIDENCE="R2_attested_binary_source_equivalent"
    echo "arm_build=R2_ATTESTED"
    echo "arm_r2_head=$R2_HEAD"
    echo "arm_attested_sha256=$ARM_SHA"
    echo "arm_non_script_changes_since_r2=NONE"
    echo "arm_current_config_sha_matches_r2=YES"
  else
    echo "ERROR: ARM gem5.opt missing; set ALLOW_R2_ARM_ATTESTATION=1 to use R2 evidence" >&2
    exit 12
  fi
else
  echo "[2/7] Build current RISCV + ARM gem5"
  if [[ "$CLEAN_BUILD" == "1" ]]; then
    rm -rf build/RISCV build/ARM
  fi
  scons build/RISCV/gem5.opt -j"$JOBS"
  scons build/ARM/gem5.opt -j"$JOBS"

  [[ -x "$RISCV_GEM5" ]] || { echo "ERROR: missing RISCV gem5.opt" >&2; exit 12; }
  [[ -x "$ARM_GEM5" ]] || { echo "ERROR: missing ARM gem5.opt" >&2; exit 12; }
  ARM_SHA="$(sha256sum "$ARM_GEM5" | awk '{print $1}')"
  ARM_EVIDENCE="fresh_or_existing_live_binary"
fi

echo "[3/7] Selected final-head smoke"
if [[ "$RUN_SMOKE" == "1" ]]; then
  SKIP_BUILD=1 bash scripts/rv64_revalidation_smoke.sh \
    2>&1 | tee "$OUT_ROOT.smoke.log"
else
  echo "smoke=SKIPPED"
fi

echo "[4/7] Assemble immutable evidence package"
rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT/evidence" "$OUT_ROOT/source_hashes"

for d in \
  rv64_pair_shared_fma_burst_density \
  a64_r2_historical_exact \
  rv64_p21313_writecap_control \
  rv64_p21313_steering_recovery \
  rv64_p21313_i1f_n5_closeout \
  rv64_execution_tile_integration \
  rv64_cache_l2_final_sanity
do
  mkdir -p "$OUT_ROOT/evidence/$d"
  for f in summary.csv manifest.txt historical_binary_sha256.txt; do
    if [[ -s "$d/$f" ]]; then
      cp -a "$d/$f" "$OUT_ROOT/evidence/$d/$f"
    fi
  done
done

hash_if_present() {
  local f="$1"
  if [[ -f "$f" ]]; then
    sha256sum "$f"
  fi
}

{
  hash_if_present configs/01_little_v052_proxy.py
  hash_if_present configs/02_little_v052_rv64_proxy.py
  hash_if_present src/cpu/o3/inst_queue.cc
  hash_if_present src/cpu/o3/inst_queue.hh
  hash_if_present src/cpu/o3/fu_pool.cc
  hash_if_present src/cpu/o3/fu_pool.hh
  hash_if_present src/arch/arm/decoder.hh
  hash_if_present src/arch/riscv/decoder.hh
  hash_if_present scripts/a64_r2_historical_exact_replay.sh
  hash_if_present scripts/rv64_p21313_writecap_control.sh
  hash_if_present scripts/rv64_p21313_steering_recovery.sh
  hash_if_present scripts/rv64_p21313_i1f_n5_closeout.sh
  hash_if_present scripts/rv64_execution_tile_integration.sh
  hash_if_present scripts/rv64_cache_l2_final_sanity.sh
  hash_if_present scripts/rv64_pair_shared_fma_burst_density.sh
} > "$OUT_ROOT/source_hashes/sha256.txt"

echo "[5/7] Write final freeze decisions / provenance"
{
  echo "freeze_head=$(git rev-parse HEAD)"
  echo "freeze_branch=$(git rev-parse --abbrev-ref HEAD)"
  echo "freeze_commit_time=$(git show -s --format=%cI HEAD)"
  echo "host_uname=$(uname -a)"
  echo "host_arch=$(uname -m)"
  echo "gcc=$(gcc --version 2>/dev/null | head -n 1 || true)"
  echo "gxx=$(g++ --version 2>/dev/null | head -n 1 || true)"
  echo "python=$(python3 --version 2>&1)"
  echo "scons=$(scons --version | head -n 1)"
  echo "riscv_gem5_sha256=$(sha256sum "$RISCV_GEM5" | awk '{print $1}')"
  echo "arm_gem5_sha256=$ARM_SHA"
  echo "arm_gem5_evidence=$ARM_EVIDENCE"
  echo
  echo "R1=PASS_pair_shared_FP_persistence"
  echo "R2=PASS_A64_historical_cycle_exact_and_int1_first_confirmation"
  echo "R3a=PASS_DIAGNOSTIC_first_fit_configuration_REJECTED"
  echo "R3b=PASS_int1_first_recovery_ACCEPTED"
  echo "R3c=PASS_final_int1_first_N4_N5_sensitivity"
  echo "R4=PASS_two_core_execution_tile_integration"
  echo "R5=PASS_separate_four_core_frontend_cache_cluster_sanity"
  echo
  echo "execution_scope=2core_execution_tile"
  echo "cache_frontend_scope=separate_4core_cluster"
  echo "scheduler_queues=10,6,12,4,6"
  echo "scheduler_caps=P21313:2,1,3,1,3"
  echo "int_steering=int1-first"
  echo "local_iq_picker=enabled"
  echo "issue_width=3_per_core"
  echo "n_skip=N4_Head_through_Head_plus_4_max_5_positions"
  echo "pair_shared_intdiv=1_per_2cores_latency20_nonpipelined"
  echo "pair_shared_fpsimd=enabled_in_validated_2core_tile"
  echo
  echo "cache_safe_topology=PAIR2"
  echo "cache_safe_l2_total=4096KiB"
  echo "cache_safe_l2_per_pair=2048KiB"
  echo "cache_safe_l2_assoc=8"
  echo "cache_safe_l2_sets_per_pair=4096"
  echo "cache_candidate_1p75MiB_per_pair=NOT_FROZEN_sensitivity_only"
  echo
  echo "claim_boundary_N4=selected_operating_point_not_universal_optimum"
  echo "claim_boundary_P21313=evaluated_candidate_not_PPA_optimum"
  echo "claim_boundary_fairness=directed_service_count_only_not_theorem"
  echo "claim_boundary_cross_isa=qualitatively_consistent_not_ISA_independent"
  echo "claim_boundary_scope=no_full_4core_end_to_end_validation"
} > "$OUT_ROOT/freeze_manifest.txt"

echo "[6/7] Verify packaged evidence hashes"
(
  cd "$OUT_ROOT"
  find evidence source_hashes -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum
) > "$OUT_ROOT/package_sha256.txt"

tar -czf "$OUT_ROOT.tar.gz" "$OUT_ROOT"

echo "[7/7] Final report"
echo "freeze_head=$(git rev-parse HEAD)"
echo "riscv_gem5_sha256=$(sha256sum "$RISCV_GEM5" | awk '{print $1}')"
echo "arm_gem5_sha256=$ARM_SHA"
echo "arm_gem5_evidence=$ARM_EVIDENCE"
echo "package=$OUT_ROOT.tar.gz"
echo "package_sha256=$(sha256sum "$OUT_ROOT.tar.gz" | awk '{print $1}')"
echo
echo "R6 PASS: required evidence present, tracked tree clean, current RISCV/ARM clean builds succeeded,"
echo "selected final-head smoke completed (unless explicitly skipped), and freeze package was assembled."
