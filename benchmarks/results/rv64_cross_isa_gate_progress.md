# RV64 Cross-ISA Replication Gate — Progress Snapshot

Branch: `little-v052-rv64-revalidation`

Validated through run source HEAD:
`3e9e9bcaa6074fb3a43b7234d92eb9fe859dbd80`

This note records directed RV64 replication evidence only. It does not claim
broad application-level ISA invariance or PPA/energy equivalence.

## 1. Centralized N-SKIP directed GAP replication

Directed workload:
- one long-latency serial `DIVU` producer
- GAP=0..8 younger dependent ALU operations
- six younger independent ALU operations
- self-checking bare RV64 Linux ELF

Sweep:
`stock, N0, N1, N2, N4` × GAP 0..8 = 45 runs.

All 45 runs exited with code 0 and bounded-window issue offsets obeyed N.

Normalized simTick overhead versus centralized stock:

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

Against the historical AArch64 directed GAP matrix, the 36 N0/N1/N2/N4
normalized-overhead cells have mean absolute difference ~0.037 percentage
points and maximum absolute difference ~0.077 percentage points.

Interpretation: the characteristic bounded-visibility staircase replicated
closely across AArch64 and RV64 for the same dependency topology.

## 2. P21313 distributed N-SKIP directed GAP replication

Frozen queue topology:
- INT0: 10 entries / dispatch cap 2
- INT1: 6 / cap 1
- MEM: 12 / cap 3
- DIV: 4 / cap 1
- FP/SIMD: 6 / cap 3
- first-fit IntAlu steering
- true local-IQ picker
- N4 means local Head..Head+4 visibility

All 45 distributed runs exited with code 0. N0/N1/N2/N4 max issued offsets
were exactly bounded by 0/1/2/4.

Normalized N4 simTick overhead versus distributed full-visibility stock:

| GAP | N4 overhead |
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

The distributed full-visibility stock path also matched the centralized
full-visibility stock path to within 0–2 simulated core cycles over GAP 0..8.

Interpretation: local queue partitioning allows N4 to preserve near-stock
performance through GAP5 in this directed workload, even though hidden-ready
work exists beyond local windows. This supports, but does not by itself prove,
the explanation that queue partitioning reduces the effective local blocking
distance and lets independent queues continue issuing.

## 3. N4 per-IQ hidden-ready attribution

Observation-only instrumentation:
- `nSkipLocalHiddenReadySamplesByIQ`
- `nSkipLocalNoVisibleReadyCyclesByIQ`

IQ map:
- IQ0 = INT0
- IQ1 = INT1
- IQ2 = MEM
- IQ3 = DIV
- IQ4 = FP/SIMD

Measured N4 results:

| GAP | H_INT0 | H_INT1 | H_MEM | H_DIV | H_FP | NV_INT0 | NV_INT1 | NV_MEM | NV_DIV | NV_FP |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 244 | 0 | 0 | 0 | 0 | 193 | 0 | 0 | 0 | 0 |
| 1 | 18,265,539 | 2,733,152 | 0 | 0 | 0 | 3,399,840 | 2,533,160 | 0 | 0 | 0 |
| 2 | 14,699,512 | 1,899,845 | 0 | 0 | 0 | 3,099,971 | 1,799,852 | 0 | 0 | 0 |
| 3 | 10,599,858 | 2,066,552 | 0 | 0 | 0 | 3,666,567 | 1,833,222 | 0 | 0 | 0 |
| 4 | 7,599,933 | 39 | 0 | 0 | 0 | 3,066,610 | 36 | 0 | 0 | 0 |
| 5 | 9,839,557 | 2,039,877 | 0 | 0 | 0 | 3,119,989 | 1,799,875 | 0 | 0 | 0 |
| 6 | 11,033,229 | 2,066,641 | 0 | 0 | 0 | 2,899,962 | 1,966,641 | 0 | 0 | 0 |
| 7 | 6,700,355 | 2,066,462 | 0 | 0 | 0 | 2,000,063 | 1,966,470 | 0 | 0 | 0 |
| 8 | 19,799,246 | 199,990 | 0 | 0 | 0 | 3,799,965 | 0 | 0 | 0 | 0 |

The hidden-ready pressure is therefore entirely attributable to the integer
queues in this workload. No hidden-ready events were observed in MEM, DIV, or
FP/SIMD.

At GAP8, 99.0% of hidden-ready samples are in INT0 and the per-IQ no-visible
condition is entirely INT0, coincident with the N4 performance gap rising to
~8.696%.

Caution: per-IQ no-visible cycle counts overlap in time and must not be summed
to infer global stall cycles. Hidden-ready samples are opportunity-pressure
observations, not direct critical-path stall counts.

## 4. Current gate status

- RV64 bring-up: PASS
- scalar RVV-off provenance: PASS
- raw IntDiv predecoder directed exactness: PASS
- pre-Decode squash lineage closure: PASS
- B0/B1/B2 directed wake behavior: PASS
- B2 useful wake-latency region: OBSERVED (directed)
- pair-shared DIV sustained fairness: PASS
- pair-shared DIV saturation sanity: PASS
- centralized N-SKIP cross-ISA directed replication: PASS
- P21313 distributed N-SKIP directed correctness/performance: PASS
- per-IQ local-visibility attribution: PASS

Next gate: realistic RV64 workload replication, keeping the AArch64 freeze
unchanged and treating qualitative conclusion survival—not numerical equality—
as the acceptance criterion.
