# Little v0.52 BPU-7 C3 PC_BIAS — Reviewer Handoff v0.1 (2026-10-08)

**Status: C3 PC_BIAS FINITE-STATE ENGINE + G5 SHADOW INTEGRATION IMPLEMENTED; INTEGRATION BUILD/ROI AND M1 FUNCTIONALITY NOT YET PROVEN.**
This is **one candidate**, not all C-family implementations. Branch: `little-v052-bpu7-c3-pcbias-p0`, parent `little-v052-bpu`.
**Production G5/G7 preserved**: work is isolated on a review branch and the C3 SimObject flag defaults to False.

## 1. What we are learning

Current G5 = 5 tagged-history TAGE tables, 45,736 logical persistent bits. A branch direction is predicted from G5, with `tagePred` and provider confidence stored **at prediction time**. C3 tests whether a tiny *PC-indexed residual exception table* can learn the **specific branch PCs for which flipping G5 is often beneficial**. It does *not* predict taken/not-taken independently.

**C3 PC_BIAS is NOT C3 HIST_TAG.** No extra local-history/GHR context exists in this variant: only shifted branch PC, table row, truncated PC tag and a signed inversion-benefit score. HIST_TAG must be separately implemented and reviewed later.

**Important prior-art boundary:** This is a small tagged exception/corrector-style implementation informed by earlier tagged branch-predictor work and the existing G5 TAGE/perceptron metadata paths, *not* a demonstrated novel predictive concept.

## 2. Concrete first-seed geometry and state accounting

- Direct-mapped rows: E64/E128/E256 (CLI `--bp-type tage5-c3-pcbias-shadow-e64`, `e128`, or `e256`).
- Each row is logically **valid(1), PC tag(10), signed residual score(3), collision protection(2) = 16 bits**.
- Auxiliary budgets: E64=1,024 bits, E128=2,048 bits, E256=4,096 bits; G5+aux = **46,760 / 47,784 / 49,832 bits**. This excludes separately tracked in-flight branch metadata and physical SRAM width/banking overhead; *do not* claim RTL area or power from this number.
- Branch identity used for index: `key = PC >> instShiftAmt`, default RV64/RVC `instShiftAmt=1`.
- Table index: `key & (entries-1)`.
- Truncated tag: `(key >> log2(entries)) & ((1<<10)-1)`. High-PC aliases beyond these ten tag bits remain possible; this is a bounded hardware design, not a perfect set.
- `score` signed three-bit value saturates at **[-4,+3]**. Reset row invalid, score=0, protection=0.
- The two bits originally named `replacement_bits` are provisionally interpreted as **0..3 saturating collision-protection age** rather than a way-selector in this direct-mapped structure. This implementation choice needs human sign-off before any frozen comparison.

## 3. Exact corrector state machine (reader-oriented)

Prediction (read-only):
1. Obtain G5 confidence and provider-strength only **after** G5 lookup; `G0 = (WEAK or MEDIUM or strength==5)`. Hence C3 cannot use G0 to avoid the same G5 SRAM read.
2. If G0 false, **do not touch** C3 array and do not train that branch later.
3. If G0 true, read ONE indexed C3 row; if invalid or tag mismatch, score is treated as 0, never request a flip.
4. On matching valid tag only: `G1 = (score >= +2)`. A positive score represents recurring historical **G5 errors**, i.e. a benefit for inversion. For zero or negative score, do not flip. Save eligibility, tag hit, score and hypothetical flip request in the branch's original prediction metadata; do not re-read table at commit to invent what it predicted.

Commit of an eligible conditional branch:
1. Compare **saved G5 prediction** against the actual retired outcome. Never use C3's hypothetical direction as the training label.
2. If the current indexed row has the saved PC tag, increment score by +1 when G5 was wrong, decrement by -1 when G5 was correct; clip [-4,+3].
3. On matching row, also increment protection (up to 3) for G5 wrong or decrement it (down to 0) for G5 correct.
4. If row is empty, or is a different tag with **zero protection**, allocate the saved tag; initialize score to +1 on G5 wrong or -1 on G5 correct, with protection 1 or 0 respectively.
5. If a conflicting tag is present **and protection>0**, decrement protection and skip writing a new tag. The miss never inherits another PC's score.
6. Squashed/uncommitted branches **do not train C3**. C3 has no independent speculative history and therefore no C3 counter rollback; original G5 speculative history restoration still applies.

**Training includes eligible predictions with G1 false.** Otherwise a new entry could never grow from score +1 to +2 and would never become useful.

## 4. The key distinction: real C++ predictor but SHADOW ONLY

