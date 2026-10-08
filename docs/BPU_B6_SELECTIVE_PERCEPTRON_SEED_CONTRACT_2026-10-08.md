# Little v0.52 BPU-6 — Selective Perceptron Seed Contract

Status: **IMPLEMENTATION STAGED / BUILD+RUN PENDING**

Date: 2026-10-08 KST

## Purpose

BPU-6 is the first real corrector experiment after BPU-5D froze the
prediction-time candidate gate.

It tests whether a small perceptron can convert the BPU-5D **reachable TAGE
errors** into actual net corrections without excessive correct-to-wrong
overrides.

This milestone does not tune history length, row count, weight width or
override margin yet.

## Frozen G5 base

```text
G5 TAGE state = 45,736 bits = 5.5830 KiB
tagged tables = 5
histories     = 5 / 11 / 25 / 58 / 130
```

## Perceptron seed

```text
rows           = 64
PC index       = (PC >> instShiftAmt) & 63
history bits   = 24
bias weights   = 1 per row
weights/row    = 25
weight width   = signed 6-bit
weight range   = [-32, +31]
weight state   = 64 * 25 * 6 = 9,600 bits = 1.171875 KiB

combined state = 45,736 + 9,600
               = 55,336 bits
               = 6.7549 KiB
```

The C++ simulation stores weights in int8_t containers but exact architecture
accounting charges only the configured 6 logical bits per weight.

## History semantics

The perceptron does **not** create a second speculative-history structure.

At prediction time it consumes the most recent 24 bits of the already
validated TAGE speculative global-history stream:

```text
threadHistory[tid].globalHist[ptGhist + 0 .. 23]
```

Those 24 bits are snapshotted into the branch's prediction-time metadata.

Consequences:

- perceptron feature history follows the same speculation and rollback source
  already closed by BPU-3;
- no extra persistent history bits are charged;
- no additional perceptron rollback machinery is required;
- training uses the exact prediction-time feature vector even if younger or
  older branches later mutate global history.

## Perceptron sum

For row `r`:

```text
y = bias[r] + sum_i(weight[r][i] * x_i)

x_i = +1 if history bit i is taken/1
      -1 if history bit i is not-taken/0

perceptron prediction = taken iff y >= 0
```

Initial weights are zero.

## Training rule

Training occurs only for branches on which the configured gate activated the
perceptron.

The seed uses:

```text
train if:
  perceptron prediction is wrong
  OR
  abs(y) <= 60
```

The default threshold 60 is the rounded history-24 instance of the classic
perceptron training rule `theta ~= 1.93*h + 14`.

Weights update by +/-1 with signed 6-bit saturation.

Reference:
Daniel A. Jimenez and Calvin Lin,
"Dynamic Branch Prediction with Perceptrons," HPCA 2001.

The threshold remains a BPU-6 seed, not a final freeze.

## Override rule

The seed uses:

```text
override TAGE iff:
  gate active
  AND perceptron direction != TAGE direction
  AND abs(y) > 0
```

Therefore the zero-initialized perceptron cannot override on y=0 before it has
learned any signal.

A nonzero override-margin sweep is deferred until the seed establishes that
the corrector has positive net value.

## Gate variants

Three otherwise identical predictors are evaluated:

```text
ALWAYS:
  activate on every committed conditional prediction

WM:
  WEAK OR MEDIUM TAGE confidence

V1:
  WEAK
  OR MEDIUM
  OR providerStrength == 5
```

V1 is the BPU-5D candidate gate.

## TAGE/corrector separation

The base TAGE prediction is retained in `tagePred`.
The corrected frontend direction is stored separately in `finalPred`.

TAGE table allocation/training continues to use its own `tagePred`.
This prevents the corrector from silently redefining TAGE's internal learning
semantics.

The processor/frontend receives `finalPred`, so corrected predictions affect
the real speculative path and measured cycles.

## Required runtime invariants

For every workload/profile:

```text
finalCorrect + finalWrong
  == committedConditionalPredictions

overrides
  == wouldFix + wouldBreak

finalWrong
  == tageWrong - wouldFix + wouldBreak

overrides <= disagreements

trainings <= eligible predictions

ALWAYS eligible predictions
  == committedConditionalPredictions

perceptronStorageBits == 9,600

combined storageBits == 55,336
```

These gates distinguish actual corrector benefit from stats/accounting errors.

## Full-19 experiment

Runner:

```text
scripts/bpu_b6_perceptron_seed_full19.sh
```

New simulations:

```text
3 gate variants * 19 Embench workloads = 57 ROI
```

Existing BPU-4C G5 and G7 runs are reused as references.

Primary outputs:

- cycle geomean vs G5;
- cycle geomean vs G7;
- activation rate;
- base-TAGE wrongs;
- final corrected wrongs;
- fixes;
- breaks;
- final direction MPKI.

## Decision rule

BPU-6 does not require V1 to be the best gate a priori.

The seed is successful only if a selective variant demonstrates:

1. positive net direction correction: `fixes > breaks`;
2. final wrong count below G5 TAGE-only;
3. cycle benefit or a clearly explainable neutral-cycle result;
4. materially lower activation than ALWAYS;
5. no correctness/accounting gate failure.

If all selective variants have `breaks >= fixes`, the perceptron seed itself
must be revisited before any parameter sweep.
