# Little v0.52 BPU-7 — Progressive Sweep Tournament / Preparation Contract v0.2

**STATUS: PRE-FREEZE — candidate simulations not authorized.** Created 2026-10-08 (KST). This document replaces only the overly narrow single-S0 / optional 1-low+1-high approach in Notion v0.1. All frozen G5/G7 architecture facts, BPU-1–6A results, claim boundaries and backend freeze remain unchanged.

Companion files:
- Machine-readable 21-profile matrix: [bpu7_sweep_matrix_v02.json](../docs/bpu7_sweep_matrix_v02.json)
- Fail-closed plan validator: [bpu_b7_sweep_preflight.py](../scripts/bpu_b7_sweep_preflight.py)
- Branch: futureisAJASU/gem5, little-v052-bpu. Historical planning HEAD 986c8c6a09175f0a382d6bbeffa67163a0780315. Record actual HEAD/build/binary hash at P0 and runtime.

## 1. Philosophy: real sweep → narrow families → isolate axes → freeze physical Pareto winner

Every serious family C1/C2/C3/C4/C5/C7 receives finite-state gem5 implementation, real prediction-time history/index/alias/rollback/training and a full-19 multi-point trial before final elimination. No toy/oracle-only exclusion. C3 has two distinct mechanisms: PC-bias and history-tagged exception. C0 classic perceptron stays as the existing failed-but-informative reference with **no parameter/prior22 sweep**. R0 G5 and R1 G7 are mandatory anchors; C6 at most two-way composite only after parent complementarity evidence; A0 access reduction is an independent energy track.

Frozen costs: G5 = 45,736 bits, G7 = 65,192 bits, cap for G5 additional persistent state = 19,456 bits (2.375 KiB). Exact same RV64 frontend proxy: conditional index shift1, BTB shift2, indirect shift1, BTB 4,096 direct-mapped proxy, RAS16; this is not final silicon BTB. Frozen full-19 Embench ROI configuration per BPU-4C. These tests are embedded proxies, not a representative universal branch trace, and have been inspected previously (not unseen holdout).

## 2. R1 primary capacity sweep: all families, no exceptions

Machine-readable matrix is authoritative for identifiers, geometries and exact listed storage arithmetic. **21 geometry profiles × 19 frozen workloads = 399 primary M1 ROI** (not yet run). All 21 profiles use one effective G0_AND_NATIVE_G1 candidate selector, not two independent gates. G0: weak OR medium OR signed3 tagged-provider strength5 (BPU-5D). G1: candidate valid/trust/score confidence, specified and frozen at P0. Track native feature updates and training separately even if prediction read gate is closed.

| Family | First-round geometry points | Extra persistent bits as currently listed |
| --- | --- | --- |
| C1 Tiny Loop | 64 / 128 / 256 entries of 38b | 2,432 / 4,864 / 9,728 |
| C2 Local | LHT64×10 + PHT256×2; 128×10+512×2; 256×10+1024×2 | 1,152 / 2,304 / 4,608 |
| C3 Tagged | 64 / 128 / 256 of 16b each, separately PC_BIAS and HIST_TAG | 1,024 / 2,048 / 4,096 each |
| C4 MGSC | Four GEHL × 128 / 256 / 512 entries × signed5b, same-size bias × signed3b | 2,944 / 5,888 / 11,776 |
| C5 Hashed MPP | Four feature banks × 128 / 256 / 512 × signed5b + 32×6b local + 16b backward | 2,768 / 5,328 / 10,448 |
| C7 IMLI-SIC | 256 / 512 / 1024 × signed5b plus 8b IMLI and valid1 | 1,289 / 2,569 / 5,129 |

**Planning estimates, not final state accounting.** Any selector, history, replacement, valid, tag or persistent controller field omitted from a proposal must be charged and corrected **before simulation**. Bounded per-inflight checkpoint/BranchInfo bits must be recorded as transient, not silently ignored; C++ byte-container size is not an architectural logical bit count. Do not call these configurations exact iso-budget comparisons; use state-normalized Pareto envelopes.

