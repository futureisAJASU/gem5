# Little v0.52 BPU-5C — Hard-PC Trigger-Efficiency Audit

Status: **CLOSED / PASS / PC-MEMBERSHIP-ONLY WAKE REJECTED**

Date: 2026-10-08 KST

## Method

BPU-5C reused the exact BPU-5B all-commit traces with no new simulation.

Training remained the chronological first half and evaluation the held-out
second half.

Three first-half strong-PC ranking signals were compared:

```text
COUNT  = strong wrong count
RATE   = strong wrong / strong accesses
WILSON = 95% Wilson lower bound of strong misprediction rate
```

For K=8/16/32/64, the trigger remained:

```text
weak-or-medium confidence
OR
(strong confidence AND PC in learned set)
```

## Aggregate held-out results

```text
policy   K   activation   error coverage   strong coverage   trigger err   enrich
COUNT    8     32.596%       77.708%          71.434%          5.753%      2.384x
COUNT   16     46.335%       88.385%          85.115%          4.603%      1.908x
COUNT   32     51.331%       95.245%          93.906%          4.478%      1.855x
COUNT   64     56.109%       99.371%          99.194%          4.274%      1.771x

RATE     8     20.145%       45.793%          30.536%          5.486%      2.273x
RATE    16     32.406%       54.402%          41.568%          4.051%      1.679x
RATE    32     41.222%       79.311%          73.487%          4.643%      1.924x
RATE    64     50.126%       91.129%          88.632%          4.387%      1.818x

WILSON   8     21.938%       56.609%          44.396%          6.227%      2.580x
WILSON  16     34.343%       74.079%          66.783%          5.205%      2.157x
WILSON  32     42.465%       86.009%          82.071%          4.888%      2.025x
WILSON  64     50.978%       93.404%          91.547%          4.421%      1.832x
```

For context, the BPU-5B K=0 weak+medium-only baseline was:

```text
activation     = 2.421%
error coverage = 21.964%
trigger error  = 21.895%
enrichment     = 9.073x
```

## Interpretation

RATE and WILSON improve the COUNT failure mode but do not recover the intended
selectivity.

WILSON K=8 is the best compact member of the tested PC-membership family in
coverage/enrichment terms, but waking the corrector for 21.938% of all
held-out conditional branches is still too expensive for the intended
selective-complexity design.

The problem is structural:

> A PC can be a recurrent source of strong-confidence misses while still
> being correct on a very large majority of its dynamic executions.

Thus static PC membership alone is too coarse a wake condition.

## Concrete counterexamples

Several workloads retain pathological activation even after RATE/WILSON:

```text
crc32, K=8:
  all policies activation = 100.000%
  trigger error rate       = 0.099%

st, K=8:
  all policies activation = 99.411%
  trigger error rate       = 0.022%

nbody:
  all tested policies/K activate 36.958%
  held-out error coverage = 0%

nsichneu:
  activation ~= 6.6%
  held-out error coverage = 0%
```

These cases prove that a static learned-PC set by itself cannot satisfy both
coverage and activation goals.

## What remains valid

BPU-5A/B findings remain valid:

- strong errors are concentrated by static PC;
- recurrence persists across time;
- a learned difficulty signal can identify useful branch identities.

The rejected statement is narrower:

> PC membership by itself is sufficient to wake the perceptron.

It is not.

## Next gate — BPU-5D prediction-time feature conjunction

Reuse the same all-commit traces. No simulation rerun.

The next question is whether a learned hard-PC identity can be combined with
a cheap prediction-time ambiguity feature to avoid waking on already-correct
executions of a hot branch.

Predeclared available features from prediction-time metadata:

```text
ALT_DISAGREE:
  selected TAGE prediction != alternate prediction

LOW_STRONG:
  providerConfidence == STRONG
  AND providerStrength == 5
```

For a 3-bit signed TAGE counter, strong strengths are 5 or 7; strength 5 is
the lower strong-confidence magnitude.

Use the WILSON first-half learned-PC ranking and test K=8/16/32/64 with:

```text
A: W+M only                                  baseline
B: W+M OR hard-PC                            BPU-5C reference
C: W+M OR (hard-PC AND ALT_DISAGREE)
D: W+M OR (hard-PC AND LOW_STRONG)
E: W+M OR (hard-PC AND (ALT_DISAGREE OR LOW_STRONG))
F: W+M OR (strong AND ALT_DISAGREE)          no-PC diagnostic
G: W+M OR (strong AND LOW_STRONG)            no-PC diagnostic
```

Evaluate only the held-out second half and report activation, total/strong
error coverage, trigger error rate and enrichment.

No final gate is frozen before BPU-5D.
