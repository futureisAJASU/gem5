# Little v0.52 BPU-4 Methodology Audit — Literature, gem5, and Embench

Status: **METHODOLOGY REOPENED / e16384 HOLD**

Date: 2026-10-07 KST

## Executive finding

No current evidence establishes a functional bug in the Little micro-TAGE implementation or in the completed BPU-4 measurements.

However, the literature/gem5 audit shows that the current interpretation of the native tagged-entry sweep as a route to the **final micro-TAGE geometry knee** is not defensible.

The completed e256 -> e8192 sweep changed only tagged depth while freezing three tagged tables, histories 8/24/64, max history 64, tag widths 8/9/10, maxNumAlloc=1, and a 2048-entry bimodal.

That experiment remains valid, but its correct interpretation is now:

> **constrained 3-tagged-table capacity/alias-pressure characterization**

rather than an optimized TAGE capacity knee.

The staged e16384 native extension is therefore **HOLD / DO NOT RUN** until the geometry methodology is revised.

## Literature audit

The original 2006 TAGE study swept 32 Kbits through 1 Mbit. Its 8-component TAGE continued improving from about 2.61 misp/KI at 64 Kbits to 2.05 misp/KI at 1 Mbit. Therefore there is no universal rule that TAGE must saturate around 8 KiB.

At 64 Kbits, the CBP 8-component design used a base plus seven tagged tables, 512 entries per tagged table, and histories 5/9/15/25/44/76/130. gem5 stock TAGE mirrors this family with nHistoryTables=7, minHist=5, maxHist=130 and a documented 63.5-Kbit budget.

The 2007 L-TAGE study reports that a 256-Kbit predictor achieved its best accuracy with 13 components: base plus 12 tagged components, histories 4/6/10/16/25/40/64/101/160/254/403/640, and intentionally nonuniform table sizes.

The 2011 “A New Case for TAGE” study explicitly states that 32-64 Kbit budgets favor roughly 5-8 tables while 256-512 Kbit budgets favor 12-15 tables, with useful maximum history lengths ranging from about 100 to beyond 1000. Its 64-KByte reference uses 13 components and a history range starting at 6 and extending to 2000.

The same 2011 study also says the old at-most-one-entry allocation policy is mainly appropriate for small predictors or small table counts; at 256-512 Kbits, allocating up to 3-4 entries on different tables can improve warmup/transition behavior. Our current base TAGE retains maxNumAlloc=1 at every depth.

TAGE-SC-L 2016 reports 4.991 MPKI for the 8-KByte predictor and 3.986 MPKI for the 64-KByte predictor. Its 8-KByte TAGE portion alone is 58,165 bits and uses a substantially richer organization with history up to 1000; the 64-KByte design reaches history 3000. The paper also reports that simply doubling an older design was inferior to re-optimizing its organization.

Modern work such as Lin and Tarsa 2019 shows that simply scaling TAGE-SC-L eventually gives poor returns because remaining misses are dominated by hard-to-predict and rare branches. This supports a helper/corrector approach rather than indefinite TAGE growth.

Primary references:
- Seznec and Michaud, JILP 2006: https://jilp.org/vol8/v8paper1.pdf
- Seznec, L-TAGE, JILP 2007: https://jilp.org/vol9/v9paper6.pdf
- Seznec, A New Case for TAGE, 2011: https://www.cs.cmu.edu/~18742/papers/Seznec2011.pdf
- Seznec, TAGE-SC-L Branch Predictors Again, 2016: https://jilp.org/cbp2016/paper/AndreSeznecLimited.pdf
- Pruett et al., Dynamically Sizing TAGE, 2016: https://jilp.org/cbp2016/paper/StephenPruettFinal.pdf
- Lin and Tarsa, Branch Prediction Is Not a Solved Problem, 2019: https://arxiv.org/abs/1906.08170

## Current gem5 reference geometries

Current gem5 stable contains:
- stock TAGE: 7 tagged tables, minHist 5, maxHist 130, documented 63.5 Kbits;
- LTAGE_TAGE: 12 tagged tables, minHist 4, maxHist 640;
- TAGE-SC-L 8KB TAGE: 30 logical history tables/banks, minHist 4, maxHist 1000;
- TAGE-SC-L 64KB TAGE: 36 logical history tables/banks, minHist 6, maxHist 3000;
- MPP_TAGE: 15 history tables with tuned histories extending beyond 1000 and maxHist parameter 4096.

Source: gem5 stable 'src/cpu/pred/BranchPredictor.py'.

