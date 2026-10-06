# Little v0.52 BPU-3 — micro-TAGE Directed Correctness Closure

Status: **CLOSED / PASS**

Date: 2026-10-06 KST

## Directed gate result

The deterministic RV64 directed branch kernel retained:

```text
static conditional branches = 8
```

Two identical executions produced exactly identical measured results:

```text
metric                       run1         run2
simTicks                 2,766,016,008  2,766,016,008
simInsts                     4,027,630      4,027,630
historyStateRecords          1,884,983      1,884,983
historyStateRestores         1,223,775      1,223,775
historyRestoreChecks         1,223,775      1,223,775
predictionMetadataChecks       720,000        720,000
committedConditionalPreds      720,000        720,000
TAGE wrong                     215,236        215,236
persistent storage bits         24,166         24,166
```

Final markers:

```text
BPU_B3_HISTORY_ROLLBACK_CHECK=PASS
BPU_B3_PREDICTION_METADATA_CHECK=PASS
BPU_B3_EXACT_GEOMETRY_CHECK=PASS
BPU_B3_DETERMINISM_CHECK=PASS
BPU_B3_DIRECTED_CORRECTNESS=PASS
BPU_B3_DIRECTED_CORRECTNESS_PROVENANCE=PASS
```

## What was verified

### Speculative-history rollback

All 1,223,775 observed rollback events passed semantic state restoration checks.

For every rollback, the audit verifies:

- legal circular-buffer pointer placement, including the one permitted rollover relocation;
- exact raw global-history window for all `maxHist=64` bits;
- exact path history;
- exact folded index history in each tagged bank;
- exact folded tag history 0 in each tagged bank;
- exact folded tag history 1 in each tagged bank.

Thus:

```text
historyStateRestores == historyRestoreChecks
1,223,775 == 1,223,775
```

### Prediction-time metadata

Every committed conditional prediction passed provider/confidence metadata consistency:

```text
predictionMetadataChecks == committedConditionalPredictions
720,000 == 720,000
```

The checks cover provider type, selected provider bank, prediction-time counter strength, confidence class, and provider-kind/bank consistency.

### Exact S0 geometry

The emitted configuration and runtime accounting remained:

```text
bimodal entries          2048
tagged tables            3
tagged entries/table     512
history lengths          8 / 24 / 64
tag widths               8 / 9 / 10
conditional PC shift     1
persistent state         24,166 bits
```

### Determinism

The complete correctness tuple was bit-identical across two executions, including modeled time, committed instructions, rollback counts, metadata checks, TAGE errors, and storage accounting.

## Earlier audit-assertion defect

The first BPU-3 attempt failed because the audit incorrectly required physical global-history pointer identity across gem5's legal circular-buffer rollover.

That audit defect was corrected before this closure. The successful gate validates logical history contents and folded state rather than incorrectly requiring identical backing-buffer placement.

See:

```text
docs/BPU_B3A_ROLLOVER_ASSERTION_FIX_2026-10-06.md
```

## Milestone state

```text
BPU-0 methodology contract       CLOSED
BPU-1 indexing/proxy condition   CLOSED
BPU-2 instrumentation            CLOSED
BPU-3 directed correctness       CLOSED
BPU-4 micro-TAGE geometry sweep  NEXT
```

BPU-4 may now begin without reopening frozen I-EXEC state.
