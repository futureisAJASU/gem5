# Little v0.52 / RV64 Cross-ISA Final-Freeze Preflight

Date: 2026-09-19  
Branch: `little-v052-rv64-revalidation`  
Current branch HEAD at dossier creation: `71ef27d0a3a1ecf4728801106712c5a1fae739f1`  
AArch64 frozen ancestor: `70098fb56c06b3b0296d29b2f4b177ce411c7561`  
AArch64 branch: `little-v052-g8i-xbar`

This document is the working handoff/preflight record for the final
architecture freeze. It separates:

1. **AArch64 pre-port canonical evidence**,
2. **RV64 cross-ISA replication evidence**,
3. **new RV64-only evidence added after the port**, and
4. **remaining gates before the final freeze**.

The acceptance rule for the RV64 gate is **qualitative conclusion survival,
not numerical equality**. The AArch64 frozen architecture is not to be tuned
merely to force RV64 numbers to match.

---

## 1. Architecture statement to preserve

The working design principle is:

> **Demand concurrency first. Shrink redundancy, not responsiveness.**

The intended two-core execution tile keeps scheduling state private/local while
sharing selected expensive execution resources pair-locally.

### Frozen/working scheduler topology

P21313 distributed IQ topology:

| IQ | Entries | Dispatch writes/cycle |
|---|---:|---:|
| INT0 | 10 | 2 |
| INT1 | 6 | 1 |
| MEM | 12 | 3 |
| DIV | 4 | 1 |
| FP/SIMD | 6 | 3 |

Other scheduler rules:

- integer steering: `first-fit`
- local-IQ picker enabled
- each IQ nominates its oldest READY + GRANTABLE candidate
- cross-IQ arbitration chooses among local nominees by age
- per-core issue width: 3
- N-SKIP `N=4` means local visibility `Head..Head+4`, i.e. at most
  5 valid/unissued positions
- the current final-freeze candidate remains **N4**, not N5/N6

### Pair-shared execution resources

Current model:

- integer divider: one physical non-pipelined divider per two-core pair,
  latency 20
- pair-shared scalar FP domains:
  - FP-Simple x2 / pair
  - FP-Mul/FMA x2 / pair
  - FP-Div/Sqrt x2 / pair
- SIMD x4 / pair and Matrix x1 / pair remain provisional in the proxy
- vector/FP rename state remains private per core

For two-unit fully non-pipelined shared domains, the implementation uses
home-lane arbitration; a requester may steal the peer lane only when the peer
has no protected pending/recent demand.

### Power/wake path

- B0: reactive sleep/wake
- B1: full-decode OpClass predictive wake
- B2: raw/predecode resource hint predictive wake
- B2 raw hint is **power-state only**
- full decoded OpClass remains the correctness/dispatch/FU-routing authority
- wrong-path raw hints are not rolled back; their cost is measured as lost
  sleep residency / expired speculative wake
- the encoding classifier is ISA-specific; the speculative wake policy and
  backend resource-management mechanism are not tied to AArch64 encoding

---

## 2. Common proxy parameters

Historical centralized Embench AArch64 proxy:

- modeled clock: 1.4 GHz
- fetch/decode/rename/dispatch/issue/wb/commit width: 3 where explicitly
  frozen; historical Embench manifest records width=3 and commit width=3
- ROB: 80
- centralized IQ: 40
- LQ: 12
- SQ: 16

Current RV64 proxy defaults preserve:

- clock 1.4 GHz
- width 3
- commit width 3
- ROB 80
- centralized IQ 40
- LQ 12
- SQ 16
- L1I 64 KiB default
- L1D 64 KiB default
- L1D MSHRs 16 default
- L2 total capacity default 1024 KiB in the generic config
- L2 assoc 8
- L2 MSHR total budget 20
- L2 XBar width 32 B default
- L2 XBar header latency 1 cycle
- downstream membus width 64 B

The generic config defaults are **not by themselves the final cache-capacity
freeze decision**. Cache topology/capacity remains a separate architecture
selection item below.

Repository source:
`configs/02_little_v052_rv64_proxy.py`.

---

# Part A — AArch64 pre-port canonical record

## 3. Centralized N-SKIP directed GAP sweep

Repository source:
`benchmarks/results/nskip_gap_stats_summary.md`.

Normalized cycle overhead versus full-visibility stock:

| GAP | N0 | N1 | N2 | N4 |
|---:|---:|---:|---:|---:|
| 0 | +0.063% | +0.043% | +0.034% | +0.013% |
| 1 | +9.504% | +0.044% | +0.035% | +0.016% |
| 2 | +14.235% | +9.479% | +0.037% | +0.016% |
| 3 | +9.079% | +9.044% | +9.036% | +0.019% |
| 4 | +9.079% | +9.044% | +9.036% | +0.019% |
| 5 | +13.570% | +9.044% | +9.036% | +9.017% |
| 6 | +8.684% | +8.672% | +8.667% | +8.648% |
| 7 | +8.684% | +8.672% | +8.667% | +8.648% |
| 8 | +12.994% | +8.672% | +8.667% | +8.648% |

