# Little v0.52 BPU-2 — micro-TAGE Instrumentation Contract

Status: **METHODOLOGY FROZEN / IMPLEMENTATION STAGED**

Date: 2026-10-06 KST

## Purpose

BPU-2 establishes predictor-internal measurements that are independent of the top-level BTB/target confound discovered during BPU-1.

All later micro-TAGE geometry and perceptron-gating claims must use these internal commit-time statistics in addition to whole-core cycles.

## Canonical experiment controls

```text
conditional predictor shift = 1
BTB shift                   = 2
indirect predictor shift    = 1
BTB                         = 4096 entries, direct-mapped proxy
RAS                         = 16
frontend                    = F3D3
```

## Prediction-time metadata

Each conditional prediction captures, before any later training can modify the selected table entry:

```text
actual selected provider kind
actual selected provider bank
selected-provider counter strength
selected-provider confidence class
final TAGE prediction
```

This metadata is carried in the branch-history object and consumed only when the branch reaches committed predictor update.

Do not reconstruct confidence from the table at commit time.

## Confidence definition

### Tagged-table provider

For signed TAGE counter `ctr`:

```text
strength = abs(2*ctr + 1)
```

For the current 3-bit tagged counter:

```text
ctr = -4/-3/-2/-1/0/1/2/3
strength = 7/5/3/1/1/3/5/7
```

Classes:

```text
WEAK    strength = 1
MEDIUM  strength = 3
STRONG  strength >= 5
```

### Bimodal provider

The base predictor uses a conventional 2-bit state reconstructed from prediction and shared hysteresis:

```text
00 strong not-taken
01 weak not-taken
10 weak taken
11 strong taken
```

Classes:

```text
WEAK    states 01 / 10
STRONG  states 00 / 11
MEDIUM  not used by bimodal provider
```

The distinction is frozen before observing micro-TAGE workload results.

## Commit-time statistics

Required:

```text
committedConditionalPredictions
committedConditionalCorrect
committedConditionalWrong

selectedProviderBank[0..N]
providerConfidence[WEAK/MEDIUM/STRONG]
providerConfidenceCorrect[WEAK/MEDIUM/STRONG]
providerConfidenceWrong[WEAK/MEDIUM/STRONG]
```

Existing TAGE provider-kind correctness statistics remain available and are retained.

Primary derived quantities:

```text
TAGE internal MPKI
weak-prediction activation rate
fraction of all TAGE errors occurring in weak-confidence predictions
provider-bank distribution
confidence-specific error rate
```

These quantities will later determine whether a selective perceptron corrector can cover a large fraction of errors while being accessed on only a small fraction of branches.

## Persistent storage accounting

Use the same convention as gem5 `TAGEBase::getSizeInBits()`.

Emit:

```text
storageBits
bimodalStorageBits
taggedStorageBits
historyStorageBits
otherStorageBits
```

Definitions:

```text
tagged:
  Σ entries_i × (tag bits_i + prediction-counter bits + useful bits)

bimodal:
  prediction bits + shared hysteresis bits

history:
  maximum global-history state + path-history state

other:
  use-alt counters + periodic-reset counter state
```

The emitted total must equal the sum of the components and must also match a recomputation from the emitted SimObject configuration.

This is persistent predictor state. In-flight speculative checkpoint metadata is not included in the predictor-state budget and must not be silently mixed into this number.

## BPU-2 gate

Run:

```bash
bash scripts/bpu_b2_micro_tage_instrumentation.sh
```

on the frozen six-workload subset:

```text
statemate
crc32
nsichneu
slre
sglib-combined
qrduino
```

PASS requires:

1. all six workloads complete successfully;
2. total = correct + wrong for every workload;
3. confidence-vector sum = total;
4. confidence-correct sum = correct;
5. confidence-wrong sum = wrong;
6. provider-bank sum = total;
7. storage total = component sum;
8. emitted-config recomputation exactly matches reported storage;
9. persistent storage is identical across workloads.

Only after this gate may confidence/activity results be used to design the selective perceptron activation policy.
