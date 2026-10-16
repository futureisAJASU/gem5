# Little v0.52 G0-A exact DIV matched-comparator pilot (2026-10-16)

Status: **IMPLEMENTATION STAGED / GEM5 EXECUTION OPEN**. New source is isolated on `research/g0-a-matched-div-20261016`, descendant of freeze commit `b5abd424cb49e59f13e011033b7bd4417c14af33`. Historical `LittleDivFU count=2/core` is unmodified.

## Modes

- `--g0-div-mode legacy` (default): historical model, no changed FU count.
- `--g0-div-mode private2`: new `LittleG0PrivateDivFU count=1` instantiated independently under each core, two total.
- `--g0-div-mode shared1 --pair-shared-div`: existing pair-shared non-pipelined 20-cycle pool, one total; RR enabled.

Both experimental variants require two cores, distributed IQ, local picker and an **explicitly disabled** gating control. W=0 is wake latency only, not a state-disable control. G0-A enforces effective `reactivePowerGating=false`, `predictiveWakeEnabled=false`, `rawPredictiveWakeEnabled=false`, `powerWakeLatency=0`, `powerIdleThreshold=8` in every constructed pool. `g0_fu_contract.py` emits `G0_CONSTRUCTED_MANIFEST_JSON` with FU OpClass/latency/II/coupling, and checks private/shared ownership. For each Pilot run, `g0_verify_effective_config.py` **also** checks actual emitted `config.ini`, an opt-in C++ post-construction inventory (`G0_CXX_FU_POOL`), and three shared-DIV wake counters zero. Missing evidence blocks the run rather than being imputed as zero. This C++ inventory is diagnostic-only and enabled solely when `LITTLE_G0_AUDIT_FU=1`.

## Execute on Linux RV64 gem5 host

This branch must be checked out in a separate gem5 worktree, never reset or clean existing historical experiments.

```bash
cd ~/gem5-g8i-xbar   # or any existing clone containing canonical commit
git fetch origin research/g0-a-matched-div-20261016
git worktree add --detach "$HOME/gem5-g0-a-20261016" origin/research/g0-a-matched-div-20261016
cd "$HOME/gem5-g0-a-20261016"
# A new build is needed if no compatible binary exists:
scons build/RISCV/gem5.opt -j4
bash configs/g0_run_div_pilot.sh
```

Requires `riscv64-linux-gnu-gcc`, `riscv64-linux-gnu-objdump`, and `build/RISCV/gem5.opt`.

Pilot cases: heavy/sparse, sparse/heavy, heavy/heavy, sparse/sparse, each run twice (PRIVATE2 and SHARED1). The script builds identical RV64IMAFD static ELFs, records their checksums, emitted DIV instructions, config, C++ physical FU count, effective wake controls, and stats, and **fails closed** on nonzero exit, missing evidence, nonzero shared wake counter, or divergent functional output. This is a **correctness smoke only**: it does not yet close the ten-case matrix, ISA DIV/DIVW/REM/REMW coverage, real ROI, time-to-completion, per-core wait histograms, run-to-run determinism, or representative benchmark performance.

### Current limits and negative controls

- The `configs/02_little_v052_rv64_proxy.py` 4-core `pair2` L2 implementation rejects two cores. The initial matched two-core DIV pilot uses **`shared4` L2** on both sides, explicitly **not** frozen final L2 topology. It isolates the DIV resource question within a matched cache proxy; a proper two-core PAIR2 mapping remains an integration task.
- `--n-skip -1` uses FULL visibility to isolate DIV. Frozen FIXED24 needs its own independent no-backfill implementation/verification for A3–A5. Do not call this pilot A5.
- Compiler `divu/remu` checks only establish instruction presence in ELF, not dynamic instruction counts. Dynamic DIV/REM counts, per-core completion time, contention/NoFreeFU/wait p50/p95 and pair makespan must be added before quantitative claims.
- `G0_A_CONSTRUCTION_AND_WAKE_GATE` (if actually executed successfully) establishes construction configuration only, not cycle-accurate whole-work performance/energy.
- Dynamic operation counts remain `null / OPEN` in the generated capability manifest; capability descriptions are OpClass names, not proof of executed RV64 instruction counts.
- No downstream data yet substantiates a DIV slowdown or energy improvement.
- The helper avoids concurrent per-core `m5_reset_stats`/dump ROI interference and currently measures the **whole multi-program system**, including launch/drain, as a smoke. Introduce an agreed coordinated ROI before paper figures.
- Existing block routed DIV `-42.303393%` at 3000ps is independent frozen PPA evidence, not a projected full-core saving.

## G0-B / I-EXEC carryforward

G0-B must compare A0 (FULL, 33313 first-fit, DIV1/core, **full private FP/SIMD** configuration, gating explicitly disabled) vs A5 (P21313 int1-first, literal FIXED24 no-backfill, DIV1/pair, **full pair-shared FP/SIMD backend**, gating explicitly disabled). The private FP-Mul/FMA FU also executes Div/Sqrt; the shared version splits Mul/FMA and Div/Sqrt onto different FU domains. This is not an FMA-only ablation. A separate `G0-C-FMA` must hold all other FP/SIMD capacities/latencies/ownership/resource-coupling constant while comparing 4 private vs 2 shared FMA lanes. For A6, shared-DIV-only B2 uses gating=true, raw hint=true, decode hint=false (subject to validated final source), T8/W4; it does NOT prove any FP/SIMD or physical power gating benefit. No A0/A5 performance claim from this pilot. Separately the available RTL `little_v052/flow/scripts/run_rtl_two_core_iexec_composition_tests.sh` establishes prior directed two-core functional closure, but neither a conventional wrapper nor new joint synthesis has been run in this G0 attempt.

