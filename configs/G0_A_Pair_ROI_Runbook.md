# Little v0.52 G0-A synchronized two-core ROI — execution handoff (2026-10-16)

**Status: SOURCE STAGED / TARGET GEM5 BUILD AND RUNTIME OPEN.**
This is an *experimental descendant* of the already functionally tested
`research/g0-a-matched-div-20261016`, frozen final-tag ancestor
`b5abd424cb49e59f13e011033b7bd4417c14af33`.
Do not modify the frozen tag, prior 8-run evidence, or historical FU totals.

## Why this branch exists

The previous G0-A gate established actual 1 private DIV/core vs
1 pair-shared DIV, both wake-disabled, matching checksums and successful 8-run
configuration-only Pilot. That Pilot measured overall `simTicks`; it had no
common application ROI, no per-core finishes and no committed DIV OpClass
counts. It is **not** proof of the same-work performance tradeoff.

The two SE processes have **different address spaces**. An ordinary
user-space spin barrier over static memory is therefore **not shared**.
Similarly, two independent `rdcycle` reads / `m5_work_begin` exits do not
give a guaranteed common start.

## Exact isolated measurement contract

**Guests** (only `g0_div_roi_directed.c` with
`g0_pair_roi_markers.S`) issue two reserved ABI-compliant RISC-V gem5
pseudo-instructions:

- `workbegin(0x4730, 0)`: `.4byte 0xb400007b`, immediately before the
  measured hot loop.
- `workend(0x4730, 0)`: `.4byte 0xb600007b`, immediately after it.

The frozen gem5 `util/m5/src/abi/riscv/m5op.S` encodes operations with
`0x0000007b | (M5FUNC << 25)`, and the frozen generic m5ops header
assigns WorkBegin 0x5a and WorkEnd 0x5b.
The frozen `src/arch/riscv/isa/formats/m5ops.isa` generates this operation
with `['IsNonSpeculative', 'IsSerializeAfter']`. That is source-backed
evidence for an ordered marker; actual O3 Commit retirement boundaries
must still be checked from measured `committed_intdivs`.

**Simulator** (experimental `src/sim/pseudo_inst.cc` modifications):

- Only if `LITTLE_G0_PAIR_ROI=1` **and** `workid=0x4730`, intercept
  workbegin/workend. All prior paths retain historical semantics.
- CPU0/CPU1 identity is obtained from the **real**
  `tc->getCpuPtr()->cpuId()` (not guest-supplied `threadid`).
- First core at ROI entry is quiesced. When the second core reaches the
  entry, capture `pairStartTick = curTick()` and each core's committed
  baseline, then reactivate the first. Both therefore share the same
  simulator-global measurement origin.
- At each core's WorkEnd capture global `finishTick` and retired
  instruction delta. The early finisher is quiesced until the other finishes
  so guest `printf()/exit()` after WorkEnd cannot interfere with the still
  running kernel. On the second finish, print the pair summary and wake
  the first finisher.
- An O3 `CPU::instDone()` hook counts **committed**
  `opClass==IntDiv` within the active ROI for each core. Issued-but-squashed
  instructions must not be mistaken for executed work. Guest dynamic
  expectations remain a separate cross-check.

**Required markers in `simulator.log`:**

```text
G0_PAIR_ROI_READY core=0 ready_tick=...
G0_PAIR_ROI_READY core=1 ready_tick=...
G0_PAIR_ROI_SYNC start_tick=... ready0=... ready1=... clock_period_ticks=... early_core_idle_policy=quiesce
G0_PAIR_ROI_FINISH core=0 finish_tick=... pair_start_tick=... committed_insts=... committed_intdivs=...
G0_PAIR_ROI_FINISH core=1 finish_tick=... pair_start_tick=... committed_insts=... committed_intdivs=...
G0_PAIR_ROI_SUMMARY pair_start_tick=... finish0=... finish1=... pair_makespan_ticks=... clock_period_ticks=... first_finished_core=...
```

*Deterministic ordering may differ according to arrival/finish.* The strict
parser rejects missing/duplicate records, inconsistent timestamps, missing
config gate, mismatched dynamic IntDiv counts, checksum divergence and
invalid makespan. Same-tick two-core arrival is valid but not proof of
an exercised wait; the output records ready skew separately.

Define:

```text
T_core[i] = finishTick[i] - pairStartTick
T_pair    = max(finishTick[0], finishTick[1]) - pairStartTick
cycles_equiv = ticks / actual_core_clock_period_ticks
IPC[i]   = committed_insts[i] / cycles_equiv[i]
Slowdown_core[i] = T_core_shared[i] / T_core_private[i]
Slowdown_pair = T_pair_shared / T_pair_private
```

This is **not** a cycle-parity requirement. The same guest inputs/output and
executed DIV counts are required across modes, **not equal runtimes**.

Do not use `simTicks` here: it includes initialization and non-ROI libc
work, unlike the synchronized pair kernel. If core idle is used for
future power measurements, account explicitly for quiescence and clock
power, leakage and retention; **no energy claim is made by this model.**

## Commands on OCI (4 SCons workers)

Use a **new** worktree to leave the prior completed G0-A branch untouched:

```bash
cd ~/gem5-g8i-xbar
git fetch origin research/g0-a-pair-roi-20261016
git worktree add --detach "$HOME/gem5-g0-roi-20261016" \
  origin/research/g0-a-pair-roi-20261016
cd "$HOME/gem5-g0-roi-20261016"
python3 configs/test_g0_contract_audit.py -v
python3 configs/test_g0_pair_roi.py -v
bash -n configs/g0_run_div_roi.sh
scons build/RISCV/gem5.opt -j4

# First validate one mixed pair with PRIVATE2 and SHARED1:
G0_ROI_SMOKE=1 bash configs/g0_run_div_roi.sh

# If the first two-run gate passed, execute all 4 pairs x 2 modes:
bash configs/g0_run_div_roi.sh
```

