# Little v0.52 / BPU-7 — P0 residual vs P1 chooser same-binary shadow comparative contract

**Date:** 2026-10-09. **Status:** PRE-FREEZE DIAGNOSTIC, NO M1 FRONTEND CORRECTION.
**Revision:** first 152-ROI P0/P1 *experimental runner*, separate from original 21-profile frozen Round-I plan.
**Branch:** `little-v052-bpu7-c3-chooser-p1`, draft PR #2. The user's old P0 OCI worktree and completed 95-ROI data must remain untouched.

## 1. Why this comparison exists

The historical P0 PC_RESIDUAL 19-workload ROI run completed 95/95 with G5/G7 and three P0 sizes. Its C3 P0 counterfactual results were:

| Predictor | wouldFix | wouldBreak | net fixes−breaks |
|---|---:|---:|---:|
| P0 E64 | 4,366 | 6,016 | −1,650 |
| P0 E128 | 4,249 | 5,740 | −1,491 |
| P0 E256 | 4,174 | 5,541 | −1,367 |

These are **counterfactual on the *unmodified* G5 path**. They are *not* the effect of a real re-directed frontend or M1 performance. Provenance source: user-generated OCI 95-ROI console result; original `results.csv` and `manifest.json` are in the user's P0 result directory, not embedded or fabricated here.

P1 is independently trained on PC-local taken/not-taken and uses a disagreement-trained chooser; whether it overcomes P0's break rate is **UNKNOWN pending real ROI**.

## 2. Workloads, profiles, state

**Identical full-19 Embench RV64 GNU/Linux binaries** from the previously pinned `embench-iot` revision `0466a18e4f6b47e19598d7c6ba72916d54b68f65`; no alternate compilers or workloads permitted without separate report. The runner checks the original 19-name BPU-7 workload matrix and records SHA256 of every binary.

One newly built `build/RISCV/gem5.opt` from this P1 review branch, with exact simulator SHA256, executes the following eight configurations for every workload:

| Config | bp type | Logical total bits |
|---|---|---:|
| G5 | `tage5-iso45k` | 45,736 |
| G7 | `tage7-iso65k` | 65,192 |
| P0 E64 | `tage5-c3-pcbias-shadow-e64` | 46,760 |
| P0 E128 | `tage5-c3-pcbias-shadow-e128` | 47,784 |
| P0 E256 | `tage5-c3-pcbias-shadow-e256` | 49,832 |
| P1 E64 | `tage5-c3-pcchooser-shadow-e64` | 46,824 |
| P1 E128 | `tage5-c3-pcchooser-shadow-e128` | 47,912 |
| P1 E256 | `tage5-c3-pcchooser-shadow-e256` | 50,088 |

Total **8 × 19 = 152 first-ROI experiments**. Index shifts: inst/conditional=1, BTB=2, indirect=1; BTB entries=4096. The runner preserves the historical first statistics dump and refuses missing/partial dumps.

## 3. Execution and metrics

Command: `python3 scripts/bpu_b7_c3_p0_p1_full19.py --jobs 2 --embench-build /abs/old/embench-iot/bd-rv64-gem5 --out /abs/new/output`.

The one-command script:
1. Runs **both** C3 production-header C++ directed suites.
2. Runs an incremental full `scons build/RISCV/gem5.opt --ignore-style -j2` and fails on compilation errors.
3. Reuses old pinned Embench binaries (or prepares them only when explicitly requested).
4. Runs each of 152 ROIs sequentially and requires `SIMULATION_EXIT_CODE=0`, proper ROI delimiters, complete counters and accounting.
5. Enforces same G5-path `simTicks`, `simInsts`, `committedConditionalPredictions`, `committedConditionalWrong`, `finalConditionalWrong` for every P0/P1 shadow profile. G7 instruction count must match G5.
6. Validates **P0 residual** and **P1 chooser** logical bits and independent stat families, including disagreement/chooser updates, allocation/collision/stale counts.
7. Writes `manifest.json` (immutable inputs and hashes), `results.csv`, `summary.txt`, per-run `command.json`, original `stats.txt`, extracted `roi.stats`, stdout/stderr and `.verified.json` checkpoint files.
8. Supports `--resume` with **exact** SHA256 manifest equality. It never silently destroys prior failed/incomplete output.

**Definition:** `shadowNet = wouldFix - wouldBreak`. The hypothetical new wrong count would be `G5_wrong - wouldFix + wouldBreak` on the **unaltered G5 path**; this is an oracle-style local outcome comparison, *not* a new performance trace. A shadow design cannot claim lower measured `simTicks` or cycles.

## 4. Explicit known limitations and no-go conditions

1. **P1 ABA:** A–B–A reallocation can make a saved older-PC A branch train a distinct new A generation, because the 17-bit persistent P1 row contains no generation counter. `testSameTagAbaExposure_KnownLimitation` is an **exposure regression**, NOT a fix. Do not declare RTL-ready, safety-proven against stale same-tag metadata, or M1-ready. A generation guard would change the state budget; cannot add it silently.
2. **Selector/G0 exploration:** P1 trains direction only on G0-eligible branches, and comparative chooser only on *strong-direction* prediction-time disagreement. Lack of selection may mean starvation/low coverage, not necessarily correct conservatism.
3. **G5 update dynamics:** P1 direction is independent per PC but NOT contextual; it can lag if G5 learns quickly or a PC has history-dependent outcomes. Any wouldFix/wouldBreak must be analyzed by workload, not just aggregate.
4. **Transient storage:** Both P0 16-bit and P1 17-bit figures are **logical persistent bits only**, excluding branch-info snapshots, queues, read/write ports, SRAM macros, routing, energy and timing.
5. **M1 is unimplemented:** No N+1 redirect, no rollback or real corrected cycle measurements. Do not register the eight-profile diagnostic as completion of official frozen 21-profile / 399 ROI matrix.
6. **No post-hoc reparameterization:** Current E64/E128/E256 and P1 gate/threshold are fixed inputs to this diagnostic; new chooser threshold variants require separate named runs.

## 5. Implementation and verification

- [P1 production C++ engine](https://github.com/futureisAJASU/gem5/blob/little-v052-bpu7-c3-chooser-p1/src/cpu/pred/little_c3_pc_chooser.hh)
- [ABA exposure and P1 directed suite](https://github.com/futureisAJASU/gem5/blob/little-v052-bpu7-c3-chooser-p1/tests/bpu7/c3_pc_chooser_directed.cc)
- [Same-binary 152-ROI runner](https://github.com/futureisAJASU/gem5/blob/little-v052-bpu7-c3-chooser-p1/scripts/bpu_b7_c3_p0_p1_full19.py)
- [Synthetic test of harness accounting](https://github.com/futureisAJASU/gem5/blob/little-v052-bpu7-c3-chooser-p1/tests/bpu7/test_c3_p0_p1_runner.py)

Until actual OCI output has been independently reviewed, **no actual P1 ROI, accuracy gain, energy benefit or M1 performance is established**.
