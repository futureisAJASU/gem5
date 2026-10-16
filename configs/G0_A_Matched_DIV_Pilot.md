# Little v0.52 G0-A exact DIV matched-comparator pilot (2026-10-16)

Status: **IMPLEMENTATION STAGED / GEM5 EXECUTION OPEN**. New source is isolated on `research/g0-a-matched-div-20261016`, descendant of freeze commit `b5abd424cb49e59f13e011033b7bd4417c14af33`. Historical `LittleDivFU count=2/core` is unmodified.

## Modes

- `--g0-div-mode legacy` (default): historical model, no changed FU count.
- `--g0-div-mode private2`: new `LittleG0PrivateDivFU count=1` instantiated independently under each core, two total.
- `--g0-div-mode shared1 --pair-shared-div`: existing pair-shared non-pipelined 20-cycle pool, one total; RR enabled.

Both experimental variants require two cores, distributed IQ, local picker and W0 always awake. A construction-time assertion checks per-pool counts and Python SimObject pool identity. **After simulator runs, inspect generated config.ini and physical FUPool construction to substantiate actual C++ count**; the marker alone is not proof of independently measured FU count.

## Execute on Linux RV64 gem5 host

This branch must be checked out in a separate gem5 worktree, never reset or clean existing historical experiments.

```bash
cd ~/gem5-g8i-xbar   # or any existing clone containing canonical commit
git fetch origin research/g0-a-matched-div-20261016
git worktree add --detach "$HOME/gem5-g0-a-20261016" origin/research/g0-a-matched-div-20261016
cd "$HOME/gem5-g0-a-20261016"
# A new build is needed if no compatible binary exists:
scons build/RISCV/gem5.opt -j2
bash configs/g0_run_div_pilot.sh
```

Requires `riscv64-linux-gnu-gcc`, `riscv64-linux-gnu-objdump`, and `build/RISCV/gem5.opt`.

Pilot cases: heavy/sparse, sparse/heavy, heavy/heavy, sparse/sparse, each run twice (PRIVATE2 and SHARED1). The script builds identical RV64IMAFD static ELFs, records their checksums, emitted DIV instructions, config and stats, and **fails closed** on nonzero exit, missing structure marker or divergent functional output. This is a **correctness smoke only**: it does not yet close the ten-case matrix, ISA DIV/DIVW/REM/REMW coverage, real ROI, time-to-completion, per-core wait histograms, run-to-run determinism, or representative benchmark performance.

### Current limits and negative controls

- The `configs/02_little_v052_rv64_proxy.py` 4-core `pair2` L2 implementation rejects two cores. The initial matched two-core DIV pilot uses **`shared4` L2** on both sides, explicitly **not** frozen final L2 topology. It isolates the DIV resource question within a matched cache proxy; a proper two-core PAIR2 mapping remains an integration task.
- `--n-skip -1` uses FULL visibility to isolate DIV. Frozen FIXED24 needs its own independent no-backfill implementation/verification for A3–A5. Do not call this pilot A5.
- Compiler `divu/remu` checks only establish instruction presence in ELF, not dynamic instruction counts. Dynamic DIV/REM counts, per-core completion time, contention/NoFreeFU/wait p50/p95 and pair makespan must be added before quantitative claims.
- No downstream data yet substantiates a DIV slowdown or energy improvement.
- The helper avoids concurrent per-core `m5_reset_stats`/dump ROI interference and currently measures the **whole multi-program system**, including launch/drain, as a smoke. Introduce an agreed coordinated ROI before paper figures.
- Existing block routed DIV `-42.303393%` at 3000ps is independent frozen PPA evidence, not a projected full-core saving.

## G0-B / I-EXEC carryforward

G0-B must compare A0 (FULL, 33313 first-fit, DIV1/core, FMA2/core, W0) vs A5 (P21313 int1-first, exact FIXED24, DIV1/pair, FMA2/pair, W0), same binaries/ROI/cache. No A0/A5 performance claim from this pilot. Separately the available RTL `little_v052/flow/scripts/run_rtl_two_core_iexec_composition_tests.sh` establishes prior directed two-core functional closure, but neither a conventional wrapper nor new joint synthesis has been run in this G0 attempt.
