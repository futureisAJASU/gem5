# Little v0.52 BPU-1A — RV64 micro-TAGE Configuration Smoke

Status: **CLOSED / SERVER-DIRECTED PASS (configuration smoke only)**

Date: 2026-10-06 KST

## Scope

This gate validates only:

- RISCV gem5 build with the exact-history TAGE extension,
- RV64 proxy selection of TournamentBP vs LittleMicroTAGE,
- execution of PC-index shift 0/1/2 for both predictors,
- emitted LittleMicroTAGE seed geometry,
- presence of RVC/16-bit code in the directed audit binary.

It does **not** select the final PC-index shift and does **not** establish a performance knee.

## Server evidence supplied by user

Audit binary:

```text
benchmarks/bin/independent_int_rv64
ELF 64-bit RISC-V, RVC
BPU_SHIFT_EVIDENCE_SCOPE=DIRECTED_SMOKE_ONLY
BPU_AUDIT_16BIT_ENCODING_LINES=49828
```

All six predictor/shift combinations exited with code 0.

Observed whole-program simTicks:

```text
Tournament:
  shift0 = 35722493142
  shift1 = 35722434594
  shift2 = 35722373190

LittleMicroTAGE:
  shift0 = 35722552404
  shift1 = 35722430310
  shift2 = 35722368192
```

These differences are extremely small and this workload is explicitly a directed smoke. No shift performance conclusion is permitted from these values.

Emitted micro-TAGE configuration gate:

```text
BPU_MICRO_TAGE_CONFIG_GATE=PASS
micro_tage_section=board.processor.cores.core.branchPred.conditionalBranchPred.tage
BPU_B1_CONFIG_SMOKE=PASS
BPU_SHIFT_EVIDENCE_SCOPE=DIRECTED_SMOKE_ONLY
BPU_SHIFT_KNEE=NOT_CLAIMED_SMOKE_ONLY
```

## Seed geometry proven by configuration gate

```text
bimodal entries        2048
tagged tables          3
entries/tagged table   512
history lengths        8 / 24 / 64
tag widths             8 / 9 / 10
```

The exact-history path therefore reaches the generated gem5 configuration as intended.

## Provenance caveat

The supplied pasted tail does not contain the preceding `git rev-parse HEAD` output. The remote branch was expected to be at `0577c23c2168bc4e30e23e3b008af4c549b9b0c7` for this smoke, but the pasted execution evidence does not independently attest the tested commit. Do not upgrade this to exact tested-HEAD provenance unless a manifest/log contains the SHA.

## Next gate

Run:

```bash
bash scripts/bpu_b1_embench_shift_audit.sh
```

This gate uses the fixed six-workload RV64 Embench set and compares TournamentBP at shift 0/1/2 using first-ROI:

- modeled cycles,
- simInsts consistency,
- conditional predictions,
- conditional incorrect predictions,
- conditional MPKI,
- BTB lookup/hit data,
- geomean cycle ratios,
- static RVC/control-PC audit,
- exact gem5/Embench provenance manifest.

Only after this gate should the PC-index shift policy be frozen for subsequent micro-TAGE geometry sweeps.
