# Little v0.52 BPU-5A — G5 Strong-Confidence Error Localization

Status: **CLOSED / PASS**

Date: 2026-10-08 KST

## Exact gates

```text
BPU_B5A_WRONG_EVENT_RECONCILIATION=PASS
BPU_B5A_CONFIDENCE_RECONCILIATION=PASS
BPU_B5A_STRONG_PC_LOCALIZATION=PASS
BPU_B5A_PROVENANCE=PASS
```

The trace is restricted to the exact ROI tick window
`[finalTick - simTicks, finalTick]`.

## Aggregate strong-error concentration

```text
strong wrong events     = 99,706
unique strong-wrong PCs = 494

top  1 identities cover  7.286%
top  4 identities cover 25.376%
top  8 identities cover 36.873%
top 16 identities cover 53.234%
top 32 identities cover 69.248%
top 64 identities cover 83.551%

PCs for 50% coverage = 15
PCs for 75% coverage = 42
PCs for 90% coverage = 94
```

Aggregate identities are workload + static PC so unrelated binaries sharing
the same virtual address are not falsely merged.

## Representative difficult workloads

```text
qrduino:        N50=6  N75=15  N90=35
sglib-combined: N50=7  N75=15  N90=28
huffbench:      N50=3  N75=5   N90=9
picojpeg:       N50=6  N75=11  N90=17
slre:           N50=1  N75=1   N90=2
```

## Provider distribution of strong errors

```text
BIMODAL_ONLY        5.840%
TAGE_LONGEST_MATCH 82.920%
BIMODAL_ALT         2.504%
TAGE_ALT            8.736%
```

The residual strong-confidence problem is therefore primarily a longest-match
TAGE failure, not a bimodal fallback artifact.

## Relation to BPU-5 confidence profile

G5 full-19 aggregate:

```text
W+M access       = 2.986%
W+M error share  = 26.864%
strong err share = 73.136%
```

If W+M triggering is combined with an oracle top-K strong-PC set, the
reachable total-error upper bound is approximately:

```text
W+M + top16 strong PCs  ~= 65.8%
W+M + top32 strong PCs  ~= 77.5%
W+M + top64 strong PCs  ~= 88.0%
```

These are **oracle upper bounds**, not hardware results.

## Conclusion

Strong-confidence errors are highly concentrated in recurring static branch
identities. This preserves the selective-corrector thesis and motivates:

```text
trigger =
  weak-or-medium TAGE confidence
  OR
  learned recurring-hard-branch indication
```

However, no 64-entry hardware table is frozen by this result. The top-K list
uses future knowledge and ignores correct accesses, activation rate, aliasing,
replacement, finite tags, online learning delay, and phase changes.

## BPU-5B

The next gate is a temporal holdout:

1. trace every committed conditional G5 event;
2. train/rank strong-hard PCs using only the chronological first half;
3. freeze K=8/16/32/64 learned sets;
4. evaluate only the second half;
5. combine with W+M confidence triggering;
6. measure activation rate, total-error coverage, strong-error coverage,
   enrichment, and learned-PC persistence.

This is still an ideal learned-set test, not a finite-associativity hardware
table. It removes future-information leakage and determines whether hard-PC
recurrence is temporally stable enough to justify implementing such a table.

Runner: `scripts/bpu_b5b_g5_temporal_holdout.sh`.
