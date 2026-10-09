# BPU-7 C3 P2: PC / GHR16 failure diagnostics (2026-10-09)

**Status:** P2 instrumentation and synthetic analyzer tests implemented. Full RISCV linked build and four-workload diagnosis NOT YET EXECUTED. NO M1 CLAIM.

## Scope and prior evidence

Isolated branch: little-v052-bpu7-c3-pcdiag-p2, forked from P1 commit 6ce88d609c3d1c09eceabf07841565d80e670510. Existing P0/P1 branches and OCI 95/152-ROI evidence remain unchanged.

The user-provided OCI shadow-152 transcript reports P1 E256 2803 wouldFix / 3084 wouldBreak (net -281) compared with P0 E256 4174 / 5541 (net -1367). These are counterfactual, not actual M1 performance. Four **preselected** diagnoses (P1 E256 first-ROI shadow net): huffbench -207, qrduino -37, sglib-combined -52, cubic +20. Do not tune or silently cherry-pick a PC after examining new trace results.

## What the new debug flag measures

- Opt-in gem5 debug flag TageC3Diag, registered in src/cpu/pred/SConscript.
- Capture latest 16 speculative global history bits at prediction time in a debug transient BranchInfo field. This is NOT persistent 17-bit P1 SRAM state or a new HIST_TAG predictor.
- For G0-eligible **committed** P1 conditional branches, trace PC, saved GHR16, G5 and C3 prediction, actual outcome, G5 provider confidence and strength, C3 index/tag/hit, direction/chooser counts, proposed override, wouldFix/wouldBreak, allocations, eviction, collision-block and stale flags.
- No C3 algorithm change, no new predictor state table, no speculative training, no G5 direction or timing change, no frontend late redirect.
- Full-execution trace events MAY INCLUDE pre/post first ROI setup. FIRST ROI remains the original first stats dump; never silently equate full-execution per-PC event totals with first-ROI aggregate counters. The analyzer labels trace scope FULL_EXECUTION_DEBUG_TRACE_NOT_ROI_ALIGNED.

## OCI execution

Worktree from the existing original repository (leave P0 and P1 untouched):

    cd ~/gem5-bpu7-c3
    git fetch origin refs/heads/little-v052-bpu7-c3-pcdiag-p2:refs/remotes/origin/little-v052-bpu7-c3-pcdiag-p2
    git worktree add --detach "$HOME/gem5-bpu7-c3-p2" origin/little-v052-bpu7-c3-pcdiag-p2
    cd ~/gem5-bpu7-c3-p2
    python3 scripts/bpu_b7_c3_pcdiag_p2.py --jobs 2 \
      --bench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
      --out "$HOME/bpu7_c3_pcdiag_p2"

The script performs incremental gem5 build and exactly FOUR workloads x TWO runs (untraced/traced) and enforces exact first-ROI counter equivalence before reporting. The dataset is trace-focused, NOT new 152 ROI sweep results. Provenance: source, simulator, config and binaries SHA256 in manifest.json.

Expected outputs in out dir: summary.json, by_pc.csv, by_pc_ghr16.csv, per-workload control/roi.stats, trace/roi.stats and trace/c3_diag.trace. Completion marker: C3_P1_PC_DIAGNOSTIC_P2=PASS. The runner refuses any existing output directory and does not overwrite raw evidence.

## What the trace CAN and CANNOT establish

H1: Different prediction-time GHR16 contexts may correlate with different outcomes for the same PC. This justifies testing a separately designed HIST_TAG; it is not evidence of prospective improvement or causality.

H2: Chronological per-PC records may expose chooser=3 persisting across changing outcomes or G5 adaptation. Distinguish observations from inferred causes.

H3: High collisions, stale prediction or allocations near losses may explain part of P1 residual inefficiency. ABA SAME-TAG in-flight hazard remains unresolved and is NOT repaired by this diagnostic.

H4: P1 G0-only trace cannot measure how often G5-strong branches contain correctable errors, because it omits G0-ineligible events. No claim of G0 optimality or complete coverage.

Next gate: if data support it, implement HIST_TAG as SEPARATE, frozen PC+history indexed predictor with explicit tag, update/rollback, and logical/transient budgets. Compare full-19 under equal conditions. If still negative net correction or excessive area/timing, stop C3 and invest in other registered BPU-7 families. Original 21-profile matrix is not modified.
