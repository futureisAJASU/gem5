# Little v0.52 BPU-5 — G5/G7 Confidence Profile

Status: **PROFILE PASS / CONFIDENCE-ONLY GATE INSUFFICIENT**

Date: 2026-10-07 KST

## Full-19 aggregate

```text
G5:
  weak access        1.860%
  weak error share  12.562%
  weak enrichment    6.754x

  medium access      1.126%
  medium error share 14.302%
  medium enrichment  12.702x

  weak+medium access 2.986%
  weak+medium errors 26.864%
  W+M enrichment      8.997x

  strong error share 73.136%

G7:
  weak access        1.775%
  weak error share  16.301%
  weak enrichment    9.184x

  medium access      0.963%
  medium error share 14.529%
  medium enrichment 15.087x

  weak+medium access 2.739%
  weak+medium errors 30.830%
  W+M enrichment     11.256x

  strong error share 69.170%
```

## Interpretation

The selective-corrector premise is supported in one important sense:

> Low-confidence accesses are rare but highly enriched for errors.

For G5, activating on weak+medium would examine only 2.986% of committed conditional predictions while covering 26.864% of TAGE errors. For G7, 2.739% of accesses cover 30.830% of errors.

Medium confidence is especially informative: it has the highest aggregate enrichment in both profiles.

Therefore weak-only gating is no longer a serious default candidate. Weak+medium is the minimum evidence-supported confidence gate.

However, confidence-only gating is not sufficient for the full design thesis because strong-confidence predictions account for 73.136% of G5 errors and 69.170% of G7 errors.

This does not mean those strong errors require always-on correction. The missing question is whether they are concentrated in a small set of recurring static branches.

## Workload examples

Strong-error share is very high on several workloads:

```text
G5:
  crc32          99.422%
  edn            99.134%
  matmult-int    99.897%
  nettle-aes     99.099%
  slre           91.979%

G7:
  crc32          99.422%
  edn            99.136%
  matmult-int    99.898%
  nettle-aes     98.795%
  st             97.368%
  slre           91.969%
```

Yet some workloads show very strong low-confidence concentration:

```text
G5 W+M error coverage:
  minver       82.857%
  aha-mont64   76.166%
  nbody        70.000%
  nsichneu     66.667%
  statemate    64.286%
  ud           65.957%

G7 W+M error coverage:
  minver       83.871%
  statemate    77.778%
  nbody        75.000%
  ud           68.817%
  aha-mont64   67.266%
  nsichneu     65.385%
```

Thus the residual strong-confidence problem is workload/branch dependent.

## Design consequence

Do not implement the final perceptron gate as confidence-only yet.

The current candidate policy becomes:

```text
minimum candidate:
  weak + medium confidence

possible extension, pending evidence:
  weak + medium
  OR
  small learned hard-branch trigger
```

A hard-branch trigger is not frozen by this document. It is only an evidence-driven possibility.

Before adding new persistent state, BPU-5A must determine whether G5 strong-confidence errors are concentrated in a small number of static branch PCs.

If strong errors are highly concentrated, a tiny PC-indexed difficulty structure may retain selective activation while reaching errors that TAGE itself labels strong.

If strong errors are diffuse, confidence-plus-PC gating is unlikely to be sufficient and the corrector activation policy must be reconsidered.

## Next gate

BPU-5A — exact strong-error static-PC localization on frozen G5.

Required outputs:

- every logged wrong conditional must reconcile with TAGE committed wrong stats;
- exact confidence-class reconciliation;
- strong-error top-K static branch coverage for K=1/4/8/16/32/64;
- per-workload strong-error concentration;
- provider/bank metadata for those wrong events.

No perceptron implementation is authorized before this localization gate.