The exact structures are not all iso-budget conventional TAGE competitors. The important common point is that mature references do not scale into larger budgets while keeping only three tagged history lengths ending at 64.

## What the fixed-hash diagnostics prove

The fixed-11 and fixed-12 diagnostics remain valid.

They prove that **within the frozen three-tagged-table organization**, the large improvements from added entries are predominantly genuine capacity/alias-pressure effects rather than accidental width-dependent hash remapping.

They do not prove that a balanced TAGE predictor needs e4096/e8192 depth to obtain those results. A predictor with more history tables and a wider history spectrum may use the same total bit budget more efficiently.

## Workload/ROI audit

Official Embench documentation describes a deeply embedded suite intended to fit within roughly 64 KiB program and 64 KiB RAM footprints. Its speed methodology deliberately warms caches and repeats workloads.

Our exact pinned harness executes initialise_benchmark(), warm_caches(1), then calls start_trigger(), which performs m5_reset_stats(), followed by the timed benchmark. The predictor is therefore already warm at ROI entry; the present result is not explained by a fully cold predictor.

However, our build sets CPU_MHZ=1. At the pinned source revision, sglib-combined times 29 repeats of the same deterministic benchmark body, while qrduino times 5 repeats of the same input after one warmup. This is a short, small-footprint, highly repetitive embedded ROI.

The 2006 TAGE paper used 30-million-instruction traces and explicitly noted that even those were often considered short for branch-prediction studies. The 2011 study used roughly 50-million-micro-op traces and included much larger static-branch footprints and system activity.

Therefore the current six-workload set is valid as a Little-core embedded branch-pressure stress proxy, but it cannot establish a universal TAGE capacity knee. Increasing the Embench scale factor is useful for convergence sensitivity, but merely repeats the same inputs and does not replace diverse long traces.

## What remains valid

BPU-3 speculative-history rollback correctness, the BPU-1 BTB/conditional-index separation, exact storage accounting, pre-result workload freezing, TAGE-internal committed-direction MPKI, fixed backend/cache/frontend controls, and the fixed-hash positive-control diagnostics remain strong evidence.

No completed result needs to be discarded.

## Methodology defect

The problem is the path-dependent geometry optimization order:

entries/table sweep -> freeze depth knee -> history sweep -> table-count sweep.

TAGE table depth, number of tables, history distribution, tag widths, and allocation policy interact strongly. Freezing one axis at its performance-only optimum before allowing the others to move can force an under-componentized predictor to compensate with excessive depth.

Thus e8192 continuing to improve is not evidence that “TAGE needs 42 KiB.” It is evidence that the constrained three-table design remains capacity-sensitive.

## Revised BPU-4 structure

Existing data is retained and relabeled:

BPU-4A = constrained 3-table capacity-pressure characterization, e256 through e8192. Valid evidence; not a final geometry knee.

BPU-4A-D = fixed-hash causal diagnostics. Fixed-11 and fixed-12 are CLOSED/PASS; fixed-13 is optional narrow completion.

New required work:

BPU-4B = budget-normalized geometry comparison. Compare multiple table-count/history organizations at similar total bits.

BPU-4C = workload/ROI robustness. Bring forward full-19 Embench and training/length sensitivity.

BPU-5 = select a compact Pareto micro-TAGE seed, not the unconstrained maximum-accuracy depth point.

## Immediate decision

The staged native e16384 runner is **HOLD / DO NOT RUN**. It continues the already-identified depth-only optimization and cannot resolve the methodology question.

Highest-value next experiment:
1. run gem5 stock 63.5-Kbit TAGE under the same canonical frontend;
2. compare it with micro-TAGE e512/e1024/e2048;
3. bring full-19 replay forward for these candidates;
4. construct same/nearest-storage multi-table alternatives around the compact 5-8 KiB region;
5. only then choose the TAGE seed that enters perceptron research.

The selective perceptron remains well motivated: the literature shows difficult branches that capacity scaling alone handles inefficiently.

## Change control

This audit explicitly reopens only the BPU-4 geometry-search methodology.

It does not reopen the frozen Little v0.52 backend/I-EXEC, BPU-1 indexing condition, BPU-2 instrumentation semantics, or BPU-3 correctness closure.

The original 0.5% / 2% rule is not silently deleted. It remains valid for the constrained BPU-4A depth axis, whose current result is: **no performance knee observed through e8192**. It is no longer used as the sole criterion for final TAGE geometry selection.
