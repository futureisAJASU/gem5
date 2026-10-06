# Little v0.52 BPU-2A — Confidence / Provider Profile

Status: **PASS / POST-PROCESS ANALYSIS CLOSED**

Date: 2026-10-06 KST

Source:
- frozen BPU-2 micro-TAGE instrumentation output
- no simulation rerun; post-processing only
- canonical proxy condition: conditional shift1 / BTB shift2 / indirect shift1 / 4K direct-mapped BTB / RAS16 / F3D3

## Confidence profile

```text
workload           W access%   W err%   W enrich   M access%   M err%   M enrich   W+M access%   W+M err%   W+M enrich
statemate              0.030   66.667    2230.74       0.015    0.000       0.00          0.045      66.667      1469.02
crc32                  0.002    0.578     335.74       0.002    0.000       0.00          0.003       0.578       167.87
nsichneu               4.833   52.632      10.89       0.021    0.000       0.00          4.854      52.632        10.84
slre                   0.096    2.403      25.14       0.355   20.671      58.24          0.450      23.073        51.22
sglib-combined         9.050   19.593       2.16       3.510   11.503       3.28         12.560      31.096         2.48
qrduino               11.431   23.716       2.07       4.965   12.821       2.58         16.396      36.537         2.23
```

## Main conclusion

The selective-corrector premise is supported, but **weakest-only activation is too narrow to freeze as the final policy**.

Weak predictions are strongly enriched for errors, but on the hardest branch workloads they leave most errors outside the gate:

```text
sglib-combined:
  weak access = 9.050%
  weak error coverage = 19.593%

qrduino:
  weak access = 11.431%
  weak error coverage = 23.716%
```

Adding MEDIUM meaningfully improves error coverage:

```text
slre:
  W+M access = 0.450%
  W+M error coverage = 23.073%
  enrichment = 51.22x

sglib-combined:
  W+M access = 12.560%
  W+M error coverage = 31.096%
  enrichment = 2.48x

qrduino:
  W+M access = 16.396%
  W+M error coverage = 36.537%
  enrichment = 2.23x
```

For `nsichneu`, MEDIUM adds essentially nothing; WEAK alone already covers 52.632% of TAGE errors at 4.833% activation.

Therefore the likely activation families to compare after micro-TAGE geometry freeze are:

```text
weak only
weak + medium
broader low-confidence policy if needed
always-on
```

Do **not** freeze weak+medium yet. Geometry changes can change provider tables, counter strengths, and therefore the confidence distribution.

## Provider-kind profile

```text
workload            bimodal%  longest%  bimAlt%  tageAlt%  longest err%
statemate             65.218    34.781     0.001     0.000        16.667
crc32                  0.099    99.897     0.001     0.003        98.844
nsichneu              74.082    25.917     0.001     0.000         5.263
slre                  68.943    30.727     0.039     0.291        87.443
sglib-combined        56.561    40.175     2.154     1.110        55.869
qrduino               40.947    56.087     2.325     0.642        61.257
```

This profile is important for sequencing the research.

- `crc32` is almost entirely longest-match provided.
- `slre`, `sglib-combined`, and `qrduino` place a large share of their errors in longest-match providers.
- Therefore a substantial fraction of current errors may still be addressable by micro-TAGE geometry/history/tag tuning itself rather than a corrector.

This supports the existing roadmap:

```text
BPU-3 directed correctness
BPU-4 micro-TAGE geometry sweep
BPU-5 micro-TAGE knee freeze
only then:
BPU-6+ perceptron implementation and activation tuning
```

## Performance reminder

The S0 seed remains a starting point, not a winner:

```text
micro-TAGE / Tournament canonical six-workload cycle geomean
= 1.012185157
= +1.21852% cycles
```

The largest S0 regressions remain:

```text
sglib-combined  +7.4803%
qrduino         +2.6823%
```

These must remain visible as guardrail workloads during geometry tuning.

## Research interpretation

The evidence currently supports:

> Low-confidence TAGE predictions are disproportionately error-prone, so selective neural correction remains a plausible Little-v0.52-style allocation strategy.

The evidence does **not** yet support:

> Weak-only activation is the final gate.

or:

> Weak+medium is already the final gate.

Those decisions are deferred until the micro-TAGE geometry is frozen.