All policies matched checksums and instruction counts for each GAP.

Interpretation frozen from this stage:

- N-SKIP produces the expected bounded-visibility staircase.
- N4 is not a universal full-visibility replacement in a centralized queue.
- Directed gaps beyond the visible range remain intentionally capable of
  exposing the bounded-window limitation.

## 4. Centralized AArch64 realistic Embench N-SKIP sweep

Repository sources:

- `benchmarks/results/nskip_embench_realistic_summary.md`
- `benchmarks/results/nskip_embench_realistic_full.csv`
- `benchmarks/results/nskip_embench_realistic_manifest.txt`

Reproducibility anchors:

- historical gem5 source HEAD before result commit:
  `547a4323adefdff81e490caa5a5e00dc4cd7126d`
- config: `configs/01_little_v052_proxy.py`
- Embench:
  `0466a18e4f6b47e19598d7c6ba72916d54b68f65`
- static AArch64 GNU/Linux
- ROI:
  - start = `m5_reset_stats(0,0)`
  - stop = `m5_dump_stats(0,0)`
  - first stats section only
- CPU_MHZ=1
- warmup_heat=1
- 54 ROI records
- all architectural `simInsts` matched across configurations
- N39 exactly matched stock cycles, IPC, and committed branch-mispredict
  counts for all six workloads

Aggregate:

| N | Geomean cycle ratio | Gap vs stock |
|---:|---:|---:|
| 0 | 1.378552 | +37.855% |
| 1 | 1.149579 | +14.958% |
| 2 | 1.087974 | +8.797% |
| 4 | 1.020895 | **+2.089%** |
| 8 | 1.000167 | +0.017% |
| 16 | 0.993883 | -0.612% |
| 32 | 1.000023 | +0.002% |
| 39 | 1.000000 | +0.000% |

Median N0-to-stock recovery at N4: **98.001%**.

AArch64 N4 per-workload gap:

| Workload | A64 N4 |
|---|---:|
| matmult-int | +0.000% |
| nettle-sha256 | -0.001% |
| nettle-aes | +3.355% |
| sglib-combined | +0.786% |
| wikisort | +0.601% |
| picojpeg | **+8.033%** |

Important interpretation:

- centralized N4 was already a strong low-window candidate
- `picojpeg` was the most N4-sensitive realistic workload
- N8 nearly recovered stock aggregate performance
- non-monotonic scheduling effects are real; e.g. wikisort became faster than
  stock at N8/N16 and returned to exact stock at N32/N39
- this experiment alone did **not** prove final distributed N4 optimality

## 5. AArch64 distributed-IQ/write-cap freeze evidence

Pre-port canonical freeze record:

P21313:
- INT0 10 / cap2
- INT1 6 / cap1
- MEM 12 / cap3
- DIV 4 / cap1
- FP/SIMD 6 / cap3

P21313 versus unrestricted `33313` comparison:

- geomean delta: **+0.218615%**
- arithmetic mean delta: **+0.220744%**
- maximum observed delta: **+2.511772%** on `cubic`
- directed FMA16 delta: **0**

This justified freezing the dispatch-write-cap vector as a constrained,
Little-oriented issue/dispatch structure. It was **not** a PPA proof.

AArch64 frozen ancestor commit:
`70098fb56c06b3b0296d29b2f4b177ce411c7561`
(`config(o3): freeze P21313 IQ write bandwidth`).

## 6. AArch64 pair-shared integer divider

Pre-port directed fairness record:

- core cycles: 41,081 vs 41,086
- cycle ratio: ~1.00012
- divider-busy ratio: ~1.00066

Safe conclusion:

- no meaningful service bias was observed in the directed stress case
- do not describe this as a theorem of zero latency overhead

Physical model:

- private DIV IQ per core
- one pair-shared IntDiv
- latency 20
- non-pipelined
- count 1 / pair

## 7. AArch64 pair-shared FP/FMA

Historical 16-FMADD directed result:

- total FMA: 262,144
- cycles: 138,729
- throughput: **1.8896 FMA/cycle**
- pair physical FP-Mul/FMA lanes: 2
- corresponding utilization relative to 2 FMA/cycle:
  approximately **94.48%**

Historical burst/persistence study dimensions preserved from the pre-port
record:

- burst sizes: 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192
- historical density points retained for RV64 reconstruction:
  25%, 37.5%, 43.75%
- prior qualitative observation: the sharing knee moved as sustained FP
  pressure increased; low-density/bursty regions were the intended favorable
  operating region, while sustained pressure exposed the throughput limit

The original AArch64 burst generator is not preserved in the current tree.
Therefore the exact old burst-density point-by-point numeric matrix must not
be invented. The current RV64 sweep is explicitly a reconstruction using the
preserved experiment dimensions.

## 8. AArch64 B0/B1/B2 predictive wake

B0 reactive directed latency sanity:

- after idle threshold T, domain enters Sleep
- sleeping demand pays wake latency W
- directed T8 cases:
  - W2 => +2 cycles
  - W4 => +4 cycles
  - W8 => +8 cycles

