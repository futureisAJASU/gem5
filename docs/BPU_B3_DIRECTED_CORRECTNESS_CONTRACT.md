# Little v0.52 BPU-3 — micro-TAGE Directed Correctness Contract

Status: **STAGED / SERVER UNRUN**

Date: 2026-10-06 KST

## Goal

BPU-3 verifies that the S0 micro-TAGE implementation remains functionally correct under speculative execution before any geometry sweep begins.

This stage does not tune performance.

## Properties under test

### 1. Exact seed geometry

The emitted configuration must match:

```text
bimodal entries          2048
tagged tables            3
tagged entries/table     512
history lengths          8 / 24 / 64
tag widths               8 / 9 / 10
conditional PC shift     1
persistent state         24,166 bits
```

### 2. Prediction-time metadata integrity

Every committed conditional prediction must pass consistency checks for:

```text
provider type
selected provider bank
provider counter strength
confidence class
provider-kind ↔ bank relationship
```

The number of successful metadata checks must equal the number of committed conditional predictions in the measured ROI.

### 3. Speculative-history rollback correctness

At prediction-time history snapshot, save:

```text
path history
global-history pointer
folded index history per tagged bank
folded tag history 0 per tagged bank
folded tag history 1 per tagged bank
```

Whenever a speculative history update is rolled back, after inversion the current predictor history must exactly match that saved snapshot.

Any mismatch is a runtime fatal error.

Successful rollback checks must equal observed restore events.

### 4. Directed stress

The dedicated RV64 branch kernel uses several deterministic, changing, cross-correlated conditional branches with compiler if-conversion disabled.

The gate requires:

```text
at least 4 static conditional branches in branch_kernel
at least 1 committed TAGE error
at least 1 speculative history restore
```

Thus a PASS cannot be produced by a branch-free or trivially perfect workload.

### 5. Reproducibility

The identical directed binary is run twice under the same micro-TAGE configuration.

The following tuple must match exactly across runs:

```text
simTicks
simInsts
history snapshots
history restores
history restore checks
metadata checks
committed conditional predictions
TAGE errors
storage bits
```

## Execution

```bash
bash scripts/bpu_b3_tage_directed_correctness.sh
```

Expected final markers:

```text
BPU_B3_HISTORY_ROLLBACK_CHECK=PASS
BPU_B3_PREDICTION_METADATA_CHECK=PASS
BPU_B3_EXACT_GEOMETRY_CHECK=PASS
BPU_B3_DETERMINISM_CHECK=PASS
BPU_B3_DIRECTED_CORRECTNESS=PASS
BPU_B3_DIRECTED_CORRECTNESS_PROVENANCE=PASS
```

Only after this gate closes may BPU-4 geometry sweeps begin.
