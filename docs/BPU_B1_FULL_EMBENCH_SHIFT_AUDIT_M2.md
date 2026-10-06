# Little v0.52 BPU-1C — Full Embench RV64 shift1/shift2 audit

Status: **PASS / ROOT-CAUSE DIAGNOSTIC REQUIRED BEFORE FREEZE**

Date: 2026-10-06 KST

## Full-corpus result

TournamentBP, fixed 4K direct-mapped BTB, first ROI, 19 Embench workloads:

```text
shift2/shift1 geomean cycle ratio = 0.984754553  (-1.52454%)
shift2 workload cycle wins/losses/ties = 13 / 1 / 5

shift1:
  condPredicted = 6,072,281
  condIncorrect =   268,599
  condMPKI      = 5.674837
  condAccuracy  = 95.576638%

shift2:
  condPredicted = 5,942,007
  condIncorrect =   214,306
  condMPKI      = 4.527759
  condAccuracy  = 96.393373%
```

The apparent corpus-level gain is dominated by one workload:

```text
nsichneu:
  shift1 cycles = 1,362,318
  shift2 cycles = 1,021,428
  cycle delta   = -25.0228%

  shift1 conditional MPKI = 26.4240
  shift2 conditional MPKI =  2.2054
```

Removing nsichneu, the remaining 18-workload geomean shift2 benefit is approximately **-0.0217%**, consistent with the earlier six-workload result (-0.01914%).

Therefore the -1.52454% headline is not a broad shift2 advantage. It is predominantly a pathological aliasing event exposed by nsichneu.

## Critical confound

The historical `--bp-inst-shift` parameter propagates to:

- TournamentBP conditional predictor indexing,
- SimpleBTB indexing,
- SimpleIndirectPredictor indexing.

Therefore the shift1/shift2 corpus sweep changed three predictor structures at once.

The observed nsichneu result cannot yet be attributed specifically to direction prediction.

## Static audit limitation

The full-binary objdump audit showed roughly:

```text
~48.5k 16-bit encoding lines per binary
~9.8k control-flow PCs with bit1=1 per binary
~50% of statically identified control PCs with bit1=1
```

These counts are highly similar across statically linked binaries, indicating that common runtime/libc/support code dominates the static disassembly. They establish that RVC and meaningful PC bit1 values exist, but must **not** be used as ROI workload-distribution evidence.

## Sweep-subset candidate

The predeclared shift1 TournamentBP conditional-MPKI rank produced:

```text
low:
  statemate
  crc32

median:
  cubic
  slre

high:
  qrduino
  nsichneu
```

This remains a **candidate**, not a frozen future sweep subset, because nsichneu's shift1 MPKI may itself be a pathological indexing artifact. Final subset freeze is deferred until the indexing policy is closed.

## Next diagnostic

The RV64 proxy now exposes independent controls:

```text
--bp-cond-shift
--bp-btb-shift
--bp-indirect-shift
```

Run:

```bash
bash scripts/bpu_b1_nsichneu_shift_factorial.sh
```

This executes a 2×2×2 factorial on nsichneu:

```text
conditional shift ∈ {1,2}
BTB shift         ∈ {1,2}
indirect shift    ∈ {1,2}
```

and reports:

- cycles,
- conditional MPKI,
- BTB hit rate,
- indirect hit rate,
- direct-conditional predictor/BTB misprediction counters when available,
- geometric main effects,
- emitted-config verification,
- exact provenance manifest.

No final PC-shift policy is frozen before this diagnostic.