B1 Decode-stage prediction:

- at W4 the directed B1 path recovered the 4-cycle reactive WAIT/BURST
  penalty

B2 raw/predecode:

AArch64 IntDiv classifier:

- MASK = `0x7FE0F800`
- VALUE = `0x1AC00800`
- true positives = 133,162
- false positives = 0
- false negatives = 0
- 17 extra raw wake events were traced to instructions squashed before
  Decode, not classifier false positives

Directed timing summary:

- W4: raw/predecode approximately matched decode-stage predictive wake
- W8: raw was observed one modeled CPU cycle ahead of decode in the directed
  case

Correctness boundary:

- raw hint -> power state only
- full decode OpClass -> dispatcher/correctness

---

# Part B — RV64 cross-ISA replication

## 9. Port provenance and ISA controls

RV64 branch was created from the exact AArch64 frozen HEAD
`70098fb56c06...`.

Initial port commit:
`1421bb06d103` — `feat(rv64): add v0.52 cross-ISA replication proxy`.

ISA controls:

- CPU: `RiscvO3CPU`
- ISA: RISC-V
- scalar cross-ISA gate explicitly sets `RiscvISA(enable_rvv=False)`
- RVC remains supported because static GNU/Linux libraries may contain
  compressed instructions
- ordinary static Embench uses `bp_inst_shift=1`
- directed bare binaries independently verified without RVC may use
  `bp_inst_shift=2`

Relevant commits:

- `1267dcb67df6` disable RVV for scalar gate
- `560be25f7115` instantiate scalar ISA before createThreads

## 10. RV64 B2 raw IntDiv classifier and wake replication

Classifier:

- MASK = `0xFE004077`
- VALUE = `0x02004033`
- covers DIV/DIVU/REM/REMU and the W variants through the masked OP/OP-32
  structure

Decoder mapping was audited so:

- DIV
- DIVU
- REM
- REMU
- DIVW
- DIVUW
- REMW
- REMUW

map to `IntDivOp`.

Directed classifier/lineage record:

- core0 classifier hits: 18/18
- core1 classifier hits: 19/19
- classifier FP=0
- classifier FN=0
- aggregate raw events: 37
- reached Decode: 27
- pre-Decode squashes: 10
- B1 decode wake hints: 27

W4 lifecycle:

B1:
- hints 27
- transitions 12
- alreadyAwake 3
- alreadyWaking 12
- matched 10
- expired 2
- demandWhileWaking 0
- demandWhileAwake 10

B2:
- hints 37
- transitions 20
- alreadyAwake 5
- alreadyWaking 12
- matched 10
- expired 10
- demandWhileWaking 0
- demandWhileAwake 10

W4 timing:

- reactive: 17,706,486 simTicks
- decode: 17,684,352 simTicks
- raw: 17,684,352 simTicks
- simInsts: 11,966 for all three

At 1.4 GHz the 22,134-tick difference is about 30.99 modeled cycles for the
whole directed run.

Wake-latency sweep key anchors:

- W5: raw was about one modeled cycle faster than decode
- W7:
  - reactive = 17,706,486 ticks
  - decode = 17,706,486 ticks
  - raw = 17,684,352 ticks
- W8:
  - reactive/decode/raw all = 17,706,486 ticks

Interpretation:

- in this directed workload raw/predecode extended useful wake lead time
- at W7 decode no longer reduced end-to-end runtime versus reactive while raw
  still retained the lower-runtime result
- by W8 neither predictor was early enough
- this is an existence-case timing result, not a universal crossover theorem
- B2 carries extra speculative wake cost, visible in expired events; no
  joule/energy claim is made

Primary commits:

- `73273925a75b` raw RV64 classifier
- `8706233a1dfc` W4 compare
- `70d2f1968a58` lineage report
- `1b8b566b0505` B0/B1/B2 wake-latency sweep

## 11. RV64 pair-shared DIV fairness

Fairness workload/results:

- requester0 grants = **32,768**
- requester1 grants = **32,768**
- total grants = 65,536
- contended requester0 grants = **32,754**
- contended requester1 grants = **32,754**
- contended total = 65,508
- total service-count imbalance = 0
- contended service-count imbalance = 0
- simTicks = 935,941,188
- simInsts = 196,620

Caution:

`contended` means both requesters were pending according to pair-arbitration
state; it does not mean both requests necessarily arrived in the exact same
cycle.

Do not infer divider occupancy from naive `65536 * 20` arithmetic; the whole
simulation was about 1,310,317.7 modeled cycles while that naive product is
1,310,720. This is a simulator scheduling/measurement semantics warning, not
evidence of >100% physical divider occupancy.

Relevant commits:

- `5845f5b0debc`, `f8e9c7e08129`: fairness counters
- `682dc42a13cc`, `cfb337791ad1`, `a1339f296aaf`: workload/build/run

Status: **PASS**.

## 12. RV64 centralized directed N-SKIP replication

Repository progress source:
`benchmarks/results/rv64_cross_isa_gate_progress.md`.

45 runs:
`stock,N0,N1,N2,N4` x GAP0..8.

