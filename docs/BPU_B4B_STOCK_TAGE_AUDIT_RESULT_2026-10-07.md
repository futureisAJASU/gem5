# Little v0.52 BPU-4B — Stock gem5 TAGE Audit Result

Status: **CLOSED / PASS / METHODOLOGY HYPOTHESIS CONFIRMED**

Date: 2026-10-07 KST

## Result

Stock gem5 TAGE was run under the same canonical frontend condition as the Little micro-TAGE sweep.

Exact stock geometry:

```text
base bimodal        = 8192 entries
tagged tables       = 7
entries/tagged      = 512 each
minHist/maxHist     = 5 / 130
generated histories = 5 / 9 / 15 / 25 / 44 / 76 / 130
tag widths          = 9 / 9 / 10 / 10 / 11 / 11 / 12
persistent state    = 65,192 bits = 7.9580 KiB
```

Frozen six-workload result:

```text
workload            Tournament   micro1024   stockTAGE   micro2048  stock MPKI
statemate               568927      568760      568765      568760      0.0044
crc32                  1568427     1568364     1568364     1568364      0.0432
nsichneu               1021436     1021406     1021491     1021393      0.0067
slre                   1210933     1187842     1166215     1182529      1.0821
sglib-combined         1719193     1617309     1363982     1392699      5.9259
qrduino                1903690     1888715     1804416     1809621     17.4424
```

Geomean:

```text
stockTAGE / Tournament  = -5.23946%
stockTAGE / micro1024   = -3.82970%
stockTAGE / micro2048   = -0.62310%
```

Equivalent reverse ratios:

```text
micro1024 / stockTAGE = +3.98221%
micro2048 / stockTAGE = +0.62700%
```

## Storage efficiency

```text
micro1024  = 45,670 bits = 5.5750 KiB
stockTAGE  = 65,192 bits = 7.9580 KiB
micro2048  = 88,678 bits = 10.8250 KiB
```

Stock TAGE uses:

```text
26.485% less persistent state than micro2048
```

while improving six-workload geomean cycles by:

```text
0.62310%
```

Stock-vs-micro2048 workload deltas:

```text
statemate        +0.00088%
crc32             0.00000%
nsichneu          +0.00959%
slre              -1.37959%
sglib-combined    -2.06197%
qrduino           -0.28763%
```

Thus the smaller stock predictor is essentially tied on the already-easy workloads and wins materially on the hard/history-sensitive workloads.

## Interpretation

This result directly supports the BPU-4 methodology audit.

The completed BPU-4A depth sweep proved that the frozen three-tagged-table design suffers real capacity/alias pressure. However, the stock TAGE result shows that increasing tagged-component/history diversity can use storage more efficiently than simply making the three frozen tables deeper.

The result does **not** show that stock TAGE is the final Little-v0.52 predictor. It is a conventional reference and uses a larger bimodal base. It also does not isolate which stock-TAGE difference is responsible:

- 7 tagged components instead of 3;
- histories extending to 130 instead of 64;
- different tag widths;
- different distribution of state between base and tagged components.

Those are now the variables to study under budget normalization.

## Consequence for the original micro-TAGE seed

The original 3-table 8/24/64 seed remains a valid compact starting point and its BPU-2/BPU-3 correctness evidence remains valid.

It is no longer defensible to freeze that exact geometry before the perceptron stage.

The final compact TAGE seed may legitimately become a 5- or 7-tagged-table design if it provides a better performance-per-bit point.

This does not abandon the project thesis. The thesis is compact common-case TAGE plus selective difficult-case correction, not specifically “three tagged tables at all costs.”

## BPU-4B next question

The next experiment must be budget-normalized rather than depth-only:

```text
same/near-same bits
-> redistribute state among more tagged histories
-> compare accuracy/performance
```

Two literature-guided profiles are proposed before seeing their results:

### G5-45K: near-exact budget match to micro1024

```text
base             2048
tagged tables    5
histories        5 / 11 / 25 / 58 / 130
tag widths       8 / 8 / 9 / 10 / 10
table entries    512 / 512 / 1024 / 512 / 512
state            45,736 bits = 5.5830 KiB
micro1024 state  45,670 bits = 5.5750 KiB
difference       +66 bits (+0.145%)
```

The history sequence is the rounded geometric 5-point sequence spanning 5 to 130.

### G7-65K: exact state match to stock TAGE

```text
base             2048
tagged tables    7
histories        5 / 9 / 15 / 25 / 44 / 76 / 130
tag widths       9 / 9 / 10 / 10 / 11 / 11 / 12
table entries    512 / 512 / 512 / 1024 / 512 / 512 / 512
state            65,192 bits = 7.9580 KiB
stock state      65,192 bits = 7.9580 KiB
difference       0 bits
```

This profile reallocates exactly the 7,680 bits saved by shrinking the stock bimodal base from 8192 to 2048 into the central history-25 tagged bank (an extra 512 entries x 15 bits).

The bank selection is frozen before results; it is not chosen retrospectively.

## Scope

BPU-4A remains valid as constrained 3-table capacity sensitivity.

BPU-4B now tests whether table/history diversity dominates additional depth at fixed storage.

Native e16384 remains HOLD.
