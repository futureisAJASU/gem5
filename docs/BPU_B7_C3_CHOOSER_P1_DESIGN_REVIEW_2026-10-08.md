# BPU-7 C3 PC_CHOOSER P1 — independent direction + learned selector (2026-10-08)

**Status: IMPLEMENTED FINITE C++ ENGINE + OPT-IN SHADOW WIRING; NOT M1 RUN-READY.** C1/C2/C4/C5/C7 and C3 HIST_TAG are untouched. Do not merge the current review-only implementation into the frozen `little-v052-bpu` branch.

- **Current separate review branch:** `little-v052-bpu7-c3-chooser-p1` (fork of `little-v052-bpu7-c3-pcbias-p0`).
- **Older OCI-build branch remains intact:** `little-v052-bpu7-c3-pcbias-p0`; the user is building that historical 16-bit/entry PC_RESIDUAL prototype, not this new P1.
- **Original design seed:** `docs/BPU_B7_C3_PCBIAS_P0_REVIEW_2026-10-08.md`. It models historical benefit of flipping prediction-time G5, not a stand-alone branch direction. It is kept as a separate negative/positive control.

## 1. Research question and why P1 is distinct

**A past G5 error is not proof that the next G5 prediction will be wrong.** PC_RESIDUAL increment/decrement approximates whether inverting G5 helped at earlier visits of the same PC. Such a score can lag a learning G5 or fluctuate with branch history. A correct binarily inverted outcome on an earlier event still does not establish the *future* conditional probability.

P1 therefore separates **two different learning problems**:
1. A *small independent PC-indexed direction predictor*: 2-bit saturating direction counter estimates taken/not-taken of the PC.
2. A *comparative chooser*: 2-bit saturating counter is trained from **prediction-time disagreements** between independent C3 and G5. When they disagree, only the one whose saved direction equals the actual committed outcome is correct. Both are scored on precisely the **same dynamic branch instance**.

**P1 selection rule:** only if G0 is eligible, the PC tag hits, the C3 direction counter is *strong* (0 or 3), C3 and G5 disagree, and chooser counter has reached **3**, request using C3 direction. Otherwise retain G5. This is a *hypothetical shadow request*; no late redirect or real performance improvement is implemented yet.

Thus P1 can still fail (history-dependent branches, concept drift, collision alias, changing TAGE training), but it has a meaningful, separately trained prediction/selection model rather than blindly treating a recent TAGE miss as a reason to invert.

## 2. Exact first-seed state and operations

| Field per entry | Bits | Meaning |
| --- | ---: | --- |
| valid | 1 | Reject cold/invalid predictions |
| truncated PC tag | 10 | Reject other PCs mapping to this entry (finite tag alias remains) |
| C3 direction | 2 | 0/1 not-taken, 2/3 taken |
| comparative chooser | 2 | 0/1 prefer G5, 2/3 prefer C3; P1 requires **3** to request |
| collision protection | 2 | Age existing entry only after demonstrated C3 wins; prevents immediate eviction by colliding PCs |
| **Total** | **17** | Logical committed predictor state only |

- E64 = **1,088 added bits**, G5+C3 = **46,824 bits**.
- E128 = **2,176 added bits**, G5+C3 = **47,912 bits**.
- E256 = **4,352 added bits**, G5+C3 = **50,088 bits**.
- `key = PC >> instShiftAmt` (RV64C-aware; canonical `instShiftAmt=1`).
- Index = `key & (entries-1)`; tag = `(key >> log2(entries)) & ((1<<10)-1)`.
- A branch that is **G0-ineligible** does not read C3 and does not train C3 later. G0 uses existing post-TAGE WEAK/MEDIUM/strength5 metadata: it **does not eliminate G5's own SRAM reads**.
- Cold allocation happens only on commit, sets independent direction to weak actual outcome (1 for N / 2 for T), chooser=1 preferring G5, protection=0.
- Every eligible committed conditional updates exactly one C3 row (either direction update, allocation or collision-protection decay); compare chooser only for a prediction-time tagged strong-direction disagreement.
- The independent direction is trained on actual outcome whether selected or not, so a new predictor can acquire enough evidence to become trusted. The chooser also trains on *disagreement* even before the chooser would have selected C3; avoiding this would deadlock chooser learning.
- The chooser update uses **snapshotted C3 and G5 directions from lookup time**, not the current direction counter at commit.
- Collision with different valid tag: if protection > 0, decrement protection and defer allocation; otherwise evict/allocate new weak row. Never consume the wrong PC's direction or chooser. If a formerly hit row was evicted before commit, record a stale prediction and never update the conflicting row's chooser as if it matched.
- **No speculative C3 row writes**; wrong-path branches may read, but squashed branches cannot train. TAGE speculative history and repair remain the canonical G5 implementation.

