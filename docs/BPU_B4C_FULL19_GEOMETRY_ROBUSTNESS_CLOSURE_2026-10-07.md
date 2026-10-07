# Little v0.52 BPU-4C — Full-19 Geometry Robustness Closure

Status: **CLOSED / PASS**

Date: 2026-10-07 KST

## Frozen profile set

```text
micro3-e1024   45,670 bits
G5-45K         45,736 bits
stock TAGE     65,192 bits
G7-65K         65,192 bits
micro3-e2048   88,678 bits
```

No geometry was retuned after the six-workload BPU-4B result.

## Full-19 result

```text
G5 / micro3-e1024  = -0.97128% geomean, W/L/T 14/4/1
G7 / stock TAGE    = -0.37794% geomean, W/L/T 6/9/4
G5 / stock TAGE    = +0.84597% geomean
G7 / micro3-e1024  = -2.17314% geomean
G7 / micro3-e2048  = -0.61624% geomean
stock / micro3-e2048 = -0.23920% geomean
```

## Versus Tournament canonical

```text
micro3-e1024  -1.65266% geomean ; worst huffbench +9.84536%
G5-45K        -2.60788% geomean ; worst huffbench +6.90628%
stock TAGE    -3.42488% geomean ; worst huffbench +2.86380%
G7-65K        -3.78988% geomean ; worst nsichneu +0.00989%
micro3-e2048  -3.19332% geomean ; worst huffbench +2.25332%
```

## G5 robustness

G5 remains better than its near-exact-budget micro3 comparator on the full corpus:

```text
G5 / micro3-e1024 = -0.97128%
W/L/T = 14 / 4 / 1
storage difference = +66 bits (+0.145%)
```

Largest wins:

```text
sglib-combined  -7.92032%
huffbench       -2.67565%
qrduino         -1.89849%
slre            -1.87205%
aha-mont64      -1.39027%
```

Largest losses are negligible:

```text
nsichneu        +0.01596%
statemate       +0.01459%
nettle-sha256   +0.00322%
nettle-aes      +0.00031%
crc32            0.00000%
```

Thus the six-workload G5 advantage generalizes rather than disappearing.

## G7 robustness

G7 has exactly the same persistent-state count as stock TAGE:

```text
G7 state   = 65,192 bits
stock state= 65,192 bits
```

and improves full-19 geomean by:

```text
G7 / stock = -0.37794%
```

W/L/T is 6/9/4, but the losses are extremely small:

```text
wikisort      +0.10814%
picojpeg      +0.10122%
aha-mont64    +0.02298%
minver        +0.01016%
cubic         +0.00746%
```

while the largest wins are:

```text
sglib-combined  -3.65144%
huffbench       -2.99663%
qrduino         -0.69169%
```

Therefore the negative geomean is not produced by broad regressions plus one pathological outlier. It reflects near-ties on already-easy workloads and material wins on harder workloads.

## G7 vs larger micro3-e2048

```text
G7 / micro3-e2048 = -0.61624%
G7 state          = 65,192 bits
micro3-e2048      = 88,678 bits
G7 state saving   = 26.485%
```

This is the strongest evidence that the depth-only three-table geometry was inefficient.

## Architecture interpretation

The full-19 replay confirms the BPU-4 methodology revision:

> At equal or near-equal persistent state, redistributing capacity across a richer tagged-history geometry is more efficient than making three tagged tables deeper.

No functional bug is required to explain the earlier e4096/e8192 capacity curve.

The original micro3 depth sweep remains valid as a constrained-capacity experiment but is no longer a final geometry search.

## Candidate policy after BPU-4C

Do not immediately discard G5 in favor of G7.

The two profiles form useful Pareto anchors:

```text
G5-45K:
  45,736 bits = 5.5830 KiB
  materially smaller
  full-19 -2.60788% vs Tournament
  still has a huffbench tail regression (+6.90628%)

G7-65K:
  65,192 bits = 7.9580 KiB
  full-19 -3.78988% vs Tournament
  essentially zero worst-case regression (+0.00989%)
  exact-budget improvement over stock TAGE
```

This naturally tests the project thesis:

> Can selective difficult-case correction allow the smaller G5 fast path to approach G7-class robustness without paying G7's persistent TAGE state everywhere?

Therefore BPU-5 should freeze **G5 as the compact anchor and G7 as the robust compact reference**, rather than forcing a single seed before the corrector experiment.

No further six-workload geometry tuning is authorized before the corrector study.

Native e16384 remains HOLD / obsolete for the final-geometry track.
