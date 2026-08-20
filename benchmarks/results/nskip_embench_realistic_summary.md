# Realistic Embench N-SKIP validation

## Scope

This result set validates bounded N-SKIP scheduling on the centralized 40-entry gem5 O3 proxy.

It is an algorithm/scheduler sensitivity experiment, not a validation of the final Little Core distributed queue topology.

N16, N32, and N39 are upper-bound/control points. They are not proposed Little Core queue sizes.

With IQ=40, N39 exposes offsets 0..39 and therefore acts as the full-visibility equivalence control.

## Reproducibility metadata

- gem5 branch: `little-v052`
- gem5 source HEAD before result commit: `547a4323adefdff81e490caa5a5e00dc4cd7126d`
- gem5 config: `configs/01_little_v052_proxy.py`
- gem5 config SHA256: `db7d16fe6c6ddcb70c78b8dd9080a85968173f2d06021580106468a4b8f4b570`
- gem5.opt SHA256: `0b5f20709d8f94cf568f2899d5794e89bd8f729d7bfef421d5f6b70c4f9ba0d0`
- Embench revision: `0466a18e4f6b47e19598d7c6ba72916d54b68f65`
- Embench tag: `embench-1.0`
- Embench CPU_MHZ scaling parameter: `1`
- Embench warmup heat: `1`
- benchmark links: static AArch64 GNU/Linux
- benchmark user libraries: gem5 `libm5.a` + `-lm`
- modeled clock: `1.4GHz`
- width / commit width: `3 / 3`
- ROB / IQ / LQ / SQ: `80 / 40 / 12 / 16`
- CheckerCPU: disabled for ordinary Embench runs

## ROI protocol

Embench performs benchmark initialization and cache warming before `start_trigger()`.
`start_trigger()` executes `m5_reset_stats(0, 0)`.
The benchmark body then runs inside the measured ROI.
`stop_trigger()` executes `m5_dump_stats(0, 0)` before verification and process exit.
Only the first `Begin Simulation Statistics` section is used. The second/final section is deliberately excluded because it includes post-ROI verification/exit activity.

## Workloads

- `matmult-int`
- `nettle-sha256`
- `nettle-aes`
- `sglib-combined`
- `wikisort`
- `picojpeg`

## Sweep

`stock`, `N0`, `N1`, `N2`, `N4`, `N8`, `N16`, `N32`, `N39`

Total measured ROI points: **54**.

## Aggregate cycle sensitivity

| config | geomean cycle ratio vs stock | geomean gap | median N0→stock recovery |
|---|---:|---:|---:|
| N0 | 1.378552 | +37.855% | 0.000% |
| N1 | 1.149579 | +14.958% | 54.684% |
| N2 | 1.087974 | +8.797% | 80.309% |
| N4 | 1.020895 | +2.089% | 98.001% |
| N8 | 1.000167 | +0.017% | 99.748% |
| N16 | 0.993883 | -0.612% | 99.995% |
| N32 | 1.000023 | +0.002% | 100.000% |
| N39 | 1.000000 | +0.000% | 100.000% |

## Per-workload gap to stock

| workload | N4 | N8 | N16 | N32 | N39 |
|---|---:|---:|---:|---:|---:|
| matmult-int | +0.000% | +0.000% | +0.000% | +0.000% | +0.000% |
| nettle-sha256 | -0.001% | -0.001% | -0.001% | +0.000% | +0.000% |
| nettle-aes | +3.355% | +0.714% | +0.036% | +0.000% | +0.000% |
| sglib-combined | +0.786% | +0.161% | +0.014% | +0.014% | +0.000% |
| wikisort | +0.601% | -1.934% | -3.665% | +0.000% | +0.000% |
| picojpeg | +8.033% | +1.190% | +0.004% | +0.000% | +0.000% |

## Validation gates

- All 54 ROI records are present.
- Architectural `simInsts` match across all nine configurations within each workload.
- No bounded configuration issues beyond its enabled N.
- N0 has zero bypass issues.
- N39 has zero N-SKIP window rejects and zero N-SKIP blocked cycles.
- N39 exactly matches stock cycles, IPC, and committed branch-mispredict counts for all six workloads.

## Interpretation

- N4 is a strong low-window candidate on this centralized proxy, but it is not proven optimal.
- N8 nearly recovers stock aggregate performance on this six-workload pilot.
- Deep ready instructions can exist well beyond N8/N16, but their frequency does not directly determine cycle benefit.
- The response is not strictly monotonic: for example, `wikisort` is faster than stock at N8/N16 and returns to stock at N32/N39 because bounded scheduling changes issue ordering.
- N39 exact stock equivalence closes the centralized N-SKIP full-visibility sanity check.
- These results must not be interpreted as proof that the final Little Core should implement N16/N32/N39.
- The next architectural validation stage should use the intended small/distributed queue domains.

## Validation status

**CENTRALIZED_EMBENCH_NSKIP_VALID**
