# Little v0.52 BPU-4 A1D — Fixed-Hash Capacity Isolation Results

Status: **CLOSED / PASS**

Date: 2026-10-07 KST

## Executive result

The fixed-hash diagnostic confirms that the large BPU-4 A1 gains are dominated by **tagged-table capacity / alias pressure**, not by an accidental width-dependent remapping artifact.

The controlled experiment froze the tagged index transform at the native 2048-entry width (11 bits) while varying only physical capacity:

```text
e512   -> canonical 11-bit hash, low 9 bits used
e1024  -> canonical 11-bit hash, low 10 bits used
e2048  -> canonical 11-bit hash, all 11 bits used
```

All other micro-TAGE geometry remained fixed.

## Positive control

The diagnostic required fixed-11 e2048 to converge exactly with native e2048.

Result:

```text
BPU_B4_A1D_2048_NATIVE_CONVERGENCE=PASS
```

The equality gate covered cycles, committed instructions, committed conditional predictions, TAGE correct/wrong counts, selected-provider-bank vectors, and confidence vectors.

Therefore the controlled mode itself did not perturb the native e2048 predictor behavior.

## Controlled fixed-hash results

```text
workload             e512 cyc     MPKI  e1024 cyc    vs512%     MPKI  e2048 cyc    vs1024%     MPKI
statemate              568760   0.0036     568760     0.000   0.0036     568760      0.000   0.0036
crc32                 1568364   0.0432    1568364     0.000   0.0432    1568364      0.000   0.0432
nsichneu              1021403   0.0054    1021403     0.000   0.0049    1021393     -0.001   0.0045
slre                  1184094   1.7197    1182639    -0.123   1.6653    1182529     -0.009   1.6624
sglib-combined        1833069  22.3116    1612682   -12.023  14.2787    1392699    -13.641   6.7198
qrduino               1957686  22.1352    1893005    -3.304  20.1090    1809621     -4.405  17.6430
```

## Controlled vs native geometry effect

```text
512 -> 1024 controlled fixed-hash:  -2.67880% cycles
512 -> 1024 native geometry:        -2.65210% cycles

1024 -> 2048 controlled fixed-hash: -3.14621% cycles
1024 -> 2048 native geometry:       -3.22671% cycles
```

Difference in geomean effect:

```text
512 -> 1024:
  controlled - native = -0.02670 percentage points

1024 -> 2048:
  controlled - native = +0.08050 percentage points
```

These differences are tiny relative to the multi-percent capacity gains.

## Equal-capacity mapping sensitivity

Controlled fixed-11 vs native width-dependent mapping at the same physical capacity:

```text
e512  controlled/native geomean = -0.05570%
e1024 controlled/native geomean = -0.08312%
e2048 controlled/native geomean = +0.00000%
```

Largest workload-local mapping sensitivities observed in the six-workload subset:

```text
e512:
  sglib-combined  -0.797%
  slre            +0.327%
  qrduino         +0.150%

e1024:
  slre            -0.438%
  sglib-combined  -0.286%
  qrduino         +0.227%
```

Thus mapping sensitivity exists at the sub-percent workload-local level, but it is much smaller than the hard-workload gains from increased capacity.

## Mechanism conclusion

The evidence supports the following claim:

> The dominant cause of the 512 -> 1024 -> 2048 improvement is reduced tagged-table capacity/alias pressure and its downstream effects on residency, allocation, and provider behavior. Width-dependent remapping is measurable but secondary on the tested subset.

This is stronger than the native A1 result alone because the large gains persist under an invariant 11-bit index transform.

The diagnostic does **not** prove that every individual improvement is purely caused by one collision mechanism. TAGE training and allocation evolve nonlinearly, so native-minus-controlled is not treated as an additive causal decomposition.

## Provider/confidence evidence: e1024 -> e2048

No-rerun predictor-internal analysis on the native runs:

```text
sglib-combined:
  B0  -5.790 pp
  B1  -2.320 pp
  B2  +3.316 pp
  B3  +4.794 pp
  weak   -2.814 pp
  medium -1.101 pp
  strong +3.916 pp
  total TAGE errors -53.428%

qrduino:
  B0  -4.902 pp
  B1  -0.740 pp
  B2  +4.870 pp
  B3  +0.772 pp
  weak   -0.287 pp
  medium -0.418 pp
  strong +0.705 pp
  total TAGE errors -11.354%
```

Longest-match provider share also increases:

```text
sglib-combined:
  48.990% -> 54.879%

qrduino:
  62.321% -> 67.526%
```

This is consistent with larger tagged capacity preserving more useful longer-history contexts and reducing fallback pressure.

For `sglib-combined`, the improvement is especially strong:

```text
native MPKI:
  e512   22.9871
  e1024  14.4287
  e2048   6.7198
```

The fixed-hash diagnostic reproduces essentially the same trend:

```text
controlled MPKI:
  e512   22.3116
  e1024  14.2787
  e2048   6.7198
```

## Research consequence

A1D closes the principal interpretation ambiguity from the native geometry sweep.

The paper may state, with the appropriate scope:

> On the frozen six-workload subset, the performance gains from larger tagged tables persisted under a fixed index transform, indicating that reduced tagged-table capacity/alias pressure was the dominant mechanism rather than a favorable remapping artifact.

Do not generalize this claim beyond the tested workload subset without broader replay.

## Milestone state

```text
BPU-4 A1D fixed-hash diagnostic  CLOSED / PASS
BPU-4 A1 native capacity axis    OPEN
```

The native performance-knee rule still requires extension above 2048 because e2048 improves e1024 by 3.22671% geomean and violates the 2% next-larger workload guardrail.

A1D does not replace that endpoint rule.
