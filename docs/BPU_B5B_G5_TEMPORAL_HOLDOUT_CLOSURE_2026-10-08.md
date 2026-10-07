# Little v0.52 BPU-5B — G5 Temporal Hard-PC Holdout

Status: **CLOSED / PASS / RAW-COUNT HARD-PC GATE REJECTED**

Date: 2026-10-08 KST

## Method

Every committed conditional G5 event was traced and exactly reconciled with
predictor statistics.

For each workload:

1. chronological first half = training;
2. rank strong-confidence wrong PCs by first-half wrong count;
3. freeze top K for K=8/16/32/64;
4. evaluate only the chronological second half;
5. trigger on weak/medium confidence OR a strong-confidence learned PC.

K=0 is the weak+medium confidence-only baseline.

## Aggregate held-out result

```text
K    persistence   activation   error coverage   strong coverage  trigger err  enrich
0       0.000%       2.421%        21.964%          0.000%         21.895%     9.073x
8      53.659%      32.560%        77.708%         71.434%          5.759%     2.387x
16     58.549%      46.326%        88.386%         85.117%          4.604%     1.908x
32     64.727%      51.310%        95.254%         93.919%          4.480%     1.856x
64     69.372%      56.080%        99.349%         99.166%          4.275%     1.772x
```

All-event reconciliation and temporal-holdout gates passed.

## What BPU-5B proves

The hard-PC recurrence observed in BPU-5A is real and temporally persistent.

Even top-8 PCs learned only from the first half recover 71.434% of
second-half strong errors and 77.708% of all errors.

Thus strong TAGE errors are not merely a retrospective oracle artifact.

## Why the raw-count hard-PC gate is rejected

The activation cost is far too high for the intended selective-complexity
design.

Relative to W+M-only:

```text
K=8:
  activation   2.421% -> 32.560%
  coverage    21.964% -> 77.708%

K=16:
  activation -> 46.326%

K=32:
  activation -> 51.310%

K=64:
  activation -> 56.080%
```

At K=8, only 5.759% of triggered held-out events are TAGE errors. More than
94% of corrector activations would occur on already-correct TAGE predictions.

Several workloads expose the failure mode directly:

```text
crc32 K=8:
  activation = 100.000%
  trigger error rate = 0.099%

edn K=16:
  activation = 99.926%
  trigger error rate = 0.121%

st K=8:
  activation = 99.411%
  trigger error rate = 0.022%
```

Therefore ranking PCs by absolute strong-wrong count preferentially selects
very hot branches whose absolute miss count is high even when their
misprediction probability is tiny.

That is not the desired definition of a hardware "difficult branch".

## Architecture consequence

BPU-5A's conclusion remains valid:

> strong errors are concentrated on recurring PCs.

But BPU-5B refines it:

> PC membership alone is too coarse. The learned difficulty signal must
> account for the frequency of correct strong predictions as well as wrong
> strong predictions.

The raw-count top-K trigger is therefore **REJECTED** as the final activation
policy.

W+M confidence-only remains the high-efficiency baseline:

```text
activation = 2.421%
error coverage = 21.964%
trigger enrichment = 9.073x
```

## Next gate — BPU-5C no-rerun trigger-efficiency audit

Reuse the existing BPU-5B all-commit traces.

For each first-half static PC, collect:

```text
strong accesses A
strong wrongs   W
strong corrects C = A-W
```

Compare predeclared ranking signals:

1. COUNT: W (existing BPU-5B baseline);
2. RATE: W/A;
3. WILSON: 95% Wilson lower confidence bound of W/A.

RATE tests the direct error-per-activation objective.
WILSON penalizes tiny-sample branches and tests sustained difficulty.

Evaluate K=8/16/32/64 only on the already-held-out second half and report
activation, total-error coverage, strong-error coverage, trigger error rate,
enrichment and temporal persistence.

This is still an ideal fully-associative learned-set analysis, not a hardware
table. No final policy is frozen from BPU-5C alone.