All exited 0 and all max issued offsets obeyed N.

RV64 normalized overhead:

| GAP | N0 | N1 | N2 | N4 |
|---:|---:|---:|---:|---:|
| 0 | +0.003% | +0.000% | +0.000% | +0.000% |
| 1 | +9.526% | +0.003% | +0.000% | +0.000% |
| 2 | +14.288% | +9.526% | +0.003% | +0.001% |
| 3 | +9.093% | +9.093% | +9.093% | +0.000% |
| 4 | +9.093% | +9.093% | +9.093% | +0.003% |
| 5 | +13.638% | +9.094% | +9.094% | +9.094% |
| 6 | +8.698% | +8.698% | +8.698% | +8.698% |
| 7 | +8.698% | +8.698% | +8.697% | +8.697% |
| 8 | +13.045% | +8.698% | +8.698% | +8.698% |

Versus AArch64, across the 36 N0/N1/N2/N4 cells:

- MAE ~ **0.037194 percentage points**
- RMSE ~ **0.041092 pp**
- max absolute difference ~ **0.077 pp**
- max difference location: GAP5/N4

Status: **strong directed cross-ISA replication**.

## 13. RV64 P21313 distributed directed N-SKIP

45 distributed runs passed.

N4 overhead versus distributed full visibility:

| GAP | RV64 P21313 N4 |
|---:|---:|
| 0 | ~0.000% |
| 1 | ~0.000% |
| 2 | ~0.000% |
| 3 | ~0.000% |
| 4 | +0.000% |
| 5 | +0.003% |
| 6 | +2.174% |
| 7 | +2.174% |
| 8 | +8.696% |

Distributed full-visibility stock differed from centralized full-visibility
stock by only 0-2 modeled core cycles in this directed GAP workload.

### Per-IQ hidden-ready attribution at N4

| GAP | H_INT0 | H_INT1 | NV_INT0 | NV_INT1 |
|---:|---:|---:|---:|---:|
| 0 | 244 | 0 | 193 | 0 |
| 1 | 18,265,539 | 2,733,152 | 3,399,840 | 2,533,160 |
| 2 | 14,699,512 | 1,899,845 | 3,099,971 | 1,799,852 |
| 3 | 10,599,858 | 2,066,552 | 3,666,567 | 1,833,222 |
| 4 | 7,599,933 | 39 | 3,066,610 | 36 |
| 5 | 9,839,557 | 2,039,877 | 3,119,989 | 1,799,875 |
| 6 | 11,033,229 | 2,066,641 | 2,899,962 | 1,966,641 |
| 7 | 6,700,355 | 2,066,462 | 2,000,063 | 1,966,470 |
| 8 | 19,799,246 | 199,990 | 3,799,965 | 0 |

MEM/DIV/FP hidden-ready and no-visible counts were zero in this directed
workload.

At GAP8:

- hidden-ready in INT0 = 19,799,246
- hidden-ready in INT1 = 199,990
- about 99.0% of hidden-ready pressure is INT0
- no-visible condition is entirely INT0
- N4 performance gap = +8.696%

Caution:

- hidden/no-visible are local visibility-pressure observations
- they are not global stall-cycle counts
- no-visible values may overlap across IQs

Relevant commits:

- `c1610876e35d` distributed GAP runner
- `92356205aac6`, `d54e3d9ae6d1`, `0ea5d5a84d1e` visibility stats
- `65c564769077`, `1faccbc18ea6`, `b6b49b87fa19` per-IQ attribution
- stale-build guard/fix:
  `14a540a658be`, `7faf6add0d9e`

## 14. RV64 realistic Embench — centralized stock vs N4

Exact Embench source revision was kept:
`0466a18e4f6b47e19598d7c6ba72916d54b68f65`.

RV64 build:

- static GNU/Linux
- `-O2 -march=rv64imafd -mabi=lp64d`
- binary may contain RVC from static runtime
- therefore `bp_inst_shift=1`
- ROI protocol matches historical Embench:
  reset stats at start, dump stats at stop, first stats section only

All 12 stock/N4 ROI runs verified.
All six stock/N4 `simInsts` matched.
N4 max offset <= 4.

| Workload | A64 N4 | RV64 central N4 | Delta RV64-A64 |
|---|---:|---:|---:|
| matmult-int | +0.000% | +2.744% | +2.744 pp |
| nettle-sha256 | -0.001% | -0.154% | -0.153 pp |
| nettle-aes | +3.355% | +0.707% | -2.648 pp |
| sglib-combined | +0.786% | +1.754% | +0.968 pp |
| wikisort | +0.601% | +1.773% | +1.172 pp |
| picojpeg | +8.033% | +13.390% | +5.357 pp |

Geomean:

- A64 central N4: **+2.089%**
- RV64 central N4: **+3.272%**

Interpretation:

- exact per-workload sensitivity is ISA/compiler dependent
- broad behavior survived
- `picojpeg` remained the most N4-sensitive workload in both ISAs

## 15. RV64 repeatability and centralized N4/N5/N6/N8 knee

The stock/N4 run was repeated.

