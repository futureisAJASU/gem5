# Little v0.52 BPU-6 — Selective Perceptron Seed Result

Status: **CLOSED / FAIL**

Date: 2026-10-08 KST

## Seed result

The BPU-6 standalone-direction perceptron seed passed all implementation,
storage and accounting gates but failed the architecture-value criterion.

```text
profile      vs G5 cycles   vs G7 cycles   activation   TAGE wrong   final wrong   fixes    breaks
V1             +0.55406%      +1.78942%       5.615%       137354       150316      27676    40638
W+M            +0.14051%      +1.37079%       2.977%       136729       139305      18090    20666
ALWAYS         +8.20775%      +9.53715%     100.000%       136417       363294      49344   276221
```

Net corrections:

```text
V1     = fixes - breaks = -12,962
W+M    = fixes - breaks =  -2,576
ALWAYS = fixes - breaks = -226,877
```

Thus even the most conservative W+M variant makes more correct TAGE
predictions wrong than it repairs.

## Correctness status

This is not an accounting failure.

The run passed:

```text
BPU_B6_STORAGE_GATE=PASS
BPU_B6_FINAL_ERROR_RECONCILIATION=PASS
BPU_B6_SEED_FULL19=PASS
BPU_B6_PROVENANCE=PASS
```

For every profile/workload:

```text
finalWrong == tageWrong - fixes + breaks
overrides  == fixes + breaks
```

Therefore the negative result is architectural/algorithmic under the tested
seed rather than a hidden stats inconsistency.

## Per-workload evidence

V1 degrades the dominant difficult workloads:

```text
huffbench       TAGE MPKI 15.1135 -> final 16.0088; fix 8,131 / break 10,423
picojpeg        1.9778 -> 2.4144;                 1,353 / 3,036
qrduino        19.1268 -> 20.0864;               11,943 / 14,795
sglib          10.0726 -> 11.7963;                5,079 / 9,491
slre            1.0980 -> 1.3625;                   404 / 1,138
```

The seed is therefore not failing only on low-branch-count noise.

## Why this seed is the wrong corrector semantics

The BPU-6 seed treated the perceptron as an independent direction predictor:

```text
if eligible and perceptron direction disagrees with TAGE:
    use perceptron
```

with only `abs(sum)>0` as the override margin.

That is materially simpler than established TAGE+SC integration in gem5.

### gem5 TAGE-SC-L

In `src/cpu/pred/statistical_corrector.cc`, `scPredict()` does not blindly
replace TAGE whenever the SC direction differs.

When TAGE and SC disagree, the code considers TAGE confidence and SC
`abs(lsum)`, and can keep the previous TAGE prediction when the SC score is
not sufficiently decisive.

### gem5 MPP-TAGE

In `src/cpu/pred/multiperspective_perceptron_tage.cc`, the MPP-TAGE lookup
explicitly seeds the correction sum with a vote from the previous/base
prediction:

```text
init_lsum = +22 if base prediction is taken
            -22 otherwise

init_lsum += multiperspective partial sum
```

The statistical corrector then works from this combined score.

This means the BPU-6 seed omitted a central integration idea used by the
reference implementations: **the already-trained base predictor receives an
explicit prior/chooser advantage before the auxiliary predictor may overturn
it.**

## Decision

Do not sweep entries/history/weight width yet.

Do not claim that the perceptron concept is rejected.

The rejected item is specifically:

> a 64x24x6 perceptron used as a near-unconditional replacement direction
> predictor whenever the BPU-5 gate activates.

## BPU-6A next diagnostic

Test one source-anchored integration change before any broad tuning:

```text
combined_sum =
    raw_perceptron_sum
    + (TAGE prediction ? +22 : -22)
```

The value 22 is not selected from Little-v0.52 results. It is taken directly
from gem5's MPP-TAGE integration as a diagnostic seed.

Keep unchanged:

```text
rows             64
history          24
weights          signed 6-bit
training theta   60
override margin  0 on the combined score
storage          55,336 bits total
```

Run only:

```text
V1 + TAGE prior22
W+M + TAGE prior22
```

on full-19, comparing against the already completed BPU-6 V1/W+M seeds and
G5/G7 references.

### BPU-6A decision

The prior22 integration is promising only if:

1. `fixes > breaks`;
2. finalWrong < profile-local TAGEwrong;
3. cycle geomean improves versus the corresponding BPU-6 seed;
4. no accounting/storage invariant fails.

If prior22 still gives `breaks >= fixes`, the next step is not blind prior
or threshold sweeping. The corrector target/integration semantics must be
reconsidered (e.g. explicit trust-TAGE/invert-TAGE residual learning or a
small chooser).
