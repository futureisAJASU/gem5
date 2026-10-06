# Little v0.52 BPU-2 — micro-TAGE Instrumentation Closure

Status: **CLOSED / PASS**

Date: 2026-10-06 KST

## Gate result

The frozen six-workload subset completed under the canonical proxy condition:

```text
conditional predictor shift = 1
BTB shift                   = 2
indirect predictor shift    = 1
BTB                         = 4096 entries, direct-mapped proxy
```

All required invariants passed:

```text
BPU_B2_TAGE_INTERNAL_INVARIANTS=PASS
BPU_B2_STORAGE_ACCOUNTING=PASS
BPU_B2_MICRO_TAGE_INSTRUMENTATION=PASS
BPU_B2_INSTRUMENTATION_PROVENANCE=PASS
```

## Exact persistent state

The S0 seed occupies, under the frozen persistent-state accounting convention:

```text
tagged tables   21,504 bits
bimodal          2,560 bits
history             80 bits
other               22 bits
--------------------------------
total            24,166 bits
                 3,020.75 bytes
                 2.9500 KiB
```

The runtime-reported total and components matched the independent reconstruction from emitted `config.ini`.

## Internal TAGE results

```text
workload            cycles     TAGE MPKI   weak%    weak-error share
statemate            568,771     0.0044     0.030%    66.667%
crc32              1,568,364     0.0432     0.002%     0.578%
nsichneu           1,021,495     0.0085     4.833%    52.632%
slre               1,180,231     1.5903     0.096%     2.403%
sglib-combined     1,847,793    22.9871     9.050%    19.593%
qrduino            1,954,753    22.0602    11.431%    23.716%
```

Selected-provider-bank distribution:

```text
workload            B0        B1        B2        B3
statemate          65.219%   26.086%    8.696%    0.000%
crc32               0.100%    0.587%    1.941%   97.373%
nsichneu           74.083%   11.999%    6.720%    7.199%
slre               68.982%   12.533%   11.375%    7.110%
sglib-combined     58.715%   31.889%    7.722%    1.674%
qrduino            43.271%   49.858%    6.237%    0.634%
```

## Immediate interpretation

The selective-corrector premise remains plausible, but **weakest-confidence-only activation is not sufficient as the default policy**.

The enrichment factor:

```text
weak-error-share / weak-access-share
```

is approximately:

```text
statemate          ~2222×   (very small sample / do not over-interpret)
crc32               ~289×   (very small weak population)
nsichneu             10.9×
slre                  25.0×  but only 2.4% of all errors are covered
sglib-combined         2.16×
qrduino                2.07×
```

Thus weak predictions are often disproportionately error-prone, but the hardest workloads still leave most errors outside the weakest class.

The next policy decision must therefore compare at least:

```text
weak only
weak + medium
all low-confidence / broader gate
always-on
```

using the already captured confidence vectors.

## S0 seed performance is not a final result

Against the TournamentBP canonical-condition cycles from BPU-1:

```text
statemate          -0.0274%
crc32              -0.0040%
nsichneu           +0.0058%
slre               -2.5354%
sglib-combined     +7.4803%
qrduino            +2.6823%
```

The six-workload geomean is approximately:

```text
micro-TAGE / TournamentBP = 1.012185157
                          = +1.21852% cycles
```

Therefore S0 is **not** a final performance winner. This is expected: BPU-2 validates instrumentation and the historical seed geometry, not the final micro-TAGE knee.

The poor `sglib-combined` and `qrduino` results are especially important and must remain visible during the geometry sweep.

## Metric separation

BPU-2 confirms the need to separate:

```text
TAGE-internal committed direction correctness
from
top-level branch/BTB target-side misprediction counters
```

All direction-predictor geometry and corrector claims will use the former as the predictor-accuracy metric.

## Follow-up analysis

`scripts/bpu_b2_confidence_profile.sh` performs a no-rerun post-processing pass over the existing BPU-2 output and reports:

```text
weak / medium / strong access share
weak / medium / strong error share
confidence-class error enrichment
weak+medium aggregate coverage/activity
provider-kind distribution
provider-kind error share
micro-TAGE vs Tournament canonical cycle delta
```

No simulation rerun is required.

## Milestone state

```text
BPU-0 methodology contract       CLOSED
BPU-1 indexing/proxy condition   CLOSED
BPU-2 instrumentation            CLOSED
BPU-3 directed correctness       NEXT
```