All six workloads reproduced **exact cycle counts** for both stock and N4:

| Workload | stock | N4 |
|---|---:|---:|
| matmult-int | 1,340,672 | 1,377,457 |
| nettle-sha256 | 2,780,544 | 2,776,275 |
| nettle-aes | 1,945,125 | 1,958,879 |
| sglib-combined | 1,718,600 | 1,748,747 |
| wikisort | 298,440 | 303,731 |
| picojpeg | 1,652,214 | 1,873,438 |

Therefore these differences are deterministic under the frozen simulator,
binary, and configuration rather than run-to-run timing noise.

Centralized knee:

| Workload | N4 | N5 | N6 | N8 |
|---|---:|---:|---:|---:|
| matmult-int | +2.744% | +0.000% | +0.000% | +0.000% |
| nettle-sha256 | -0.154% | +0.137% | +0.307% | +0.171% |
| nettle-aes | +0.707% | +0.390% | +0.274% | +0.053% |
| sglib-combined | +1.754% | +1.460% | +1.199% | +0.980% |
| wikisort | +1.773% | +1.111% | +1.002% | +0.624% |
| picojpeg | +13.390% | +9.921% | +8.611% | +4.654% |

Geomean:

- N4: **+3.272%**
- N5: **+2.112%**
- N6: **+1.855%**
- N8: **+1.067%**

Centralized-only interpretation:

- most workloads already show a knee near N4
- matmult-int is a one-step N5-sensitive case
- picojpeg remains broadly window-sensitive even through N8
- picojpeg alone is insufficient justification to enlarge the final local
  window indefinitely

Commit:
`ede8c53836dc7f5b06cc6da69e348518e291224a`.

## 16. RV64 realistic Embench — final P21313 topology

This is currently the strongest realistic evidence for the final scheduler
topology.

24 verified runs:
`stock,N4,N5,N6` x six workloads.

All runs:

- self/benchmark verified
- `simInsts` match stock within each workload
- max issue offsets obey configured N

| Workload | P21313 N4 | N5 | N6 | N4->N5 improvement |
|---|---:|---:|---:|---:|
| matmult-int | **0.000%** | 0.000% | 0.000% | 0.000 pp |
| nettle-sha256 | +0.342% | +0.240% | +0.103% | 0.102 pp |
| nettle-aes | +0.141% | +0.028% | +0.004% | 0.113 pp |
| sglib-combined | +0.783% | +0.608% | +0.273% | 0.175 pp |
| wikisort | +0.441% | +0.446% | +0.398% | -0.005 pp |
| picojpeg | **+1.226%** | +0.654% | +0.021% | 0.571 pp |

Geomean:

- N4: **+0.488%**
- N5: **+0.329%**
- N6: **+0.133%**

This materially changes the interpretation of the centralized tail cases:

- matmult-int:
  - centralized N4 = +2.744%
  - P21313 N4 = **0.000%**
- picojpeg:
  - centralized N4 = +13.390%
  - P21313 N4 = **+1.226%**

Thus the N5 motivation seen in the centralized proxy is largely removed by
the intended distributed topology.

### Visibility counters in realistic P21313 N4/N5

N4 -> N5:

- nettle-sha256:
  - hidden: 1,643,161 -> 841,420
  - noVis: 158,142 -> 78,835
  - perf: +0.342% -> +0.240%
- nettle-aes:
  - hidden: 134,217 -> 68,401
  - noVis: 17,839 -> 5,404
  - perf: +0.141% -> +0.028%
- sglib-combined:
  - hidden: 494,071 -> 378,744
  - noVis: 150,863 -> 136,870
  - perf: +0.783% -> +0.608%
- wikisort:
  - hidden: 21,298 -> 7,300
  - noVis: 1,555 -> 1,068
  - perf: +0.441% -> +0.446%
- picojpeg:
  - hidden: 666,001 -> 251,384
  - noVis: 69,603 -> 8,773
  - perf: +1.226% -> +0.654%
- matmult-int:
  - hidden/noVis = 0/0 at N4 and N5
  - performance = 0% gap at N4/N5/N6

Key architecture conclusion:

> Hidden ready work beyond the local window does not map one-to-one to
> end-to-end performance loss. Distributed independent IQs can continue
> supplying issue opportunities even while one local queue has hidden ready
> work.

Current final-freeze choice: **keep N4**.

Reason:

- P21313 N4 geomean residual = only +0.488%
- worst observed realistic residual = picojpeg +1.226%
- N4->N5 geomean improvement = only 0.159 percentage points
- N5 does not produce a new clear aggregate knee in the final topology
- implementation/PPA cost of the larger compare/select window is not yet
  measured, so performance alone does not justify increasing N

Commit:
`8dbb548946a50aa0da63366e352e14d5810225c5`.

## 17. RV64 pair-shared scalar FMA saturation replication

Directed workload:

- 16 independent FMADD.D chains
- 8,192 iterations/core
- 131,072 FMA/core
- 262,144 FMA/pair
- final zero-result self-check
- static binary check: exactly 16 `fmadd.d` instructions
- directed binary has no RVC, so `bp_inst_shift=2`

