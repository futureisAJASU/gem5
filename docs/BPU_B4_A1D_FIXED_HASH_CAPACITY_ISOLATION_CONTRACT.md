# Little v0.52 BPU-4 A1D — Fixed-Hash Capacity Isolation Diagnostic

Status: **METHODOLOGY FROZEN / STAGED / SERVER UNRUN**

Date: 2026-10-07 KST

## Why this diagnostic exists

The native BPU-4 A1 sweep changed tagged-table capacity through
`logTagTableSizes`. In gem5 TAGE, that parameter affects more than the
final table mask:

- folded global-history index width;
- shifted-PC mixing distance;
- path-history mixing in `F()`;
- final physical index width.

Therefore the native 512/1024/2048 results combine:

1. true capacity/collision/residency effects; and
2. width-dependent index/hash remapping.

The native sweep remains the correct experiment for **real architecture
selection**, because a physical table-size change naturally changes its
index width and implementation geometry.

A1D is a separate causal diagnostic intended to answer:

> Does the large hard-workload improvement persist when the index transform
> is held constant and only the physical tagged-table capacity changes?

## Controlled indexing definition

A1D freezes the tagged index transform to the native 2048-entry width:

```text
canonical index-hash width = 11 bits
```

For every tagged bank and every physical capacity:

```text
PC mixing width              = 11 bits
folded GHR index width       = 11 bits
path-history F() mix width   = 11 bits
history lengths              = 8 / 24 / 64
tag widths                   = 8 / 9 / 10
tag computation              = unchanged
```

A canonical 11-bit hash is computed first. Only the final physical mask
changes:

```text
512-entry table   -> low 9 bits
1024-entry table  -> low 10 bits
2048-entry table  -> all 11 bits
```

Thus the physical table sizes are still:

```text
512 / 1024 / 2048 entries per tagged bank
```

and capacity-driven behavior is intentionally allowed to change.

## What is intentionally allowed to vary

The following are **not** controlled away, because they are genuine
consequences of capacity:

- destructive alias frequency;
- entry residency;
- useful-bit pressure;
- replacement/allocation churn;
- provider-bank selection;
- fallback to shorter-history/bimodal providers;
- confidence distribution;
- prediction accuracy.

Holding these fixed would remove the mechanism through which table capacity
affects a TAGE predictor.

## What is held fixed

A1D specifically removes width-dependent remapping from:

- PC hash/mix width;
- folded global-history index width;
- path-history hash width.

The final physical-capacity mask necessarily changes.

## Positive control

The 2048-entry native configuration already uses an 11-bit index width.

Therefore:

```text
native e2048
and
fixed-11 controlled e2048
```

must converge exactly.

The runner requires equality for each frozen workload in:

- cycles;
- committed instructions;
- committed conditional predictions;
- TAGE correct/wrong counts;
- selected-provider-bank vector;
- provider-confidence vector.

If this convergence fails, the controlled diagnostic is invalid and no
capacity interpretation may be made.

## Sweep matrix

Frozen six-workload subset:

```text
statemate
crc32
nsichneu
slre
sglib-combined
qrduino
```

Controlled points:

```text
512 tagged entries/table
1024 tagged entries/table
2048 tagged entries/table
```

Total new simulations:

```text
3 × 6 = 18 ROI runs
```

Native results are reused from the existing A1/A1-extension evidence; they
are not rerun.

## Persistent state

The diagnostic changes only combinational indexing behavior, not persistent
state accounting.

Expected direction-predictor state:

```text
e512   = 24,166 bits = 2.9500 KiB
e1024  = 45,670 bits = 5.5750 KiB
e2048  = 88,678 bits = 10.8250 KiB
```

## Required output

The runner reports:

1. controlled fixed-hash cycles and TAGE-internal MPKI;
2. controlled 512→1024 and 1024→2048 geomean effects;
3. corresponding native geometry effects;
4. native-vs-controlled performance at equal capacity;
5. exact 2048 positive-control convergence;
6. storage and BPU-3 runtime-invariant checks.

Interpretation rule:

> The controlled fixed-hash sweep estimates capacity/collision pressure under
> an invariant index transform. The difference between native and controlled
> results is evidence of mapping sensitivity, **not an additive causal
> decomposition**, because predictor training/allocation state evolves
> nonlinearly.

## Decision use

A1D does **not** replace the native A1 performance-knee experiment and does
not directly select the final architecture.

Use:

```text
native A1     -> architecture / Pareto candidate selection
A1D           -> mechanism / causal interpretation
```

If the large `sglib-combined` and `qrduino` gains persist under fixed
hashing, this supports a capacity/alias-pressure explanation.

If the controlled gains shrink substantially, native width-dependent
remapping is a material part of the observed improvement and must be stated
explicitly in the paper.

## Execution

```bash
bash scripts/bpu_b4_a1d_fixed_hash_capacity_sweep.sh
```

Expected completion markers:

```text
BPU_B4_A1D_2048_NATIVE_CONVERGENCE=PASS
BPU_B4_A1D_FIXED_HASH_GEOMETRY_GATE=PASS
BPU_B4_A1D_STORAGE_GATE=PASS
BPU_B4_A1D_CAPACITY_ISOLATION_SWEEP=PASS
BPU_B4_A1D_PROVENANCE=PASS
```

Artifacts:

```text
bpu_b4a1d_fixed_hash_capacity/summary.csv
bpu_b4a1d_fixed_hash_capacity/interpretation_guardrails.txt
bpu_b4a1d_fixed_hash_capacity/manifest.txt
```

This diagnostic is considered important evidence for any later paper claim
that larger tagged tables improve the hard workloads primarily by reducing
capacity/alias pressure.