**Explicit limits:** `std::vector<Entry>` physical byte footprint is not 17 bits/row. Tag SRAM, read+write ports, C3+chooser read timing, in-flight lookup metadata/branch queue width, commit updates and RTL power require separate synthesis/physical accounting. P1 source-level implementation does not prove 1-cycle availability.

## 3. Checks and expected honest telemetry

New statistics from `src/cpu/pred/tage_base.cc`:
- `c3PcChooserReads`: actual auxiliary lookups, including wrong-path fetches.
- `c3PcChooserEligibleCommitted`, `c3PcChooserTagHits`, `c3PcChooserDisagreements`, `c3PcChooserWouldOverride`.
- `c3PcChooserWouldFix`, `c3PcChooserWouldBreak`: **hypothetical** per committed branch, never real accuracy gain.
- `c3PcChooserRowWrites`, `c3PcChooserDirectionUpdates`, `c3PcChooserChooserUpdates`, `c3PcChooserAllocations`, `c3PcChooserEvictions`, `c3PcChooserCollisionBlocked`, `c3PcChooserStalePredictions`.
- `c3PcChooserStorageBits` (stat Value survives ROI reset), plus `storageBits` includes correct added logical state.

Within a complete shadow ROI, require:
`wouldOverride = wouldFix + wouldBreak`; 
`wouldOverride <= disagreements <= tagHits <= eligibleCommitted`;
`chooserUpdates <= disagreements`;
`rowWrites = eligibleCommitted`;
`directionUpdates + allocations + collisionBlocked = eligibleCommitted`.
Actual `finalConditionalWrong` must equal `committedConditionalWrong`, **and** G5-only and C3 shadow must have identical instructions, cycles and real branch errors on the same binary/config. If not, stop and debug rather than reporting synthetic improvements.

**What PASS means right now:** GCC/Clang/UBSan directed tests of this production state machine and static Python/SimObject integration syntax. **NOT YET** gem5/RISCV fully linked build, actual G5 shadow equivalence, actual E64/E128/E256 ROI, or real M1 +1-cycle correction.

## 4. Artifacts

- `src/cpu/pred/little_c3_pc_chooser.hh` — finite independent C3 and chooser state machine.
- `tests/bpu7/c3_pc_chooser_directed.cc` — cold, G5-wrong-not-enough, strong direction, chooser trust/decay, no-update if gate off, alias and stale prediction, bounds.
- `src/cpu/pred/tage_base.{hh,cc}` — *opt-in* shadow instrumentation, no actual prediction override.
- `src/cpu/pred/BranchPredictor.py` + `configs/02_little_v052_rv64_proxy.py` — new explicit `tage5-c3-pcchooser-shadow-e64/e128/e256` bp types.
- `scripts/bpu_b7_c3_chooser_shadow_smoke.py` — intended G5 vs P1 same-binary equivalence; needs real RISCV simulator and binary.
- `.github/workflows/bpu7-c3-chooser-p1.yaml` — fast isolated C++/Python gates.

## 5. Open reviewer decisions BEFORE a frozen sweep

1. **Direction+chooser vs residual:** keep PC_RESIDUAL as a separate baseline, not quietly rename P1 as identical `PC_BIAS`.
2. **Learning eligibility:** training only under G0 may hide useful PC-bias evidence and lead to a cold chooser. G1-only/alternative trigger is a separate registered axis.
3. **Trust rule:** 2-bit chooser level 3 + strongly polarized direction is *conservative seed*, not proven optimum. E.g. under alternating workloads it may be so conservative that it never overrides.
4. **Collision policy:** 2-bit protection acts on comparator wins and is not part of original YAGS specification. Consider no-protection and alternative allocation policies in future registered axis studies.
5. **History context:** PC alone cannot represent correlations that depend on global history. C3 HIST_TAG is a separate important implementation, not a flag in this P1.
6. **Prediction-time causal validity:** on multi-thread or deep in-flight traffic, old snapshots can race with table replacement. Current tag matching blocks obvious stale training, but same-tag reallocation (ABA) requires an explicit stress audit at gem5 stage.
7. **Round-I scope:** 21 registered primary configurations do NOT include this new PC_CHOOSER by default. A numbered and frozen amendment is required to add it; no silent change to the existing 399 ROI, C3 six-profile matrix, or budget.

**Overall status: P1 SHADOW/REVIEW, NO MERGE, NO M1 CLAIM, OCI OLD BRANCH UNMODIFIED.**
