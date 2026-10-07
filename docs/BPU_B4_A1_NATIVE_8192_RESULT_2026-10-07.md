# Little v0.52 BPU-4 A1 — Native 8192 Extension Result

Status: **PASS / PERFORMANCE AXIS STILL UNSATURATED**

Date: 2026-10-07 KST

## Result

```text
workload             e4096 cyc      MPKI   e8192 cyc   vs4096%      MPKI
statemate               568760    0.0036      568760     0.000    0.0036
crc32                  1568364    0.0432     1568364     0.000    0.0432
nsichneu               1021384    0.0040     1021373    -0.001    0.0036
slre                   1180143    1.5853     1180090    -0.004    1.5867
sglib-combined         1312995    4.0151     1261420    -3.928    2.3511
qrduino                1687203   13.8664     1510632   -10.465    8.9337
```

Geomean:

```text
e8192/e4096 = 0.975200615
            = -2.47994% cycles

benefit e4096 -> e8192 = +2.47994%
max workload penalty of e4096 vs e8192
                        = +11.68855% (qrduino)
```

Persistent state:

```text
e4096 = 174,694 bits = 21.3250 KiB
e8192 = 346,726 bits = 42.3250 KiB
growth = +98.48%
```

Tournament visibility:

```text
e8192 geomean vs Tournament = -9.01842%
worst workload              = crc32 -0.00402%
```

Decision:

```text
BPU_B4_A1_FINAL_DECISION=EXTEND_ABOVE_8192_REQUIRED
```

## Interpretation boundary

The performance-only capacity axis remains unsaturated at 8192 entries/table.

The improvement is still concentrated in the hard workloads:

```text
sglib-combined:
  cycles -3.928%
  MPKI 4.0151 -> 2.3511

qrduino:
  cycles -10.465%
  MPKI 13.8664 -> 8.9337
```

The `slre` cycle change is effectively zero (-0.004%) while internal TAGE
MPKI slightly increases (1.5853 -> 1.5867), so no monotonic per-workload
accuracy claim is made.

Native e4096 -> e8192 changes the tagged index-transform width from 12 to 13
bits. A fixed-13 diagnostic is required before attributing this step to
capacity/alias pressure.

## Architecture significance

At 42.3250 KiB before any perceptron state, e8192 is purely a
performance-upper-envelope probe. It is not a compact Little-v0.52
architecture candidate.

The native performance knee and the final Pareto architecture selection
remain separate decisions.