## 3. P0 BLOCKING implementation readiness

No R1 simulation until each of the following passes:
1. Audit source APIs in src/cpu/pred/tage_base.*, bpred_unit.*, fetch stage, loop_predictor.*, statistical_corrector.*, multiperspective_perceptron_tage.*, configs/02_little_v052_rv64_proxy.py. Prove conditional PC shift, branch target availability, and whether a genuine **Cycle N+1** corrector-triggered frontend redirect is supported. M1 must charge wrong-path fetch, cancellation, history repair, redirect arbitration and restart, not spoof same-cycle final direction.
2. Pin complete exact geometry, index/hash/tag, counter sign and initial value, training threshold/learning policy, chooser/tie rule, G0/native-G1 Boolean, and replacement. Current v0.1 C1 loop lifecycle and C4/C5 train/chooser have open details; resolve before first result. C7 backward conditional detection and counter saturation/checkpoint semantics likewise.
3. Implement C1,C2,C3, C4,C5,C7 **real finite state**, with capacity aliasing, entry replacement, confidence, actual read/write activity, prediction-time snapshot and committed training. Candidate-off path must exactly reproduce G5; unrelated G7 and backend logic unchanged.
4. Directed tests: cold/valid state, alias collisions and tag false match, counter saturation, 2+ inflight same-entry, read/update collision, RVC PC indexing, history rollover/squash/replay, deterministic repeat, wrong-path update, G5/R1 no-regression, signed sum and update, native candidate-specific loop/local/IMLI edge cases. Test M0/M1/M2 timing explicitly.
5. Reconcile at each ROI: committedCond = finalCorrect + finalWrong; overrides=fixes+breaks; finalWrong=runLocalBaseWrong−fixes+breaks; all state/port/activity fields present. Different predictor speculative paths can alter dynamic event streams; never subtract unrelated R0 and candidate wrong-count totals as if exactly corresponding.
6. Record executable/commit SHA, config INI, compiler, Embench binary SHA, ROI reset, expected state, timing model, baseline seed and script hash in immutable manifests. Any post-result change requires versioned amendment and full audit.
7. Keep independent generalization corpus sealed before inspecting C1–C7 if external claims beyond existing embedded full-19 are planned.

## 4. R1 evaluation and first pruning

Run all 21×19 configurations and retain even unfavorable and failed attempts. On correctness failure stop affected experiments, preserve artifacts, repair with versioned change and rerun fair comparisons; do not alter seed after seeing a poor performance number. Environment blockers are documented separately.

Evaluate per profile: cycles/geomean versus G5 and G7, conditional MPKI, fixes, breaks, net, per-workload worst regressions, state, bounded transient state, real table/bank reads, tags, adder activity, tracking updates, training writes, M1 redirect/wrong-path fetch cost. Actual power is **not known** until RTL switching/library/macro-aware analysis.

Family-level post-R1 categories:
- **ADVANCE:** convincing Pareto competitiveness or uniquely useful residual-error class with documented plausible untested axis.
- **HOLD/VERIFY:** one bounded controlled test required to distinguish poor geometry, gate, training, collision, or late timing from ineffective algorithm.
- **REJECT FOR CURRENT BUDGET:** only after all realistic R1 points and a predeclared confound check show clear dominance by G5/G7 or a cheaper candidate; preserve original numbers.
- **BLOCKED:** independently confirmed interface/feasibility defect; never equate to algorithm accuracy loss.
- **REFERENCE:** G5/G7/C0 remain regardless.

Before rejecting a family specifically inspect: capacity/alias, actual training opportunity/warmup, selector activation and misses/fixes/breaks, tag hit/false-positive rates, M1 late penalty, and whether the largest sweep point continues to improve. A toy diagnostic alone may reprioritize but cannot reject.

## 5. R2: axis-isolated secondary sweep (versioned amendment BEFORE each experiment)

Do not brute-force the Cartesian product. A branch of experiments requires explicit question, changed variable, control configuration, bounded values, expected cost and stop criterion before results. Full-19 R2 comparisons are exploratory on a corpus already seen; claim independent confirmation only on sealed tests.