The C3 class has actual finite memory, lookup, tag collision, saturation and commit learning.
However, `tagePredict()` only records `c3PcBiasLookup`; it **does not alter** `bi->finalPred`.
Therefore:
- This branch uses ordinary G5 fetch direction and G5 speculative path. No incorrect claim that a same-cycle override constitutes an implementable N+1 correction.
- `c3PcBiasWouldFix` and `c3PcBiasWouldBreak` are **same-path hypothetical** correction labels from the actual G5 path, not measured speedups.
- `c3PcBiasWouldFlip = c3PcBiasWouldFix + c3PcBiasWouldBreak` over committed conditionals.
- `finalConditionalWrong` still equals `committedConditionalWrong` in C3-only shadow mode.
- C3 shadow increases logical predictor storage and modeled auxiliary accesses, but its runtime cycles cannot establish accuracy/speed tradeoff of a *functional* C3+G5 M1 predictor.
- **No C3 entry is an M1-tested, RUN_READY 21-profile BPU-7 configuration.** Promotion requires actual redirect, squash/replay and cycle penalty in the frontend, plus baseline equivalence and actual full-19 ROI.

## 5. Instrumentation and consistency checks

Source: `src/cpu/pred/tage_base.cc` stats:
`c3PcBiasBankReads` (dynamic predicted-path and wrong-path eligible lookups),
`c3PcBiasEligibleCommitted`,
`c3PcBiasTagHits`,
`c3PcBiasWouldFlip`,
`c3PcBiasWouldFix`,
`c3PcBiasWouldBreak`,
`c3PcBiasTrainWrites`,
`c3PcBiasAllocations`,
`c3PcBiasEvictions`,
`c3PcBiasCollisionBlocked`,
`c3PcBiasStorageBits` (a Value stat, survives ROI stats reset).

Predeclared post-run invariants:
- `c3PcBiasWouldFlip = c3PcBiasWouldFix + c3PcBiasWouldBreak`
- `c3PcBiasTagHits <= c3PcBiasEligibleCommitted`
- `c3PcBiasWouldFlip <= c3PcBiasTagHits`
- `c3PcBiasTrainWrites + c3PcBiasCollisionBlocked = c3PcBiasEligibleCommitted` (given every eligible branch is processed by one C3 commit)
- `c3PcBiasAllocations <= c3PcBiasTrainWrites` and `c3PcBiasEvictions <= c3PcBiasAllocations`
- E128 `storageBits = 47,784` and `c3PcBiasStorageBits=2,048`
- Within pure C3 shadow, `finalConditionalWrong = committedConditionalWrong`
- G5-only and G7-only show `c3PcBiasStorageBits=0` and zero C3 activity.

## 6. Current evidence and limitations

Source files:
- `src/cpu/pred/little_c3_pc_bias.hh`: self-contained finite-state corrector.
- `src/cpu/pred/tage_base.{hh,cc}`: G5 prediction-time metadata, commit-only training, shadow stats and state cost.
- `src/cpu/pred/BranchPredictor.py`: opt-in C3 SimObject (no default behavioral change).
- `configs/02_little_v052_rv64_proxy.py`: exact E64/E128/E256 experimental CLI IDs.
- `tests/bpu7/c3_pc_bias_directed.cc`: direct C++ tests against the production header.
- `.github/workflows/bpu7-c3-pcbias-p0.yaml`: GCC -Werror, directed tests, Python syntax and source shadow gate.

**Evidence available at handoff**: C3 header compiled, directed C++ tests passed, Python config syntax passed, source guard showing no G5 prediction override passed, CI run linked in GitHub. **Full gem5/RISCV binary build, integrated RTL/gem5 ROI, shadow stats extraction, M1 redirect, full-19 and ASIC PPA are NOT established by this test.** Do not change matrix status from PRE_FREEZE.

## 7. Review decisions requested before proceeding to HIST_TAG or other candidates

1. Confirm or replace the *two-bit collision-protection* semantic choice; do not silently imply a 2-way replacement policy.
2. Confirm signed +1/-1 **benefit-of-flipping-G5** training and G1 score>=2; these are pre-result engineering choices, not optimized values.
3. Confirm only G0-eligible branches are trained. This reduces activity but may slow learning when confidence fluctuates.
4. Confirm C3 PC-tag index scheme with compressed instruction shift 1, and whether to add a later rehash axis (separate from this frozen first seed).
5. Keep SHADOW diagnostic until a real M1 frontend correction has a complete test and energy/timing cost.

**Do not merge C3 into the frozen G5/G7 evaluation branch or run B7-1 399 ROI before review and M1 readiness.**