Measured:

| Mode | simTicks | cycles | FMA/cycle |
|---|---:|---:|---:|
| private-fp | 50,077,104 | 70,107.9 | 3.739148 |
| pair-shared-fp | 93,817,458 | 131,344.4 | **1.995852** |

Pair-shared 2-FMA-lane efficiency:

- **99.793%** of 2 FMA/cycle

Private path has four pair-total FMA lanes; measured utilization relative to
4 FMA/cycle is approximately 93.48%.

Runtime ratio:

- shared/private = **1.873460**

Shared arbitration counters:

- total requester grants:
  - requester0 = 131,146
  - requester1 = 131,150
  - absolute imbalance = 4
- contended requester grants:
  - requester0 = 65,436
  - requester1 = 65,438
  - absolute imbalance = 2

The requester grant total is not an FMA-only count; setup/teardown FP-class
operations also use the shared backend. Do not label 262,296 total grants as
262,296 FMAs.

A64 historical reference:

- 262,144 FMA
- 138,729 cycles
- 1.8896 FMA/cycle
- ~94.48% of the pair 2-FMA/cycle limit

Cross-ISA conclusion:

- exact cycle equality is not required
- both ISAs sustain high utilization of the two physical shared FMA lanes
- RV64 directed run reached ~99.8% pair peak
- directed shared service counts show no meaningful requester bias

Relevant commits:

- `c512a3721004` FMA stress
- `5dd0d0f93515` build
- `ffa3ac1c97bf` runner
- `7a80ce580e2e` robust static FMA-count validation

Status: **PASS**.

---

# Part C — Cross-ISA comparison summary

## 18. What replicated strongly

### N-SKIP dependency topology

A64 vs RV64 directed centralized GAP:

- 36-cell MAE ~0.0372 pp
- max difference ~0.077 pp
- same bounded-visibility staircase

This is the cleanest direct cross-ISA replication.

### Pair-shared DIV fairness

A64:
- core-cycle ratio ~1.00012
- busy ratio ~1.00066

RV64:
- total grants 32768 / 32768
- contended grants 32754 / 32754
- measured service-count imbalance 0

Both support the same qualitative conclusion:
no meaningful pair-service bias was observed under sustained directed stress.

### Pair-shared FMA

A64:
- 1.8896 FMA/cycle on two pair-shared FMA lanes

RV64:
- 1.995852 FMA/cycle
- 99.793% of pair peak
- grant imbalance 4 total, 2 contended

Both support the same high-utilization shared-backend conclusion.

### B2

A64:
- exact classifier 133,162 TP, 0 FP, 0 FN
- 17 extra raw events traced to pre-Decode squashes

RV64:
- directed classifier exactness: 18/18 + 19/19
- 0 FP, 0 FN
- 37 raw events = 27 Decode-reaching + 10 pre-Decode squashes

Both support the same semantic boundary:
speculative predecode power hint, full decode correctness authority.

## 19. What changed numerically but did not reverse the conclusion

Central realistic N4:

- A64 geomean +2.089%
- RV64 geomean +3.272%

Per-workload sensitivity moved substantially:
matmult and AES roughly traded sensitivity, while picojpeg stayed the worst
case.

This is expected to remain described as ISA/compiler-dependent instruction
stream behavior rather than ISA-independent performance.

## 20. New evidence stronger than the old pre-port record

The realistic RV64 P21313 run is stronger than the old centralized-only
realistic N-SKIP evidence for the final scheduler combination:

- central RV64 N4 geomean +3.272%
- P21313 RV64 N4 geomean +0.488%
- central picojpeg +13.390%
- P21313 picojpeg +1.226%
- central matmult +2.744%
- P21313 matmult 0.000%

This supports the architecture-level claim that bounded local visibility and
distributed partitioning should be evaluated together rather than treating
N-SKIP as an isolated centralized-queue trick.

It does **not** prove a causal PPA advantage and does not show that every
workload will receive the same benefit.

---

# Part D — Current gate status

## 21. PASS / OPEN table

| Gate | Status | Evidence |
|---|---|---|
| RV64 bring-up | PASS | static RV64 workloads execute |
| RVV-off scalar provenance | PASS | explicit ISA object |
| RVC-aware BP shift | PASS | shift1 for glibc, shift2 only verified bare binaries |
| RV64 raw IntDiv classifier | PASS | FP=0/FN=0 directed |
| pre-Decode squash lineage | PASS | 10 RV64 raw squashes accounted |
| B0 reactive wake | PASS | latency sweep |
| B1 decode predictive wake | PASS | W4 useful |
| B2 raw predictive wake | PASS directed | W7 useful lead-time existence case |
| pair-shared DIV fairness | PASS | exact grant split |
| centralized directed N-SKIP | PASS | very close A64/RV64 matrix |
| P21313 directed N-SKIP | PASS | 45 runs + attribution |
| realistic central N-SKIP | PASS | six Embench |
| run-to-run reproducibility | PASS | exact stock/N4 cycles |
| realistic P21313 N4 | PASS | +0.488% geomean |
| N4 vs N5/N6 sensitivity | PASS | final topology favors keeping N4 |
| pair-shared FMA saturation | PASS | 1.995852 FMA/cycle |
| pair-shared FMA fairness | PASS directed | grant imbalance 4/2 |
| FMA burst/density cross-ISA persistence | **OPEN; runner ready** | next immediate gate |
| A64 final-topology realistic P21313 replay | OPEN / recommended | closes symmetry of synergy claim |
| RV64 P21313 vs unrestricted write-cap control | OPEN / recommended | confirms P21313 cap choice across ISA |
| combined-feature two-core integration sanity | OPEN / recommended | final integration gate |
| 4-core/L2 cross-ISA sanity | OPEN / lower priority | cache is not paper centerpiece |
| RTL PPA/energy | OUT OF CURRENT GEM5 FREEZE | cannot claim from proxy |

