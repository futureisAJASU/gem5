# Little v0.52 BPU-4B — Budget-Normalized Geometry Result

Status: **PASS / SIX-WORKLOAD RESULT / FULL-19 REQUIRED**

Date: 2026-10-07 KST

## Frozen profiles

### micro3-45K reference
```text
state       45,670 bits = 5.5750 KiB
base        2048
tagged      3 x 1024
histories   8 / 24 / 64
tags        8 / 9 / 10
```

### G5-45K
```text
state       45,736 bits = 5.5830 KiB
delta       +66 bits (+0.145%) vs micro3-45K
base        2048
tagged      5
histories   5 / 11 / 25 / 58 / 130
tags        8 / 8 / 9 / 10 / 10
entries     512 / 512 / 1024 / 512 / 512
```

### stock TAGE-65K
```text
state       65,192 bits = 7.9580 KiB
base        8192
tagged      7 x 512
histories   5 / 9 / 15 / 25 / 44 / 76 / 130
```

### G7-65K
```text
state       65,192 bits = 7.9580 KiB
delta       0 bits vs stock TAGE
base        2048
tagged      7
histories   5 / 9 / 15 / 25 / 44 / 76 / 130
entries     512 / 512 / 512 / 1024 / 512 / 512 / 512
```

### micro3-89K reference
```text
state       88,678 bits = 10.8250 KiB
base        2048
tagged      3 x 2048
histories   8 / 24 / 64
```

## Six-workload result

```text
workload               m3-45K     G5-45K   stock65K     G7-65K     m3-89K
statemate              568760     568843     568765     568798     568760
crc32                 1568364    1568364    1568364    1568364    1568364
nsichneu              1021406    1021569    1021491    1021537    1021393
slre                  1187842    1165605    1166215    1166200    1182529
sglib-combined        1617309    1489213    1363982    1314177    1392699
qrduino               1888715    1852858    1804416    1791935    1809621
```

Geomean ratios:

```text
G5 / micro3-45K     = -1.98464%
G7 / stock65K       = -0.73145%
G5 / stock65K       = +1.91854%
G7 / micro3-45K     = -4.53314%
G7 / micro3-89K     = -1.34999%
```

## Workload-local evidence

G5 vs same-budget micro3-45K:

```text
statemate        +0.0146%
crc32             0.0000%
nsichneu         +0.0160%
slre             -1.8721%
sglib-combined   -7.9203%
qrduino          -1.8985%
```

G7 vs exact-same-budget stock TAGE:

```text
statemate        +0.0058%
crc32             0.0000%
nsichneu         +0.0045%
slre             -0.0013%
sglib-combined   -3.6514%
qrduino          -0.6917%
```

G7 vs larger micro3-89K:

```text
statemate        +0.0067%
crc32             0.0000%
nsichneu         +0.0141%
slre             -1.3809%
sglib-combined   -5.6381%
qrduino          -0.9773%
```

## Internal TAGE MPKI

```text
workload              G5 MPKI    G7 MPKI
statemate              0.0102     0.0066
crc32                  0.0432     0.0432
nsichneu               0.0134     0.0116
slre                   1.0965     1.0817
sglib-combined        10.1754     4.2241
qrduino               18.8341    16.9983
```

## Interpretation

The principal BPU-4 methodology hypothesis is experimentally confirmed on the frozen six-workload subset:

> At fixed or near-fixed persistent state, increasing tagged-component/history diversity is substantially more efficient than increasing only the depth of three frozen tagged tables.

The evidence is strongest because both comparisons are budget controlled:

- G5 is only 66 bits (+0.145%) larger than micro3-45K yet improves geomean cycles by 1.98464%.
- G7 has exactly the same persistent-state count as stock TAGE yet improves geomean cycles by 0.73145%.
- G7 also beats the much larger micro3-89K by 1.34999% while using 26.485% less persistent state.

This confirms that the earlier depth-only curve was partly compensating for insufficient table/history diversity.

## Important scope limit

The six-workload result is not enough to freeze G5 or G7 as the final Little-v0.52 TAGE geometry.

The six workloads were preselected for branch-pressure coverage before these results, which protects against direct cherry-picking. However, they remain a small embedded subset and the largest gains are concentrated in sglib-combined and qrduino.

No additional geometry tuning is allowed on these six results before full-corpus replay.

## Next gate

BPU-4C full-19 robustness replay must compare, without retuning:

```text
micro3-45K
G5-45K
stock TAGE-65K
G7-65K
micro3-89K
```

under the same canonical frontend condition.

Only after full-19 results may the compact Pareto candidate set be reduced or a new budget-normalized geometry matrix be defined.

Native e16384 remains HOLD.
