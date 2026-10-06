# Little v0.52 BPU-3A — Initial Rollback Assertion Failure Analysis

Status: **TEST ASSERTION DEFECT IDENTIFIED / FIXED / RERUN REQUIRED**

Date: 2026-10-06 KST

## Observed failure

The first directed BPU-3 run terminated with:

```text
fatal: TAGE history rollback pointer mismatch:
got 2096088 expected 0
```

The directed kernel itself built correctly and retained eight static conditional branches.

## Root cause

This was **not evidence of an incorrect TAGE history rollback**.

gem5's `TAGEBase::updateGHist()` stores global history in a large circular buffer. When the initial history pointer is near the beginning of the buffer:

```text
ptGhist < number_of_new_history_bits
```

the implementation first copies the reachable history window near the end of the backing buffer and relocates the pointer to:

```text
histBufferSize - maxHist - rollbackBuffer
```

For the current configuration:

```text
saved pointer       = 0
restored pointer    = 2,096,088
```

After reversing the speculative update, the predictor contains the **same logical history**, but represented at the relocated copy. Therefore exact numeric pointer equality is not a valid rollback invariant across a rollover.

The original BPU-3 audit incorrectly asserted physical pointer identity.

## Corrected rollback invariant

BPU-3 now verifies:

1. the current pointer is either the original pointer or the single legal rollover-equivalent pointer;
2. the entire `maxHist` raw global-history window exactly matches its prediction-time snapshot;
3. path history exactly matches;
4. every tagged bank's folded index history exactly matches;
5. both folded tag histories for every tagged bank exactly match.

For S0, the raw exact comparison covers all 64 global-history bits used by the longest tagged table.

This is stronger than the original numeric-pointer check because it validates predictor semantics rather than backing-buffer placement.

## Implementation changes

`BranchInfo` now stores:

```text
savedPtGhist
savedGlobalHistWindow[maxHist]
saved path history
saved folded index histories
saved folded tag0 histories
saved folded tag1 histories
```

The history rollover safety-window constant is shared by `updateGHist()` and the BPU-3 audit so the legal relocation rule cannot silently diverge.

## Classification

```text
micro-TAGE architecture defect       NOT ESTABLISHED
gem5 rollback defect                 NOT ESTABLISHED
BPU-3 audit assertion defect         CONFIRMED
fix                                  STAGED
clean rerun                          REQUIRED
```

No BPU-3 PASS is claimed from the failed run.
