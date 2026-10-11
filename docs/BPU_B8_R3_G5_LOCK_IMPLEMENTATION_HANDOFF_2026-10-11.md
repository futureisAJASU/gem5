# BPU-8 R3A/R3B — G5 Lock Validation (2026-10-11)

## Status
**IMPLEMENTED / SOURCE AND LINK CI PENDING / ACTUAL OCI SMOKE UNRUN / FULL19 UNRUN.** Never infer ROI results from workflow preflight. R2C source-level RAW remains pending separately. Not a final RTL/silicon architecture freeze; G5 remains only the research baseline. Never rewrite previous R1/R2A/R2B/R2C artifacts, C3 P0/P1 negatives, or P3 Draft PR.

Base commit: `883d685d31dc026a0e7a30d201c00abdc9c2bd68` (R2C). Branch: `little-v052-bpu8-r3-g5-lock-hash-geometry`. This PR must remain draft and unmerged until audit.

## Pre-registered factorial
Exact 45,736 logical predictor bits for all six measured profiles:

| Profile | Tables | Hash width | Geometry source |
|---|---:|---:|---|
| g5_native | 5 | 0 | R1 tg5_45 |
| g5_h11 | 5 | 11 | R1 tg5_45 |
| tg6_native | 6 | 0 | R1 tg6_45 |
| tg6_h11 | 6 | 11 | R1 tg6_45 |
| tg7_native | 7 | 0 | R1 tg7_45 |
| tg7_h11 | 7 | 11 | R1 tg7_45 |

Fixed workload list inherited byte-for-byte from `docs/bpu8_tage_isobit_r1.json`. No posthoc geometry tuning. Smoke: huffbench and qrduino, 6×2=12 *selected known workloads*; Full19: 6×19=114 first ROI runs. Hash0 means existing per-bank native width, not 0 index bits. All use same build binary and same RV64 ELF per workload.

Source assertion and config.ini gate enforce `r3TageDiagnosticsEnabled=true`, `maxNumAlloc=1`, `speculativeHistUpdate=true`, `perceptronEnabled=false`, first ROI, identical commit instruction/conditional event counts, and exact 45,736-bit state. R3A primary outcome real simTicks geometric mean with paired per-workload sign and worst regression; secondary MPKI and R3B diagnostic counters. Existing hot3 is **posthoc already inspected**, not unseen holdout.

## R3B counters and inferential boundaries
- `r3HitBank`, `r3HitBankWrong`: longest matching bank and its outcome; includes 0=bimodal. **Not** all parallel tag matches, **not** an alias fingerprint.
- `r3SelectedBankWrong`: actual provider chosen at lookup, prediction-time snapshots maintained across commit.
- `r3AltBank`: alternate tagged-bank match; 0 excluded.
- `r3PseudoNewAlloc`, `r3AlternateDisagreements`, `r3AlternateWouldFix`: committed metadata and alternative-direction counterfactual, **not** causal timing gains.
- `r3AllocAttempts`, `r3Allocations`, `r3ForcedUsefulClears`, `r3AllocByBank`: commit-time actual training/allocation operations, **not** estimates of initial prediction. These are not exact per-PC alias/collision counts or an SRAM energy model.
- Additive diagnostics gated behind opt-in; no user-visible P3/C3 routing or new TAGE policy. R3B counters are *measured only if the linked build and OCI ROI jobs run*.
- Conservation: sum hit-bank counts=committed conditionals; sum hit-bank wrong=sum selected-bank wrong=committed wrong; sum alloc by bank=actual allocations; forced clear ≤ attempts; allocation ≤ attempts.
- Scope: existing gem5 logical state excludes history checkpoint transient memory, folded history combinational gates, mux/SRAM PPA; physical design and independent holdout remain open.

## OCI execution, strict custody
```bash
set -euo pipefail
cd ~/gem5  # replace with actual OCI repository root if different
git fetch origin little-v052-bpu8-r3-g5-lock-hash-geometry
git switch little-v052-bpu8-r3-g5-lock-hash-geometry
git status --short
python3 scripts/bpu_b8_r3_g5_lock_full19.py --list
python3 scripts/bpu_b8_r3_g5_lock_full19.py --smoke --list

# Fresh R3 build: the old R2C gem5.opt SHA cannot be reused.
python3 scripts/bpu_b8_r3_g5_lock_full19.py \
  --prepare-if-missing --jobs 4 --smoke --out "$HOME/bpu8_r3_smoke_01"
# Only after smoke's own new-build, first ROI and counters pass:
python3 scripts/bpu_b8_r3_g5_lock_full19.py \
  --no-build --jobs 4 --out "$HOME/bpu8_r3_full19_01"

# Preserve ALL original raw files, stderr, config, command, manifest.
cd "$HOME"
test "$(find bpu8_r3_full19_01 -type f -name roi.stats | wc -l)" -eq 114
test "$(find bpu8_r3_full19_01 -type f -name config.ini | wc -l)" -eq 114
tar -czf bpu8_r3_full19_raw.tar.gz bpu8_r3_full19_01
sha256sum bpu8_r3_full19_raw.tar.gz
```

Do not start Full19 if Smoke fails. The runner refuses dirty tracked sources, unpinned manifest resume, duplicate/missing ROI markers, config drift, nonconserved counter values and non-matching branch/instruction counts. Simulator/ELF SHA256 are manifest-recorded (not independently rehashed until actual RAW reviewed). SimTicks source is the **first** ROI; no shadow signal is an actual frontend timing result.

## Gate for future geometry freeze
1. Source and linked-build CI green; R3 Smoke 12/12 actual with source/ELF/config hash.
2. New Full19 114/114 raw, independent source-file audit, no missing losing profiles, predeclared pair deltas.
3. Differentiate hash-width effects, bank geometry, and selected hot3 dependence. No causation purely from correlations.
4. Independent untouched held-out benchmark suite to test generalization.
5. RTL implementation and physical SRAM/mux critical path/area/energy comparison before final freeze.

Referenced original audits: R1: https://app.notion.com/p/3f56f08ed24481619212f003f24769b4; R2B: https://app.notion.com/p/3f56f08ed24481d680b0e238a9e00301; R2C: https://app.notion.com/p/3f66f08ed244815e86d6c77fff951a7f.