## Explicit Addendum 2026-10-16 HIGH-1/HIGH-2 and measurement contract

The **binding authority** is Notion Execution Plan §29.5 / Checklist §21.1 / Contract v1.6 §§11,13–15. This experiment branch intentionally does **not** implement an A0↔A5 full-compute benchmark because the historical gem5 `--n-skip 4` is sliding, not the literal FIXED24 same-cycle snapshot. A new no-backfill implementation and directed verification are required before A3/A5 acceptance.

- For synchronized pair timing define `T_pair = max(T_core0_finish, T_core1_finish) - T_pair_start`, not a sum of per-core times and not a cycle-parity requirement. Capture both core completions and explicitly define optional drain.
- Pair weighted speedup needs standalone solo-reference cycle measurements for **each** constituent workload and a declared definition.
- A complete same-work energy window includes earlier-core idle time until later-core finish and, when specified, drain; dynamic, leakage and clock power measured on equivalent domains.
- The current pilot's `simTicks` comparison is **full simulation length only**; it is not per-core completion or aligned ROI. No G0-A slowdown, G0-B integrated PPA or energy claim is permitted yet.
- All source paths and generated outputs are kept outside the frozen branch; the final-tag architecture remains unchanged.

## Required diagnostic evidence per run

1. `G0_CONSTRUCTED_MANIFEST_JSON` from the Python construction gate.
2. `G0_CXX_FU_POOL` record after the actual C++ `numFU` constructor loop; enabled by `LITTLE_G0_AUDIT_FU=1`.
3. `config.ini` FUPool flags and FuDesc/OpDesc geometry, cross-compared with C++ inventory.
4. `stats.txt` for shared DIV `reactiveSleepTransitions=0`, `reactiveWakingSamples=0`, `reactivePowerBlockedRequests=0`; private counter absence is documented `UNOBSERVED`.
5. Same two printed result checksums, process exit code 0, ELF SHA and disassembly check.

If the reporter fails because gem5 names or serialized config structure differ, inspect the **real** emitted artifacts and fix the verifier in this experimental branch. Do not relax the evidence gate merely to get a green marker. The current source modifications have not yet been compiled or run with the RV64 gem5 simulator; all performance and C++ audit statuses remain OPEN.

## 2026-10-16 post-build manifest hotfix / host thread policy

Observed on OCI: `scons: done building targets`, but the first Python post-run
verifier stopped with `constructed capability manifest missing/duplicated`.
That traceback occurred after the verifier's checks of DIV ownership, each
FUPool's effective wake settings, C++ physical count, DIV capability, and the
applicable shared counter(s). The first completed simulator log therefore
*may* contain sound evidence, but this is not declared PASS without
successfully extracting and cross-verifying the actual manifest.

Changes:
- Removed unsupported `gem5.opt --version` invocation; binary SHA-256 and
  exact Git HEAD remain as version/provenance identifiers.
- The constructor now writes the whole manifest to a **new** per-run
  `constructed_fu_manifest.json` (exclusive create, fsync) and prints
  `G0_CONSTRUCTED_MANIFEST_FILE=... sha256=...`. The verifier checks the
  pathname, file bytes and SHA-256 against the log witness. Missing or
  inconsistent evidence means FAIL; no synthetic FU manifest backfill.
- Old simulator logs can be salvaged only if a complete
  `G0_CONSTRUCTED_MANIFEST_JSON=` object is truly present and decodable.
  In that case the recovered provenance is marked
  `LEGACY_LOG_JSON_RECOVERED_UNHASHED`, *not* a SHA-bound new artifact.
- G0-A execution still excludes performance/PPA acceptance until synchronized
  start/finish and dynamic operation counting are independently validated.

Host parallelism convention (future commands):
- OCI gem5 host: `scons build/RISCV/gem5.opt -j4` (4 compilation jobs).
- Dedicated OpenROAD server: 8 worker threads for supported OpenROAD/ORFS
  steps; do not assume `scons -j4` configures OpenROAD parallelism.

For a **previously completed** configuration-only run, the upgraded verifier
can be used directly without rerunning gem5. Choose the actual legacy run
folder (do not overwrite prior audit JSON):

```bash
python3 configs/g0_verify_effective_config.py \
  /path/to/old-root/heavy_sparse/private2 \
  --mode private2 \
  --json /path/to/old-root/heavy_sparse/private2/effective_config_recovered.json
```

If legacy JSON was truncated or missing, keep the original logs and run the
updated pilot to a fresh output directory. Do not manufacture a manifest
from the config file to close that gate.

```bash
git fetch origin research/g0-a-matched-div-20261016
cd "$HOME/gem5-g0-a-20261016"
git diff --quiet && git diff --cached --quiet || {
  echo "Worktree has tracked changes; abort fast-forward" >&2
  exit 1
}
git merge --ff-only origin/research/g0-a-matched-div-20261016
cd "$HOME/gem5-g0-a-20261016"
python3 -m unittest discover -s configs -p 'test_g0_contract_audit.py' -v
scons build/RISCV/gem5.opt -j4
bash configs/g0_run_div_pilot.sh
```

The starting worktree is detached by design. `git merge --ff-only`
advances the detached HEAD only when it is an ancestor of the remote branch.
It refuses a divergent history and does not invoke reset or clean.
Preserve any pre-existing untracked files; inspect a merge conflict instead
of forcing an update.
