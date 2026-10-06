# Little v0.52 BPU-4 A1 — Native 4096 Extension Result

Status: **PASS / PERFORMANCE AXIS STILL UNSATURATED**

Date: 2026-10-07 KST

## Result

```text
workload             e2048 cyc      MPKI   e4096 cyc   vs2048%      MPKI
statemate               568760    0.0036      568760     0.000    0.0036
crc32                  1568364    0.0432     1568364     0.000    0.0432
nsichneu               1021393    0.0045     1021384    -0.001    0.0040
slre                   1182529    1.6624     1180143    -0.202    1.5853
sglib-combined         1392699    6.7198     1312995    -5.723    4.0151
qrduino                1809621   17.6430     1687203    -6.765   13.8664
```

Geomean:

```text
e4096/e2048 = 0.978402202
            = -2.15978% cycles

benefit e2048 -> e4096 = +2.15978%
max workload penalty of e2048 vs e4096
                        = +7.25568% (qrduino)
```

Persistent state:

```text
e2048  =  88,678 bits = 10.8250 KiB
e4096  = 174,694 bits = 21.3250 KiB
growth = +97.00%
```

Tournament visibility:

```text
e4096 geomean vs Tournament = -6.70476%
worst workload              = crc32 -0.00402%
```

Decision under the predeclared performance-only knee rule:

```text
BPU_B4_A1_FINAL_DECISION=EXTEND_ABOVE_4096_REQUIRED
```

## Interpretation boundary

This result proves only that the native tagged-table performance axis has not saturated by 4096 entries/table on the frozen six-workload subset.

It does **not** by itself prove that the 2048 -> 4096 gain is purely a capacity effect because native geometry changes the TAGE index-transform width from 11 to 12 bits.

The previous fixed-11 diagnostic established capacity dominance over 512 -> 1024 -> 2048, but a corresponding fixed-12 diagnostic is required before attributing the new 2048 -> 4096 gain to the same mechanism.

## Architecture significance

At 21.3250 KiB for micro-TAGE alone, e4096 is no longer a plausible compact Little-v0.52 final predictor candidate under the Selective Complexity Allocation philosophy.

Its role is therefore:

```text
performance saturation / upper-envelope probe
```

rather than preferred final architecture.

The final design decision remains a Pareto decision involving performance, state, activity/power, and future selective-perceptron headroom.

## Next mandatory work

1. Fixed-12 causal diagnostic:
   `scripts/bpu_b4_a1d_fixed12_2048_4096.sh`

2. Native endpoint extension:
   `scripts/bpu_b4_a1_extend_8192.sh`

The native 8192 point has:

```text
346,726 bits = 42.3250 KiB
```

of persistent micro-TAGE state before any perceptron is added.

The 8192 point is strictly an upper-envelope/saturation probe, not a final compact-design candidate.