---

# Part E — Immediate next run already prepared

## 22. RV64 pair-shared FMA burst-density sweep

Current branch HEAD contains:

- `f1f77f6ee20d` — reconstruction workload
- `e64f1c9a68c0` — build historical matrix
- `71ef27d0a3a1` — burst-density cross-ISA runner

Files:

- `benchmarks/src/rv64_fma_burst_density.S`
- `scripts/rv64_pair_shared_fma_burst_density.sh`

Run:

```bash
cd /home/ubuntu/gem5-g8i-xbar
git pull
bash scripts/rv64_pair_shared_fma_burst_density.sh
```

Matrix:

- nominal densities:
  - 25.00%
  - 37.50%
  - 43.75%
- bursts:
  - 16
  - 32
  - 64
  - 128
  - 256
  - 512
  - 1024
  - 2048
  - 4096
  - 8192
- private/shared for each point
- total = **60 simulations**
- each point executes the same total scalar-FMA count:
  - 172,032/core
  - 344,064/pair

The nominal density is a reconstructed payload-period ratio, not a literal
measured hardware FU duty cycle.

Outputs include:

- private cycles
- shared cycles
- slowdown
- shared FMA/cycle
- percent of 2-FMA/cycle pair peak
- requester grant imbalance
- contended grant imbalance
- contended grant fraction
- per-density persistence summary
- CSV + manifest + binary hashes

Acceptance rule:

- do not require exact AArch64 numeric equality
- look for the same qualitative transition:
  sharing is relatively favorable at lower/intermittent FP pressure, while
  long persistent bursts expose the two-lane shared throughput ceiling
- fairness should remain near-balanced across long contention intervals
- any qualitative reversal must be investigated before freeze

Important provenance warning:

the old AArch64 burst generator is not preserved; this RV64 workload is an
explicit reconstruction of the historical experiment dimensions. Do not
present the RV64 points as bit-for-bit reproduction of an unavailable A64
generator.

---

# Part F — Remaining roadmap before final freeze

## 23. Gate R1 — finish FMA burst/density persistence

Priority: **highest / next command**.

After the 60-run sweep:

1. archive `summary.csv`, manifest, binary hashes
2. record the density/burst transition shape
3. compare to the historical A64 qualitative knee
4. inspect any requester/contended imbalance outlier
5. if no reversal, mark pair-shared FP cross-ISA gate CLOSED

Do not retune FP lane count to match A64 numbers.

## 24. Gate R2 — AArch64 P21313 realistic replay

Priority: **highly recommended before final freeze**.

Reason:

The strongest new architectural result is the interaction:

`distributed P21313 + local N4`

which reduced RV64 N4 geomean from +3.272% centralized to +0.488%.

The pre-port realistic Embench record was centralized. Therefore, if the final
paper uses the architecture-level “combination” result prominently, replaying
the same six-workload P21313 N4/N5 control on AArch64 closes the remaining
cross-ISA asymmetry.

Minimum matrix:

- six historical A64 Embench workloads
- distributed P21313
- full-visibility stock
- N4
- optionally N5 as sensitivity control

Primary freeze question:

> Does AArch64 also show that P21313/local partitioning materially suppresses
> the large centralized N4 tail without a major qualitative reversal?

This is more valuable than expanding to many new workloads before freeze.

## 25. Gate R3 — RV64 write-cap control

Priority: **recommended**.

Re-run the final P21313 topology against an unrestricted dispatch-cap control
analogous to the historical `33313` study.

Historical A64 anchor:

- geomean +0.218615%
- mean +0.220744%
- max +2.511772% on cubic
- FMA16 0%

RV64 acceptance:

- no requirement to match +0.218615%
- require no broad/significant reversal showing P21313 caps are pathological
  on RV64
- retain exact per-workload `simInsts` equality and correctness checks

If RV64 remains low-overhead, the P21313 cap vector can be frozen with much
stronger cross-ISA support.

## 26. Gate R4 — combined two-core execution-tile integration

Priority: **recommended final integration gate**.

The mechanisms have individually passed, but final freeze should include at
least one run where they coexist:

- P21313 distributed IQ
- N4
- pair-shared DIV
- pair-shared FP/SIMD
- pair-local arbitration
- B0/B1/B2 power-state machinery enabled as intended