- C1: tag 8/10/12, trip/iteration width 8/10/12, fixed two-point confidence threshold after training/hysteresis correctness. If upper R1 capacity has not leveled off, test one more size under bit cap.
- C2: split R1 co-scaling into LHT-only at fixed PHT, PHT-only at fixed LHT; local history length 6/10/14 with exactly recorded speculation/rollback.
- C3: PC_BIAS vs HIST_TAG already compared at all three R1 depths; change tags 8/10/12, signed residual counter 2/3/4, native trust threshold in isolated experiments. Two-level bias+history is C6 only if both parents earn it.
- C4: banks 2/4/6 with near-iso **total** bits, then source-anchored two alternate history spectra, then counter width 4/5/6; charge full bank read/adder tree depth and train logic.
- C5: leave-one-feature-out for global8/global64/local6/backward16; compare per-bank feature cost. Only after ablation, vary weight width or hash/feature bank budget with iso-state comparator. Never free-add a fifth feature or use inaccessible register data.
- C7: IMLI width 6/8/10, table capacity, PC+iteration hash; test backward branch classification, taken increment/not-taken reset, nested loops, overflow/alias and squash before measuring improvement.
- Selector: candidate-native threshold and G0 eligibility can be independently ablated **only after** baseline 21-profile trial; ALWAYS is an upper-activity diagnostic, never an energy claim.
- Timing: for shortlisted implementations compare algorithmic M0, true M1, sensitivity M2. Architectural claims rest on M1 and eventually physical timing closure.

**Boundary rule:** if largest point is still best with no knee, allow one larger predeclared entry size only within 19,456 added bits. If smallest is essentially equivalent, try one smaller. Report unresolved knee when cap reached rather than silently expanding budget.

## 6. R3/R4: shortlist, composition, independent validation and PPA

Shortlist by objective-specific Pareto tradeoffs (cycles, worst-tail robustness, added bits, reads, ports, latency). Avoid a fabricated single energy/accuracy score or winner from oracle upper bound. Freeze selected configurations before unseen validation, when available.

C6 uses only a **pair** of independently studied predictors that fix distinct residual events. Freeze composition precedence, combined reads/ports, checkpoints, selector, state and timing *before* combined runs. Compare to both parents, G5, G7.

Finally RTL/PPA under common technology library, macro/flip-flop assumptions, clock and activity traces. Report area/Fmax/slack/dynamic/leakage, corrector ON/OFF, redirect implementation. **G5-only and G7-only remain valid final outcomes.** No algorithm novelty claim for local, loop, IMLI, MGSC, TAGE+perceptron, tagged override or lazy access.

## 7. Safe start command and output contract

After fetching research branch, run preparation **only**:

    python3 scripts/bpu_b7_sweep_preflight.py --emit bpu_b7_prep

The script validates all 21 geometry entries and their logical-bit arithmetic against the G7−G5 bound and emits 399 **NOT_IMPLEMENTED_DO_NOT_RUN** planned rows and matrix checksum. This is not an executable experiment runner. The option --require-run-ready intentionally fails while status is PRE_FREEZE.

Expected eventual full experimental artifact schema: contract SHA, predictor code/build SHA, benchmark binary SHA, workload, profile and geometry, native selector, timing model, ROI start/end, cycles, committed instructions, committed conditional, local TAGE wrong, final wrong, fixes, breaks, overrides, MPKI, bits, transient peak, issued/completed/canceled reads, bank reads, tag compares, adder evaluations, tracker updates, training writes, redirect counts, wrong-path fetch slots, test/reconciliation markers, stdout/stderr. Do not claim completion from empty CSV or an exit code with missing ROI.

## 8. Change-control decision

v0.2 proposes an **all-family R1 multi-point sweep**, replacing v0.1's premature single-S0 narrowing. This is not an approved freeze and the new candidate implementations, precise selector learning rules and M1 redirect have **not** yet been built/tested. P0 closure authorizes implementation, not optimistic publication of projected outcomes.