The first and second invocations create **different new output
directories**, without deleting or overwriting any older result. The
full-run generated `pair_roi_summary.csv` contains per-core Runtime and
IPC, committed-instruction/DIV counts, pair makespan, core slowdown
and pair slowdown. Save the matching `manifest.txt`,
`effective_config_audit.json`, `constructed_fu_manifest.json`,
`simulator.log` and `stats.txt` for every run. The manifest records
exact git HEAD/binary/benchmark SHA.

OpenROAD host policy remains **8 threads**, but **no OpenROAD job is
launched by this gem5 branch**.

## Evidence limitations (must not be silently upgraded)

- Source code and synthetic parser tests are staged; the actual full
  simulator **has not yet been compiled or run on the new ROI branch**.
  Any unexpected `quiesce`, marker instruction decode or O3 commit timing
  must be investigated from real logs rather than disabled to force PASS.
- A first-core quiesce/resume is an experimental simulation control:
  demonstrate stable runs and vary asymmetric workloads before using
  this barrier as a general tool. Note possible marker/pipeline-boundary
  effects, and keep identical instrumentation in both compared modes.
- These are directed 3072-iteration synthetic loop results, not
  representative application-suite estimates.
- Solo reference baselines remain OPEN. Pair weighted speedup therefore
  remains `OPEN_NO_SOLO_BASELINES`, not a fabricated number.
- W0 uses all **three wake enables false**; it does not prove physical
  power state cells or switching energy.
- It isolates DIV by using `--n-skip -1` (FULL visibility) and a
  matched two-core `--l2-topology shared4` cache proxy. It is **not**
  Frozen FIXED24 or final PAIR2 L2.
- A4→A5 modifies the entire pair-shared FP/SIMD backend, not FMA only;
  no A0↔A5 integration or G0-C-FMA performance delta is claimed.
- This does not replace I-EXEC early timing synthesis, PAIR-FP0
  return-seam verification, representative energy, or integrated PPA.

## Source audit checklist

- Final reference: `src/sim/pseudo_inst.cc` workbegin/workend,
  `include/gem5/asm/generic/m5ops.h`,
  `util/m5/src/abi/riscv/m5op.S`.
- Barrier C++: `src/sim/pseudo_inst.cc`, committed DIV hook:
  `src/cpu/o3/cpu.cc`; declaration in `src/sim/pseudo_inst.hh`.
- Guest annotation: `configs/g0_div_roi_directed.c`,
  `configs/g0_pair_roi_markers.S`.
- 2-core simulator configuration: `configs/02_little_v052_rv64_proxy.py`
  `--g0-pair-roi`, `exit_on_work_items=false`.
- Runner/validator: `configs/g0_run_div_roi.sh`,
  `configs/g0_verify_pair_roi.py`, isolated
  `configs/test_g0_pair_roi.py`.

**Disposition before actual new gem5 logs: IMPLEMENTED-IN-BRANCH / SIMULATOR-UNVERIFIED / QUANTITATIVE RESULTS OPEN.**

## Build blocker resolved in source: OpClass enum qualification

The first OCI ROI-branch C++ build reported
`src/cpu/o3/cpu.cc:1196: error: 'IntDiv' was not declared in this scope`,
with compiler suggestion `gem5::enums::IntDiv`. The newly added
O3-commit instrumentation now compares to `enums::IntDiv` and explicitly
includes `enums/OpClass.hh`. This is limited to the experimental
measurement hook and does not change any FU counts/latencies/policies.
The G0 ROI CI has a static guard against the unqualified token.

**No subsequent OCI C++ compile or runtime success has been observed at the
time of this documentation update.** There is no reason to erase working
build objects; merge the fast-forward commit and resume with
`scons build/RISCV/gem5.opt -j4`. Run the two-mode smoke only after
the executable actually links successfully. Keep the historical G0-A
evidence unchanged.

## 2026-10-17: second actual OCI C++ build blocker, scoped fix

The next OCI `scons -j4` compile failed in
`src/sim/pseudo_inst.cc` at `std::array<Counter, 2>` and
`const Counter committed`. The same translation unit uses
`using namespace statistics;`; both `gem5::Counter` (signed 64-bit
instruction counter) and `gem5::statistics::Counter` (double) are visible.
`BaseCPU::totalInsts()` explicitly returns `gem5::Counter`.
The correct fix is **both** qualified declarations:

```cpp
std::array<::gem5::Counter, 2> startInsts{{0, 0}};
const ::gem5::Counter committed = tc->getCpuPtr()->totalInsts();
```

A separate `c++ -std=c++17 -Wall -Wextra -Werror -fsyntax-only`
minimal namespace/type reproduction passed; that is **not** proof of
full gem5 compilation. GitHub CI now fails the static source guard if
either qualifier is lost. No FU resource or architectural semantics
were changed.

During the same source audit the ROI runner's default output path was
found to have a literal `-$` suffix instead of a process ID.
It now uses `-$BASHPID`, and makes custom relative output paths
absolute before passing their paths to the constructor manifest writer.
A targeted Bash parsing/expansion smoke check passed.

The old 8-run G0 functional results remain valid and untouched.
The new synchronized ROI build **remains UNVERIFIED pending the next
complete OCI rebuild**, followed by a 2-mode smoke and eventually the
4-by-2 workload matrix.
