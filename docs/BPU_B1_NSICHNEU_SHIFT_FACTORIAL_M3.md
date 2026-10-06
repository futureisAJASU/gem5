# Little v0.52 BPU-1D — nsichneu split-shift factorial root cause

Status: **PASS / ROOT CAUSE IDENTIFIED**

Date: 2026-10-06 KST

## Result

A full 2×2×2 factorial was run on `nsichneu` using independently controlled shifts:

```text
conditional predictor shift ∈ {1,2}
BTB shift                   ∈ {1,2}
indirect predictor shift    ∈ {1,2}
```

Observed cycles and committed conditional-misprediction MPKI:

```text
c1 b1 i1   1,362,318 cycles   MPKI 26.4240
c1 b1 i2   1,362,318          MPKI 26.4240
c1 b2 i1   1,021,436          MPKI  2.2059
c1 b2 i2   1,021,436          MPKI  2.2059
c2 b1 i1   1,362,318          MPKI 26.4240
c2 b1 i2   1,362,318          MPKI 26.4240
c2 b2 i1   1,021,428          MPKI  2.2054
c2 b2 i2   1,021,428          MPKI  2.2054
```

Main effects:

```text
conditional shift2/shift1 = -0.000% cycles
BTB shift2/shift1         = -25.022% cycles
indirect shift2/shift1    = +0.000% cycles
```

BTB hit rate also changes strongly:

```text
BTB shift1 ≈ 33.23%
BTB shift2 ≈ 41.35%
```

## Root-cause conclusion

The `nsichneu` outlier in the earlier all-in-one `--bp-inst-shift` sweep is a **BTB indexing conflict/aliasing effect**, not a TournamentBP direction-indexing effect and not an indirect-predictor effect.

The conditional predictor itself is effectively insensitive to shift1 vs shift2 on this workload once BTB behavior is held fixed.

The dramatic `condIncorrect` / MPKI reduction observed with BTB shift2 must not be described as pure direction-predictor accuracy improvement: gem5's committed conditional incorrect counter includes branch mispredictions whose root cause can be target-side/BTB failure.

## Consequence for the BPU research methodology

For the direction-predictor geometry study, separate the controls:

```text
conditional predictor indexing : shift1
BTB proxy indexing             : shift2
indirect predictor indexing    : shift1
BTB geometry                   : 4K direct-mapped proxy
```

This is a **proxy experiment condition**, not a final-silicon BTB freeze. The final BTB capacity/associativity/indexing policy remains a later independent sweep.

Why keep conditional/indirect at shift1:

- RVC makes PC bit1 architecturally meaningful.
- The factorial shows no material benefit from discarding it in TournamentBP.
- Keeping shift1 avoids introducing a needless predictor-side indexing choice before micro-TAGE itself is studied.

Why use BTB shift2 in the proxy:

- The 4K direct-mapped proxy shows a severe, reproducible shift1 conflict pathology.
- shift2 raises nsichneu BTB hit rate by roughly eight percentage points and removes the 25% cycle penalty.
- The earlier 19-workload result is therefore mostly a BTB cleanup, not evidence for direction-predictor shift2.

## Full-corpus context

Earlier 19-workload all-shift2 vs all-shift1 geomean was -1.52454%.

Excluding `nsichneu`, the remaining 18-workload geomean shift2 benefit is only:

```text
0.999782901 ratio = -0.0217099%
```

This confirms that the corpus headline was almost entirely the single BTB pathology.

## Next closure gate

Run:

```bash
bash scripts/bpu_b1_canonical_index_closure.sh
```

It replays all 19 Embench workloads under:

```text
base   = conditional1 / BTB1 / indirect1
btb2   = conditional1 / BTB2 / indirect1
cond2  = conditional2 / BTB2 / indirect1
```

This will:

1. confirm the BTB-only effect across the full corpus;
2. confirm conditional shift2 adds no systematic value once BTB is fixed;
3. freeze the canonical proxy indexing condition for the micro-TAGE study;
4. reselect the future geometry-sweep workload subset under the corrected proxy condition.
