# Little v0.52 BPU-1B — Six-Workload RV64/RVC Shift Audit

Status: **PASS / POLICY NOT YET FROZEN**

Date: 2026-10-06 KST

## Evidence

Pinned Embench revision:

```text
0466a18e4f6b47e19598d7c6ba72916d54b68f65
```

All six workloads built as static RV64 GNU/Linux ELF with RVC enabled.

Static audit:

```text
workload         16-bit encoding lines   control PCs with bit1=1
matmult-int      48499                   9298
nettle-sha256    48499                   9298
nettle-aes       48499                   9298
sglib-combined   48499                   9298
wikisort         48509                   9300
picojpeg         48499                   9298
```

The audit demonstrates that compressed instructions are present and PC bit1 is not a globally constant-zero bit for control-flow instructions.

TournamentBP first-ROI results:

```text
workload           shift0 cycles   shift1 cycles   shift2 cycles   shift2/shift1
matmult-int        1340672         1340672         1340672          0.0000%
nettle-sha256      2780629         2780483         2780474         -0.0003%
nettle-aes         1945117         1945125         1945102         -0.0012%
sglib-combined     1716008         1719193         1718577         -0.0358%
wikisort            298501          298439          298388         -0.0171%
picojpeg           1658162         1652185         1651187         -0.0604%

shift2/shift1 geomean cycle ratio = 0.999808590 (-0.01914%)
```

Aggregate conditional direction statistics:

```text
shift0: condPredicted=1759245 condIncorrect=83125 condMPKI=3.804198 accuracy=95.274962%
shift1: condPredicted=1760136 condIncorrect=82779 condMPKI=3.788363 accuracy=95.297011%
shift2: condPredicted=1759975 condIncorrect=82619 condMPKI=3.781041 accuracy=95.305672%
```

Runner markers:

```text
BPU_B1_EMBENCH_SHIFT_AUDIT=PASS
BPU_SHIFT_POLICY_DECISION=DEFER_TO_EVIDENCE_REVIEW
BPU_B1_EMBENCH_SHIFT_PROVENANCE=PASS
```

## Interpretation

- shift0 is not attractive: with RV64/RVC, bit0 is architecturally zero and keeping it in the low index bits wastes useful index entropy.
- shift2 is not architecturally invalid. It deliberately discards meaningful PC bit1 while bringing one higher PC bit into the indexed bit slice.
- In this six-workload sample, shift2 weakly dominates shift1 in cycles and has slightly lower aggregate conditional MPKI.
- The gain is extremely small: -0.01914% geomean cycles versus shift1.
- Therefore this sample is insufficient to justify freezing shift2 solely from performance. It is also insufficient to reject shift2 merely because RVC exists.

## Next closure gate

Run `scripts/bpu_b1_full_embench_shift12.sh`.

This performs the full 19-workload Embench shift1/shift2 comparison and simultaneously profiles baseline conditional MPKI to select a fixed future BPU geometry-sweep subset by a predeclared rule:

```text
TournamentBP shift1 conditional-MPKI rank
→ 2 lowest + 2 median + 2 highest workloads
```

The final shift policy should be frozen only after that full-corpus result.
