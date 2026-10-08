# Little v0.52 BPU-6A — Fixed TAGE Prior22 Diagnostic Result

Status: **CLOSED / FAIL-BUT-INFORMATIVE**

Date: 2026-10-08 KST

## Purpose

BPU-6A tested exactly one source-anchored integration change after the failed
BPU-6 standalone-direction perceptron seed:

```text
combined_sum =
    raw_perceptron_sum
    + (tagePred ? +22 : -22)
```

The +/-22 prior was taken from gem5 MPP-TAGE's base-prediction prior. It was
not selected from Little-v0.52 outcome data.

All other seed parameters remained unchanged:

```text
base TAGE      = G5
rows           = 64
history        = 24
weight width   = signed 6-bit
training theta = 60
weight state   = 9,600 bits
combined state = 55,336 bits = 6.7549 KiB
```

## Full-19 result

```text
profile    vs BPU-6 seed   vs G5       vs G7       activation   TAGE wrong   final wrong   fixes    breaks    net
V1+P22       -0.27642%     +0.27610%   +1.50805%     5.604%       136468       142847      19583     25962    -6379
WM+P22       -0.09332%     +0.04706%   +1.27620%     2.977%       136678       136858      12989     13169     -180
```

Accounting and provenance gates all passed:

```text
BPU_B6A_STORAGE_GATE=PASS
BPU_B6A_FINAL_ERROR_RECONCILIATION=PASS
BPU_B6A_PRIOR22_FULL19=PASS
BPU_B6A_PROVENANCE=PASS
```

## Interpretation

The source-anchored TAGE prior clearly improves integration quality relative to
the standalone-direction BPU-6 seed:

```text
V1:
  net correction  -12,962 -> -6,379
  cycles vs G5     +0.55406% -> +0.27610%

W+M:
  net correction   -2,576 -> -180
  cycles vs G5     +0.14051% -> +0.04706%
```

Thus BPU-6's large break rate was not evidence that all neural correction
signal is useless. Giving the already-trained TAGE predictor an explicit prior
substantially suppresses harmful overrides.

However, the predeclared BPU-6A success gate is not met:

```text
required: fixes > breaks
observed:
  V1+P22  19,583 < 25,962
  WM+P22  12,989 < 13,169

required: finalWrong < local TAGEwrong
observed:
  V1+P22  142,847 > 136,468
  WM+P22  136,858 > 136,678

required: cycle improvement vs failed seed
observed:
  PASS for both variants

required: storage/accounting
observed:
  PASS
```

Therefore the architecture-value gate fails even though the integration
diagnostic is informative.

## Per-workload notes

V1+P22 improves several workloads relative to the failed V1 seed, but still
degrades the main difficult set versus plain G5:

```text
huffbench       vs G5 +1.210%
picojpeg        vs G5 +0.779%
qrduino         vs G5 +0.783%
sglib-combined  vs G5 +1.115%
slre            vs G5 +0.617%
```

Some workloads show positive local correction behavior:

```text
nbody      final MPKI 0.2418 -> 0.1881
nsichneu   final MPKI 0.0139 -> 0.0094
```

but these do not outweigh the regressions in the dominant hard workloads.

## Decision

**Do not sweep the TAGE prior.**

The fact that WM+P22 ends only 180 net errors negative makes further prior
values tempting, but doing so would convert a source-anchored diagnostic into
post-hoc tuning against the frozen corpus.

The classic 64x24x6 PC-indexed perceptron is therefore demoted to a
**reference corrector (C0)** rather than a final architecture candidate.

What survives from BPU-6/6A:

1. neural residual signal exists;
2. base-aware combination is necessary;
3. independent direction replacement is inappropriate;
4. a more hardware-efficient/statistical corrector should be compared under
   a common Little-core contract.

## Next milestone

Proceed to BPU-7 Corrector Microarchitecture Tournament.

Predeclare before results:

```text
C0 = classic perceptron reference
C1 = tiny Multi-GEHL / MGSC
C2 = tiny hashed multiperspective corrector
C3 = no-corrector G5 / larger-TAGE G7 references
```

Comparison must use common G5 base, near-iso corrector state budget,
prediction-time inputs, activation policy, and latency model.

No classic-perceptron parameter sweep is authorized before BPU-7.
