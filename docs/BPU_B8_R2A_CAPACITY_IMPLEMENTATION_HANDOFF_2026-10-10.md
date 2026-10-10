# BPU-8 R2A — seven-bank capacity-knee Full-19 implementation handoff

**Status: IMPLEMENTED / CI SYNTHETIC PASS / OCI FIRST-ROI SMOKE AND 209-ROI FULL-19 NOT YET RUN.**

R1 audit primary immutable source: [BPU-8 RAW 190/190, 330016/330016 PASS](https://app.notion.com/p/3f56f08ed24481619212f003f24769b4). This R2A research branch descends from frozen R1 commit `6aeed4f092c86f8c3b25654cf71f9398457bdc06` and **does not touch R1 registered geometry JSON, code runner, TAGE C++, or frozen CPU backend**. Do not cherry-pick/merge into frozen architecture before new validation.

## Experiment contents

- Registry: `docs/bpu8_r2a_capacity_knee_v01.json`, pre-registered 7 capacity-path points including TG7-45 reference + 50,088-bit TG7-50 tag-width control + untouched G5/G7/Stock anchors = **11 profiles ×19 workloads=209 paired first-ROI runs**.
- Six new seven-bank geometries use fixed histories 5/9/15/25/44/76/130, tags 8/8/9/9/9/10/10, 3-bit ctr, 2-bit useful, Bimodal 2048, maxNumAlloc 1, history 130, speculative rollback on, default `fixedIndexHashLogSize=0`. No C3, perceptron, fetch redirect changes.
- 7 capacity-path bit sizes: **43,816; 45,736; 49,064; 49,576; 52,904; 60,072; 60,584** bits. Paired tag-width ablation reuses TG7-50 50,088 bits. Other reference anchors G5 45,736, G7 and Stock each 65,192.
- `configs/02_little_v052_rv64_proxy.py` uses the same original `LittleTAGE5Iso45K` object and sets geometry parameters before instantiate (six new types). No TAGEBase C++ source change.
- `scripts/bpu_b8_r2a_capacity_full19.py` preserves first ROI raw data, all per-job stdout/stderr/stats/config, immutable SHA manifest and fail-closed resume; additionally **checks actual gem5-generated `config.ini` per job** (not just reported storageBits). Post-run computes 8 **pre-registered paired edges** with relative geomean simTicks delta and %/KiB. Do not interpret non-nested capacity points as a single monotone curve.
- `tests/bpu8/test_r2a_capacity.py` and GitHub Actions test preregistration mutation refusal, 11 instantiated parameter profiles, first ROI parsing and 209/22 run counts.

## Important experimental methodology

- The original TG7-45→TG7-50 comparison changes BOTH final-bank entries and its tag width. New R2A_LG49 (49,576b) isolates last-bank entries at unchanged 10-bit tag; comparing against TG7-50 (50,088b) isolates that bank's added tag bit at 512 entries.
- Capacity growth itself may alter **gem5's default hash mixing width** because it depends on `logTagTableSizes`. This R2A captures the normal physical configuration effects of growing a bank but is not a pure abstract capacity-only test. Fixed-hash ablations require a later separate matrix and work on 7-bank hash alias effects. Never silently change `fixedIndexHashLogSize` during this trial.
- No true global knee inferred merely from 7-bank fixed-history geometry; compare R2B geometry alternatives across budgets after R2A; new workloads and RTL SRAM/PPA remain mandatory.
- Repetitive Embench Full-19 is ALREADY OBSERVED exploratory development evidence, not an independent holdout. Pre-pick/lock new long traces in a separate suite before final generalization.
- Original R1 gem5.opt **manifest SHA256**: `96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced`. R2A does not change gem5 C++; to strengthen same-binary comparisons, you may **reuse this exact R1 gem5.opt with `--gem5` and `--no-build`**. This is preferable to an unnecessary recompilation and guarantees exact simulator binary identity if hash matches. Source for R2A Python config and matrix is loaded from its own worktree. Pin/check hash BEFORE running.

## Safe OCI handoff — reuse R1 compiled RISCV binary, separate worktree and raw

From your existing `~/gem5-bpu8-tage` checkout (which may be a detached worktree):

```bash
cd "$HOME/gem5-bpu8-tage"
git fetch origin refs/heads/little-v052-bpu8-r2a-capacity-knee:refs/remotes/origin/little-v052-bpu8-r2a-capacity-knee
git worktree add --detach "$HOME/gem5-bpu8-r2a" origin/little-v052-bpu8-r2a-capacity-knee
cd "$HOME/gem5-bpu8-r2a"
git rev-parse HEAD
python3 -m unittest discover -s tests/bpu8 -p 'test_*.py' -v
python3 scripts/bpu_b8_r2a_capacity_full19.py --list | tail -1
python3 scripts/bpu_b8_r2a_capacity_full19.py --smoke --list | tail -1

GEM5="$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt"
test -f "$GEM5" || { echo "No reusable R1 gem5.opt"; exit 1; }
ACTUAL_SHA="$(sha256sum "$GEM5" | awk '{print $1}')"
EXPECTED_SHA="96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced"
test "$ACTUAL_SHA" = "$EXPECTED_SHA" || { echo "R1 binary hash mismatch: $ACTUAL_SHA"; exit 1; }
echo "R1_GEM5_BINARY_REUSE=PASS"
```

**Smoke only first**, with exactly two previously inspected branch-heavy workloads ×11 profiles = **22 ROIs**. Use an output path never used before:

```bash
cd "$HOME/gem5-bpu8-r2a"
set -o pipefail
python3 scripts/bpu_b8_r2a_capacity_full19.py \
  --no-build --jobs 2 --smoke \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu8_r2a_smoke_01" \
  2>&1 | tee "$HOME/bpu8_r2a_smoke_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2A_SMOKE_EXIT_CODE=$RC"
```

Expected **only if successful**, not a claim already achieved: `ROI_CHECKED=22/22`, `BPU8_R2A_CAPACITY_SMOKE=PASS`, `BPU8_R2A_ACTUAL_FRONTEND_ROI_REPRO=PASS`, `BPU8_R2A_SMOKE_EXIT_CODE=0`.

After smoke successful and independent inspection of any unforeseen simulator problem, run **209 first ROIs** with the **same executable sha**, no code/matrix changes:

```bash
cd "$HOME/gem5-bpu8-r2a"
set -o pipefail
python3 scripts/bpu_b8_r2a_capacity_full19.py \
  --no-build --jobs 2 \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu8_r2a_full19_01" \
  2>&1 | tee "$HOME/bpu8_r2a_full19_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2A_FULL19_EXIT_CODE=$RC"
```

The console MUST show `ROI_CHECKED=209/209`, `BPU8_R2A_CAPACITY_FULL19=PASS`, `BPU8_R2A_ACTUAL_FRONTEND_ROI_REPRO=PASS` and exit 0 before marking completed.

**No blind failure recovery:** a failed profile's raw data remains saved; original runner only reuses full, manifest-matched completed runs with `--resume`. A source change means a new Git SHA/manifest/output and new execution, not overwriting old results. Do not turn hard-error profiles into false full19 pass.

## Postrun independent audit and kneepoint rubric

1. Archive raw full19 + log, 209 original ROI, config.ini, manifest, result CSV, summary and per-run original stats. Compute tar SHA on OCI, verify again after copying to PC, upload original tar to conversation for independent audit. No source/ELF binary file itself necessarily included; manifest hash only verifies declared identity unless original executable bytes are also provided.
2. Plot per-workload and aggregate `simTicks` vs bits for **each independently nested growth path**; calculate Δ%/KiB for each predeclared positive-sized edge. Compare committed conditional wrong counts and worst-tail. Distinguish actual gem5 proxy cycles from architecture gate depth.
3. Do not declare knee based on a single anomalous bank-size step, a 2-benchmark smoke, or significant regression hidden by 3 workloads. Predeclare second round R2B 4/5/6/7-bank frontier and new independent benchmarks separately.

**Current status as of implementation:** code/CI only; no new measured R2A ROI.