The test does not need to invent a new headline benchmark. Its role is to
ensure no interaction regression between:

- local scheduler nomination
- shared FU NoFreeFU retry behavior
- pair arbitration
- predictive wake state
- squash/recovery

Required checks:

- correct exit/self-check
- no stale-binary continuation after failed build
- no issue beyond N4
- requester accounting sane
- no deadlock/livelock
- deterministic rerun

## 27. Gate R5 — cache/L2 cross-ISA sanity

Priority: **lower than scheduler/FU gates**.

Pre-port G8I work already exposed:

- L2 topology: shared4 / pair2 / private4
- XBar width: 32 B / 64 B
- header latency: 1 cycle
- default-equivalence validation passed across six configs
- explicit header-latency=1 validation passed
- 64 B runs completed for private4/shared4/pair2

The paper should not turn L2 into the central contribution; it is an
architecture operating-point validation.

Before final cache freeze, explicitly record the chosen:

- total L2 capacity
- topology
- MSHR budget
- XBar width
- tag/data latency
- prefetch setting

The generic RV64 config default of 1 MiB shared4 must not be silently mistaken
for the final architecture choice.

If the intended paper architecture uses a 2 MiB/pair-oriented L2 point, make
that choice explicit and cite the AArch64 sweep evidence; otherwise leave the
cache claim as a validated proxy parameter rather than a novel mechanism.

## 28. Gate R6 — final reproducibility/freeze package

Before tagging final freeze:

1. rebuild from clean tree
2. run the selected compact regression set
3. require `git diff --check`
4. require clean working tree
5. record exact HEAD
6. record `gem5.opt` SHA256
7. record every benchmark ELF SHA256 used in headline figures
8. record compiler versions
9. record ISA flags
10. record exact config/CLI for each headline result
11. write final result manifests
12. tag/freeze the revision and stop retuning from RV64 numerical differences

Recommended compact final regression:

- RV64 raw IntDiv smoke
- B0/B1/B2 W4 and key latency sweep anchors
- DIV fairness
- directed GAP N0/N1/N2/N4
- six-workload P21313 N4
- scalar FMA saturation
- selected burst-density anchor points after R1
- any final AArch64 replay points added in R2

---

# Part G — Proposed final freeze statement if remaining gates pass

## 29. Scheduler

Freeze candidate:

- distributed P21313
- local picker
- first-fit integer steering
- issue width 3
- N4 local Head..Head+4 visibility

Current strongest performance evidence:

- RV64 realistic P21313 N4 geomean residual: **+0.488%**
- worst of six: **picojpeg +1.226%**
- matmult-int: **0.000%**
- N5 geomean: +0.329%
- N6 geomean: +0.133%

Therefore N5/N6 remain sensitivity controls, not current architecture choices.

## 30. Pair-shared integer divide

Freeze candidate:

- one 20-cycle non-pipelined divider per two-core pair
- private DIV scheduling queues
- pair-local arbitration
- predictive power-state support

Cross-ISA fairness evidence is consistent and strong.

## 31. Pair-shared FP

Freeze candidate:

- scalar Simple x2/pair
- Mul/FMA x2/pair
- Div/Sqrt x2/pair
- private FP/SIMD scheduling state
- pair-shared expensive physical execution

Current scalar-FMA saturation evidence:

- A64: 1.8896 FMA/cycle
- RV64: 1.995852 FMA/cycle

Do not convert the 4->2 FMA lane-count reduction into a “50% FP area saving”
claim. Only the modeled physical FMA lane count was halved; routing, rename,
scheduler, simple FP, divide/sqrt, SIMD, matrix and arbitration costs remain.

## 32. Predictive wake

Freeze mechanism:

`Raw ResourceHint -> power only`

`Full Decode OpClass -> correctness/dispatcher`

A64 classifier:
- mask `0x7FE0F800`
- value `0x1AC00800`

RV64 classifier:
- mask `0xFE004077`
- value `0x02004033`

The classifier encoding is ISA-specific. The backend policy is the portable
architecture mechanism.

## 33. Claims that remain out of scope

Do not claim from the current gem5 proxy alone:

- RTL area optimum
- physical timing closure
- energy/joule savings
- exact leakage reduction
- ISA-independent performance
- universal fairness theorem
- universal B2 wake-latency crossover
- 50% total FP-block area saving
- exact 4-core RTL-equivalent implementation

The current validated scope is a gem5 architecture model of a two-core
execution tile plus separately modeled four-core frontend/cache structures.

---

# Part H — One-line continuation state

At this dossier's creation, the branch is at:

`71ef27d0a3a1ecf4728801106712c5a1fae739f1`

and the immediate next action is:

```bash
cd /home/ubuntu/gem5-g8i-xbar
git pull
bash scripts/rv64_pair_shared_fma_burst_density.sh
```

After that output is captured, update this dossier with the 60-point
burst-density results, close/open the FP persistence gate, then proceed to the
AArch64 P21313 realistic replay and RV64 write-cap control before the final
freeze.
