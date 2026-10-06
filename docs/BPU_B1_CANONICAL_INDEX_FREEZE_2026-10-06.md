# Little v0.52 BPU-1 — RV64/RVC Indexing & Proxy-Frontend Closure

Status: **CLOSED / CANONICAL PROXY CONDITION FROZEN**

Date: 2026-10-06 KST

## Final canonical proxy condition

For all subsequent direction-predictor research until the dedicated BTB track:

```text
conditional predictor PC shift = 1
BTB PC/index shift             = 2
indirect predictor PC shift    = 1
BTB                             = 4096 entries, direct-mapped proxy
RAS                             = 16 entries
frontend                        = F3D3
```

This is an **experiment-control freeze**, not a final-silicon BTB architecture freeze.

## Closure evidence

Full 19-workload Embench replay compared:

```text
base   = conditional1 / BTB1 / indirect1
btb2   = conditional1 / BTB2 / indirect1
cond2  = conditional2 / BTB2 / indirect1
```

Results:

```text
btb2/base geomean                = 0.984936956  (-1.50630%)
btb2/base excluding nsichneu     = 0.999977942  (-0.00221%)
cond2/btb2 geomean               = 0.999824489  (-0.01755%)
BTB2 wins/losses/ties            = 4 / 1 / 14
```

The large corpus-level BTB2 benefit is almost entirely the previously isolated `nsichneu` pathology:

```text
nsichneu base    1,362,318 cycles, condIncorrect MPKI 26.4240
nsichneu BTB2    1,021,436 cycles, condIncorrect MPKI  2.2059
delta            -25.0222%
```

The prior 2×2×2 factorial proved the causal component:

```text
conditional shift2 main effect ≈ 0.000%
BTB shift2 main effect         = -25.022%
indirect shift2 main effect    = 0.000%
```

Thus the `nsichneu` event is a BTB set/index aliasing pathology, not a direction-predictor indexing effect.

## Why conditional shift1 is frozen

RVC makes PC bit1 architecturally meaningful. Once BTB indexing is held at the clean proxy condition, switching the conditional predictor from shift1 to shift2 improves 19-workload geomean cycles by only 0.01755%.

That benefit is too small to justify discarding a meaningful PC bit before the proposed micro-TAGE geometry itself is characterized.

Therefore:

```text
direction predictor indexing = shift1
```

is frozen for the BPU geometry/corrector study.

## Why proxy BTB shift2 is frozen

The historical 4K direct-mapped BTB at shift1 causes a severe workload-specific conflict pathology. BTB shift2 removes that pathology while changing the other 18 workloads by only approximately -0.00221% geomean.

Therefore:

```text
proxy BTB indexing = shift2
```

is frozen only as a clean experimental condition.

The final BTB remains OPEN and will later sweep capacity / associativity / indexing independently.

## Metric caveat

gem5's top-level `condIncorrect` is not a pure direction-predictor miss counter. It may change when BTB/target behavior changes; for example `cubic` changes its reported committed conditional MPKI when only the BTB shift changes.

Therefore BPU-2 and later direction-predictor claims must use TAGE-internal prediction/provider correctness stats in addition to top-level branch stats.

## Frozen future geometry-sweep subset

Under the corrected canonical proxy condition (TournamentBP conditional shift1 / BTB shift2 / indirect shift1), the predeclared rank rule:

```text
2 lowest + 2 median + 2 highest committed conditional-misprediction MPKI
```

selects:

```text
low:
  statemate
  crc32

median:
  nsichneu
  slre

high:
  sglib-combined
  qrduino
```

Frozen sweep subset:

```text
statemate,crc32,nsichneu,slre,sglib-combined,qrduino
```

This subset is an empirical branch-pressure spread under the canonical proxy condition. It must not be described as a pure direction-MPKI stratification because the selection metric is the top-level committed conditional-misprediction counter.

## Milestone state

```text
BPU-0 methodology contract       CLOSED
BPU-1 RV64/RVC indexing audit    CLOSED
BPU-2 micro-TAGE instrumentation NEXT
```

No frozen I-EXEC backend state was modified.
