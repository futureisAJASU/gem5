# Little v0.52 BPU-5D — Prediction-Time Feature Conjunction Closure

Status: **CLOSED / PASS**

Date: 2026-10-08 KST

## Held-out aggregate

BPU-5D reused the exact BPU-5B all-commit traces. Hard-PC ranking remained
first-half WILSON and evaluation remained second-half only.

```text
mode                       activation   error coverage   strong coverage   trig error   enrich
W+M only                     2.421%        21.964%          0.000%          21.895%      9.073x

hard-PC K8                  21.938%        56.609%         44.396%           6.227%      2.580x
hard-PC K16                 34.343%        74.079%         66.783%           5.205%      2.157x

hard-PC && ALT K8            7.365%        32.821%         13.913%          10.754%      4.457x
hard-PC && ALT K16           8.893%        38.381%         21.038%          10.415%      4.316x

hard-PC && LOW_STRONG K8     3.364%        31.436%         12.138%          22.550%      9.345x
hard-PC && LOW_STRONG K16    3.811%        36.444%         18.556%          23.077%      9.563x
hard-PC && LOW_STRONG K32    4.359%        38.751%         21.511%          21.452%      8.890x
hard-PC && LOW_STRONG K64    4.739%        39.864%         22.938%          20.297%      8.411x

hard-PC && (ALT OR LOW) K8   8.011%        39.028%         21.866%          11.756%      4.872x
hard-PC && (ALT OR LOW) K16  9.833%        47.679%         32.953%          11.702%      4.849x

ALT no-PC                   16.677%        43.538%         27.646%           6.300%      2.611x

LOW_STRONG no-PC             4.923%        40.443%         23.680%          19.825%      8.216x
```

## Decision

The best architecture-relevant result is the **no-PC LOW_STRONG extension**.

```text
baseline W+M:
  activation = 2.421%
  coverage   = 21.964%
  enrichment = 9.073x

W+M + LOW_STRONG:
  activation = 4.923%
  coverage   = 40.443%
  enrichment = 8.216x
```

It approximately doubles the wake rate but nearly doubles reachable TAGE-error
coverage while preserving very high error enrichment.

A learned hard-PC table is not justified at this stage.

The strongest low-activation hard-PC conjunction, WILSON hard-PC &&
LOW_STRONG, reaches:

```text
K16:
  activation = 3.811%
  coverage   = 36.444%
  enrichment = 9.563x
```

This saves only 1.112 percentage points of activation relative to the
no-PC LOW_STRONG gate while losing 3.999 percentage points of total error
coverage and requiring a learned-PC structure, tags/replacement/training and
additional prediction-time lookup.

That trade is not attractive for the Little-v0.52 selective-complexity goal.

## Gate interpretation

For the current TAGE counters:

```text
signed 3-bit TAGE strength magnitudes:
  1 = weak
  3 = medium
  5 = lower strong
  7 = saturated strong
```

The candidate gate is therefore:

```text
wake corrector if:
  provider confidence is WEAK
  OR provider confidence is MEDIUM
  OR providerStrength == 5
```

Bimodal strong predictions are not accidentally included: the 2-bit bimodal
provider maps to strengths 1 or 3, never 5.

Equivalently, this is:

> correct weak and medium predictions plus the less-saturated half of strong
> TAGE predictions; leave saturated-strong TAGE and strong bimodal predictions
> on the compact TAGE fast path.

## Rejected feature paths

```text
hard-PC membership alone:
  rejected by BPU-5B/C due excessive activation.

ALT_DISAGREE without PC:
  16.677% activation for 43.538% coverage; too active.

hard-PC && ALT_DISAGREE:
  lower activation than hard-PC alone but poor coverage/enrichment relative
  to LOW_STRONG.

hard-PC learned table:
  retained only as a documented negative result, not a final structure.
```

## BPU-5 freeze

The prediction-time **candidate gate** entering the perceptron study is frozen
as:

```text
SELECTIVE_GATE_V1 =
  WEAK
  OR MEDIUM
  OR TAGE_LOW_STRONG(strength == 5)
```

This freeze is a gate for BPU-6 perceptron evaluation, not a final silicon
freeze. It may be rejected if the actual perceptron fails to provide useful
corrections at the measured activation rate.

## Next milestone — BPU-6

Implement the perceptron corrector and compare:

1. TAGE-only G5;
2. always-on perceptron;
3. SELECTIVE_GATE_V1 perceptron;
4. W+M-only perceptron ablation.

Initial seed remains the predeclared conceptual point:

```text
entries       = 64
history       = 24
weights       = signed 6-bit
bias          = 1 weight
raw weights   = 64 * 25 * 6 = 9,600 bits = 1.171875 KiB
```

The perceptron must train from committed actual outcomes and use
prediction-time speculative history/metadata with exact rollback provenance.
Override threshold/learning threshold is not frozen by this document.
