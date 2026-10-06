# Little v0.52 BPU-4 A1 — Tagged-Entry Geometry Sweep Contract

Status: **METHODOLOGY FROZEN / STAGED / SERVER UNRUN**

Date: 2026-10-06 KST

## Scope

BPU-4 begins micro-TAGE geometry optimization only after BPU-3 correctness closure.

A1 changes exactly one axis:

```text
tagged entries per table = 256 / 512 / 1024
```

All other predictor/frontend controls remain fixed.

## Fixed S0 controls

```text
bimodal entries          2048
tagged tables            3
history lengths          8 / 24 / 64
tag widths               8 / 9 / 10
tagged prediction ctr    3 bits
tagged useful ctr        2 bits

conditional PC shift     1
BTB PC shift             2
indirect PC shift        1
BTB                      4096 direct-mapped proxy
RAS                      16
frontend                 F3D3
```

Frozen six-workload sweep subset:

```text
statemate
crc32
nsichneu
slre
sglib-combined
qrduino
```

## Exact persistent-state points

Under the frozen accounting convention:

```text
tagged bits = entries/table × (13 + 14 + 15)
            = entries/table × 42

fixed non-tagged state:
bimodal  = 2560 bits
history  =   80 bits
other    =   22 bits
fixed    = 2662 bits
```

Therefore:

```text
256 entries/table   13,414 bits = 1.6375 KiB
512 entries/table   24,166 bits = 2.9500 KiB
1024 entries/table  45,670 bits = 5.5740 KiB
```

The runner must verify these values from runtime stats and the emitted configuration.

## Metrics

For each workload and point, report:

```text
cycles
TAGE-internal committed-direction MPKI
persistent storage bits
cycle delta vs S0 512-entry point
```

Also report six-workload geometric-mean cycle ratios.

TournamentBP canonical-condition performance is shown only as a visibility/reference column and is not used directly in A1 knee arithmetic.

## Predeclared knee rule

Existing research-contract geomean rule:

> Select the smallest configuration for which the next larger point improves six-workload geomean cycles by less than 0.5%, unless a severe single-workload regression requires the larger point.

To remove ambiguity before A1 results, the single-workload guardrail is now frozen as:

> A smaller candidate is not selected as the knee if any frozen sweep workload is at least **2.0% slower** than the immediately next larger point.

The 2.0% threshold is a methodology choice for this research track, not a literature-derived universal constant. It is frozen before A1 results and must not be changed retrospectively without explicitly reopening the methodology.

Sequential A1 decision logic:

```text
if 256 -> 512 geomean benefit < 0.5%
and no workload makes 256 >= 2.0% slower than 512:
    A1 knee = 256

else if 512 -> 1024 geomean benefit < 0.5%
and no workload makes 512 >= 2.0% slower than 1024:
    A1 knee = 512

else:
    1024 is still an improving endpoint
    -> extend one point above 1024 before declaring a knee
```

This follows the contract rule that an improving endpoint must be extended.

## Known guardrail visibility

S0 remains worse than TournamentBP on the frozen subset by approximately +1.21852% geomean, with known large S0 regressions:

```text
sglib-combined   +7.4803%
qrduino          +2.6823%
```

These are not separate knee thresholds, but must stay visible in every A1 report so geometry tuning cannot hide a worsening hard-workload tail behind a geomean.

## Execution

```bash
bash scripts/bpu_b4_a1_tagged_entries_sweep.sh
```

Expected completion markers:

```text
BPU_B4_A1_GEOMETRY_GATE=PASS
BPU_B4_A1_STORAGE_GATE=PASS
BPU_B4_A1_KNEE_EVALUATION=PASS
BPU_B4_A1_PROVENANCE=PASS
```

The runner emits:

```text
bpu_b4_a1_tagged_entries_sweep/summary.csv
bpu_b4_a1_tagged_entries_sweep/decision.txt
bpu_b4_a1_tagged_entries_sweep/manifest.txt
```

## Change control

Do not change history lengths, tag widths, bimodal capacity, table count, BTB geometry, or backend/cache state during A1.

Do not begin A2 history-scale tuning until A1 is closed or explicitly extended according to the endpoint rule.
