# Little v0.52 BPU-4 A1 — 2048 Extension Result and Capacity/Indexing Interpretation

Status: **PASS / TAGGED-CAPACITY AXIS STILL UNSATURATED**

Date: 2026-10-07 KST

## 2048 extension result

```text
workload             e1024 cyc      MPKI   e2048 cyc   vs1024%      MPKI
statemate               568760    0.0036      568760     0.000    0.0036
crc32                  1568364    0.0432     1568364     0.000    0.0432
nsichneu               1021406    0.0049     1021393    -0.001    0.0045
slre                   1187842    1.7810     1182529    -0.447    1.6624
sglib-combined         1617309   14.4287     1392699   -13.888    6.7198
qrduino                1888715   19.9027     1809621    -4.188   17.6430
```

Geomean:

```text
e2048/e1024 = 0.967732907
            = -3.22671% cycles

benefit 1024 -> 2048 = +3.22671%
max workload penalty of 1024 vs 2048
                        = +16.12768% (sglib-combined)
```

Exact persistent state:

```text
1024 entries/table = 45,670 bits = 5.5750 KiB
2048 entries/table = 88,678 bits = 10.8250 KiB
storage growth      = +94.17%
```

Reference visibility:

```text
e2048 vs Tournament canonical six-workload geomean = -4.64531%
worst workload vs Tournament                       = crc32 -0.00402%
```

Decision:

```text
BPU_B4_A1_FINAL_DECISION=EXTEND_ABOVE_2048_REQUIRED
```

This is the result of the predeclared performance-only knee rule. It does not by itself imply that a >10 KiB tagged predictor is the correct final Little-v0.52 design.

## Why the same TAGE algorithm changes so much with table size

The algorithmic policy is unchanged, but table geometry changes the physical mapping of (PC, history) contexts to predictor entries.

gem5 `TAGEBase::gindex()` computes:

```text
index =
    shiftedPC
    XOR shifted-PC mix
    XOR folded global history
    XOR folded path history

index &= (2^logTableSize - 1)
```

Crucially, `logTagTableSizes[bank]` is used not only in the final mask but also in:

- the shifted-PC mixing distance;
- the width of the folded global-history index state;
- the path-history mixing function `F()`.

Therefore changing 1024 -> 2048 entries changes:

```text
logTableSize 10 -> 11
```

and consequently changes both capacity **and the hash/index mapping itself**.

The tag computation remains based on PC and folded tag histories with the same 8/9/10-bit tag widths, but which dynamic history contexts compete for an entry changes substantially.

## Mechanisms

The observed benefit can come from a combination of:

1. **lower destructive aliasing**
   - fewer unrelated (PC, history) contexts map onto one tagged entry;
   - prediction counters are overwritten/trained by fewer unrelated branches.

2. **higher residency / reduced replacement pressure**
   - useful tagged entries survive longer;
   - the `u` bit is less often forced/aged because multiple useful contexts collide.

3. **more successful long-history specialization**
   - a context that previously fell back to a shorter-history bank or bimodal can retain a matching tagged entry;
   - provider choice can shift toward the intended longer-history table.

4. **different index-hash mapping**
   - because `logTagTableSizes` participates in `gindex()` and `F()`, some improvement can be due to a more favorable remapping rather than capacity alone.

Thus this A1 sweep must be described as a **tagged-table geometry/capacity sweep**, not a pure “number of entries only with otherwise identical mapping” experiment.

## Interpretation of the hard workloads

The continuous improvements:

```text
sglib-combined:
  512 MPKI   22.9871
  1024 MPKI  14.4287
  2048 MPKI   6.7198

qrduino:
  512 MPKI   22.0602
  1024 MPKI  19.9027
  2048 MPKI  17.6430
```

are strong evidence that the original S0 512-entry tables were capacity/alias-sensitive on these workloads.

However, current evidence cannot yet distinguish how much of the improvement is from:

```text
more entries
vs
different index/hash mapping
vs
changed provider/allocation dynamics
```

## Research consequence

The tagged-capacity axis is still unsaturated by the predeclared performance knee rule.

At the same time, 2048 already costs:

```text
10.825 KiB
```

for micro-TAGE alone, before the selective perceptron is added. This exceeds the approximate logical-state size of the TournamentBP conditional predictor baseline.

Therefore the final architecture decision must remain a **Pareto decision**, not “choose the largest performance point”.

The 1024 point remains especially interesting because it:

- uses 5.575 KiB of micro-TAGE state;
- is smaller than the Tournament conditional predictor baseline;
- already beats the Tournament canonical six-workload geomean by 1.46590%;
- leaves storage headroom for the future selective perceptron.

The 2048 point is currently an **upper-performance probe**, not a preferred final architecture candidate.

## Next analysis

Before interpreting the next capacity point, run the no-rerun postprocessor:

```bash
bash scripts/bpu_b4_a1_provider_confidence_delta.sh
```

It compares 1024 vs 2048 using existing ROI outputs and reports changes in:

- selected provider bank distribution;
- weak/medium/strong confidence distribution;
- longest-match vs bimodal provider share;
- longest-match error share;
- total TAGE error reduction.

This does not isolate hash collisions directly, but it can show whether the 2048 benefit is accompanied by a systematic shift toward tagged providers and stronger confidence.

A future extension run should add explicit allocation/replacement/conflict-pressure instrumentation if the capacity axis continues to improve materially.
