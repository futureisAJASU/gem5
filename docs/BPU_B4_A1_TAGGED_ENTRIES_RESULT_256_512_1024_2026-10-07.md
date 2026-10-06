# Little v0.52 BPU-4 A1 — Tagged-Entry Sweep, Initial 256/512/1024 Result

Status: **PASS / ENDPOINT EXTENSION REQUIRED**

Date: 2026-10-07 KST

## Tested axis

```text
tagged entries/table = 256 / 512 / 1024
```

All other micro-TAGE, BTB, frontend, backend, cache, and workload controls were held fixed according to the BPU-4 A1 contract.

## Results

```text
workload             e256 cyc   vs512%     MPKI   e512 cyc     MPKI  e1024 cyc   vs512%     MPKI
statemate              568771    0.000   0.0044     568771   0.0044     568760   -0.002   0.0036
crc32                 1568364    0.000   0.0432    1568364   0.0432    1568364    0.000   0.0432
nsichneu              1045074    2.308   1.1239    1021495   0.0085    1021406   -0.009   0.0049
slre                  1184120    0.330   1.7118    1180231   1.5903    1187842    0.645   1.7810
sglib-combined        1949669    5.513  26.7552    1847793  22.9871    1617309  -12.473  14.4287
qrduino               2024180    3.552  24.3647    1954753  22.0602    1888715   -3.378  19.9027
```

Geomean:

```text
e256/e512  = 1.019296934  (+1.92969%)
e1024/e512 = 0.973479046  (-2.65210%)

benefit 256 -> 512   = +1.89316%
benefit 512 -> 1024  = +2.65210%
```

Per-workload next-larger guardrail:

```text
max e256 regression vs e512   = +5.51339%
max e512 regression vs e1024  = +14.25108%
```

Therefore neither 256 nor 512 satisfies the predeclared knee conditions.

## Storage

```text
256 entries/table    13,414 bits = 1.6375 KiB
512 entries/table    24,166 bits = 2.9500 KiB
1024 entries/table   45,670 bits = 5.5750 KiB
```

## Tournament reference visibility

This comparison is informational only and not part of A1 knee arithmetic.

```text
e256  geomean vs Tournament = +3.17172%
      worst workload        = sglib-combined +13.40606%

e512  geomean vs Tournament = +1.21852%
      worst workload        = sglib-combined +7.48025%

e1024 geomean vs Tournament = -1.46590%
      worst workload        = nsichneu -0.00294%
```

The 1024-entry point therefore crosses the canonical TournamentBP proxy on the six-workload geometric mean and, in this frozen subset, has no material positive worst-workload regression versus TournamentBP.

This is a useful intermediate result but is not yet the tagged-entry knee.

## Interpretation

The S0 512-entry geometry was not near the tagged-entry knee under this workload subset.

The improvement from 512 to 1024 is both:

- much larger than the 0.5% geomean knee threshold; and
- large on specific hard workloads, especially:
  - `sglib-combined`: -12.473% cycles relative to e512;
  - `qrduino`: -3.378% cycles relative to e512.

The tagged-entry capacity axis therefore remains performance-sensitive at 1024.

`slre` is a counterexample to monotonicity: e1024 is +0.645% slower than e512 and has higher internal TAGE MPKI. This is below the 2.0% guardrail, but it confirms that the larger table is not uniformly better workload-by-workload.

## Decision

Per the predeclared endpoint rule:

```text
BPU_B4_A1_DECISION=EXTEND_ABOVE_1024_REQUIRED
```

The next and only currently authorized extension point is:

```text
2048 tagged entries/table
```

All other axes remain frozen.

Exact 2048 persistent state:

```text
tagged bits = 2048 × 42 = 86,016 bits
fixed state = 2,662 bits
total       = 88,678 bits
            = 10.8250 KiB
```

The extension runner is:

```bash
bash scripts/bpu_b4_a1_extend_2048.sh
```

It reuses the already-generated 1024-point evidence and runs only six new 2048-entry ROI experiments.

If 1024 -> 2048 improves geomean cycles by <0.5% and no workload makes 1024 >=2.0% slower than 2048, freeze 1024 as the A1 knee.

Otherwise, the endpoint remains improving and the contract requires another upward extension before the tagged-entry axis can close.
