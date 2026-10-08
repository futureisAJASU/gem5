
# Little v0.52 BPU-7 — Multi-Stage Sweep Campaign v0.3

**Status: PRE-FREEZE / PRE-IMPLEMENTATION / NOT AN EXPERIMENT RESULT.** Date: 2026-10-08 KST. Candidate implementation, M1 late correction, and 399 ROI runs are NOT complete. This document changes the exploratory workflow, not frozen R0/R1/C0 results.

**Existing truth:** [BPU-7 Notion implementation contract](https://www.notion.so/3f36f08ed24481d09579e99cf22aded1); [Prior Art and CURRENT BPU-7 v2](https://www.notion.so/3f36f08ed2448128931fd559ec083883); frozen GitHub BPU-4C, BPU-5D, BPU-6A reports. Existing matrix: docs/bpu7_sweep_matrix_v02.json; validator: scripts/bpu_b7_sweep_preflight.py. Do not overwrite or reinterpret their results. **The draft v0.1 one-S0-only rule is superseded by this planned multi-stage sweep, subject to P0 approval.**

## 1. Experiment algorithm — breadth → shortlist → focused axis sweep → independent verification

- **P0 readiness**: independently audit all candidate prediction-time inputs, exact index/hash, tag/replacement, counter saturation/initial state, training/rollback, cost and N+1 frontend correction. Complete finite-table implementations and directed tests. Do NOT run the matrix when implementation/M1/readout verification is absent.
- **B7-1 Round I breadth**: keep the existing 21 registered geometries × 19 frozen workloads = **399 candidate ROI**. Implement all six serious families C1/C2/C3/C4/C5/C7. These must be REALISTIC gem5 predictors with finite aliasing and speculation, not trace oracles.
- **Fresh baselines**: add G5/R0 and G7/R1, **2×19=38 ROI**, on the same final gem5+binary+front-end condition unless rigorous bit-for-bit baseline equivalence is independently documented. Hence **437 planned fresh ROI including baselines**, not 399. Optional C0 historical-perceptron replay adds 19 (456 total) but does not authorize prior ±22 tuning.
- **B7-2 Round I triage**: report all configurations, even failures; construct a non-dominated Pareto shortlist over measured cycle geomean, total direction-predictor persistent state, real bank-read activity and worst-case risk. Retain near ties and complementary branch classes; don't automatically pick top-one per family. Toy-only family elimination forbidden.
- **B7-3 Round II axis search**: vary ONE variable group at a time around selected Round I points, using new versioned, finite matrix amendments with selected values sealed *before Round II execution*. Round II is adaptive engineering exploration on already-seen full-19, not independent statistical confirmation. Keep original Round I negative results.
- **B7-4 Round III**: selector, training and activity ablations, M0 same-cycle diagnostic, **M1 genuine +1-cycle late-correction primary**, M2 +2-cycle sensitivity. C6 two-auxiliary composite only after measured fix/break complementarity and a predeclared combined M1 and physical cost.
- **B7-5 holdout+PPA**: evaluate finalist choices on separately frozen outside-corpus programs/inputs (list and hashes fixed before results inspection). Then RTL area/slack/Fmax/power under identical libraries, corners, clock and memory-macro assumptions. If G5 or G7 alone is optimal, freeze that instead of forcing novelty.

## 2. Frozen Round I breadth from matrix v0.2

| Family | First-pass profiles | Primary capacity axis |
| --- | ---: | --- |
| C1 Tiny Loop | 3 | E64 / E128 / E256 |
| C2 Tiny Local | 3 | L64-P256 / L128-P512 / L256-P1024 |
| C3 Tagged Exception | 6 | PC_BIAS E64/E128/E256 **and** HIST_TAG E64/E128/E256 |
| C4 Tiny MGSC | 3 | E128 / E256 / E512, fixed 4-bank spectrum |
| C5 Hashed Multiperspective | 3 | E128 / E256 / E512, fixed four features |
| C7 Tiny IMLI-SIC | 3 | E256 / E512 / E1024 |
| **Total** | **21** | **399 candidate ROI** |

Fixed G5 = 45,736 bits; fixed G7 = 65,192 bits; G7−G5 = 19,456 bits = 2.375 KiB. Logical state values in v0.2 are preliminary field sums; selector, independently maintained histories, tracker validity, replacements, speculative checkpoint and physical array overhead must NOT disappear from final accounting. State is not equal to energy. The G7 baseline contains TAGE bank reads even when it has zero *auxiliary* reads: use total predictor reads for cross-family energy/activity comparisons.

The first pass uses one frozen G0_AND_NATIVE_G1 policy per geometry, not an unconstrained gate sweep. **An unfavorable G0-constrained result does not establish that a candidate family fails under native-only G1 gating.** G1-only is a controlled later study.

## 3. Round II registered VARIABLE FAMILIES (not yet chosen test points)

The suggested values below are only pre-result design proposals; values and exact storage formulas MUST be fixed in a versioned second-stage manifest before execution. The chosen subset is adaptive to Round I, must be marked exploratory, and must not become an enormous Cartesian grid.

| Candidate | One-factor axes and proposed levels |
| --- | --- |
| C1 | Trip/iteration width 8/10/12; tag bits 8/10/12; confidence threshold 4/6/7. Include nested loops, overflow and rollback. |
| C2 | Local history length 6/10/14; independently resize LHT at fixed PHT and PHT at fixed LHT; strong-counter policy. |
| C3 | Keep PC_BIAS vs HIST_TAG distinct; tag 8/10/12; residual-counter width 2/3/4, source-accurate confidence/selector threshold. |
| C4 | Number of GEHL banks 2/4/6; folded-history span alternatives around frozen 0/8/24/64; signed counter 4/5/6 bits; account adders and ports. |
| C5 | One-at-a-time feature removal (global8, global64, local6, backward16); 3/4 banks; weight 4/5/6 bits; remove unused feature history state. |
| C7 | IMLI counter 6/8/10 bits, index/hash choice, signed counter 3/5/7 bits; exact backward-target availability, squash, nested loop and overflow rules. |
| All | Native G1-only vs predeclared G0∧G1; separate M0/M1/M2 correction timing and bank activity. |

Only one axis group changes in a given contrast. Fixed sources/features are maintained for that contrast. If a measured interaction justifies two-factor designs, version and cap them separately before simulation, retaining the single-axis results. Do not retune features, predictor index, prior, or gate per workload or based on unfavorable post-hoc cases.

## 4. Exact accounting, provenance and comparison gates

Common condition: conditional shift 1; BTB shift 2; indirect shift 1; BTB 4096×1 **simulation proxy**; RAS 16; frozen 19 Embench workloads. Source must remain the existing Little v0.52 branch predictor frontend and backend; no backend changes.

Per profile/workload archive: HEAD/dirty status, gem5 ELF SHA256, config digest, Embench binary SHA256 and toolchain, command arguments, warmup/ROI statistics, stderr/stdout, valid exit code, predictor settings, random seeds, actual simulator stats digest, result status and any later rerun reason. Do not delete partial/failed artifacts.

Within the *same run*:
- committedConditional = finalCorrect + finalWrong
- overrides = fixes + breaks
- finalWrong = baseTAGEWrong − fixes + breaks
- completed + canceled requests reconcile with launched; late redirects and squashes are counted
- training writes cannot exceed valid eligible update opportunities per documented training semantics
- prediction-time feature vector is snapshotted and restored after squash; no future branch outcome leakage
- record exact persistent bits, separate transient per-flight checkpoint bound, total branch-predictor reads/writes, comparisons, adder operations, history/loop updates, and per-bank read/write counts.

**Readiness failure or broken reconciliation = INVALID TEST, not algorithmic defeat.** A simulator geometry can be ranked only after correctness+metadata+storage+M1 timing gates PASS. Keep bad-result runs: negative net corrections and cycle regressions are research evidence and are not reasons to modify params mid-batch.

Report per-workload cycles, conditional MPKI, instructions, fixes, breaks, net fixes, actual read/write activity and worst regression. Aggregate geomean cycle ratios vs fresh G5 and fresh G7, net fixes vs same-run base direction, weighted/unweighted risk and per-bit/per-read effectiveness. Give worst-tail counterexamples individually.

**Pareto definition:** A non-invalid candidate A dominates B only when A is no worse on measured cycle geomean, total persistent bits, total predictor bank reads, and defined worst-case regression, with at least one strict improvement beyond repeatability tolerance. Provide the raw dimensions and the caveat that RTL dynamic power and area are not yet available. Do NOT declare a unique winner from an arbitrary hand-tuned weighted score.

Family closure requires enough realistic evidence that *tested geometries/selector modes* do not justify more state/activity, not a toy-oracle inference that the abstract technique can never work.

## 5. Implementation / CLI gaps confirmed from current branch

At the time of this preparation, configs/02_little_v052_rv64_proxy.py lists G5/G7 and BPU-6 perceptron bp-type options, but **does not yet expose** C1/C2/C3/C4/C5/C7. No candidate runner should map missing profiles to G5 or a preexisting predictor. Implement explicit BP aliases and geometry parameters; make unknown profile an error.

- Build test and G5/G7 disabled-aux equivalence first; preserve classic 64×24×6 C0 report without post-hoc ±22 sweep.
- Directed candidate tests must include initialization, overflow/saturation, tag alias, collision/replacement, local-history same-PC in-flight hazard, C7 iteration update/reset and unknown backward-target, stale entries after squash, RVC PC alignment, saved speculative history and ROI accounting.
- M1 must actually redirect after one cycle; it is not same-cycle oracle with added integer penalty after the fact. Verify target availability, fetched wrong-path work, priority among competing redirects, fetch restart and history rollback.
- Only **after** these gates pass may v0.2 PRE_FREEZE be amended into a RUN_READY manifest and dispatched.

## 6. Actions and explicit non-claims

Run now, as a **preparation-only** check: python3 scripts/bpu_b7_sweep_preflight.py --emit bpu_b7_plan. It emits planned_jobs.csv and matrix.sha256, not simulator results. The command with --require-run-ready must fail while matrix is PRE_FREEZE.

Next milestones: (1) commit each candidate's real finite-state microarchitecture + directed correctness, (2) implement M1 frontend proof, (3) freeze all CLI/selector/training/hash details, (4) fresh R0/R1, (5) full B7-1 399 candidate ROI, (6) B7-2 Pareto report, (7) adaptive and declared B7-3 single-axis sweeps, (8) B7-5 final independent validation/RTL-PPA.

No performance winner, optimum numeric configuration, extra energy saved, or completed sweep is claimed by this planning document.
