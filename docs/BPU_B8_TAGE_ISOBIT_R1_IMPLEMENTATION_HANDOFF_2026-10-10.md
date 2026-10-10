# BPU-8 R1 — TAGE-only exact-bit geometry sweep implementation handoff

**Status 2026-10-10: IMPLEMENTED / Python CI PASS / real RISCV gem5 OCI smoke NOT RUN.**

This is a separate TAGE-only research experiment. It does not supersede the historical BPU-4A/B/C results, frozen Little v0.52 backend, completed BPU-7 C3 P0/P1/P2 evidence, the deferred (never run) C3 P3 G1-veto plan, or the unexecuted original 21-profile BPU-7 M1 matrix.

## Code and data ownership

- Registry is `docs/bpu8_tage_isobit_r1.json`; it defines 8 TAGE-only alternatives plus exact existing G7 and Stock reference profiles. G5 is profile `tg5_45` and uses the **unchanged** `tage5-iso45k` configuration rather than a rewritten G5.
- `configs/02_little_v052_rv64_proxy.py` reads the registry, constructs an unchanged `LittleTAGE5Iso45K` predictor wrapper for each of the **seven new** geometries, and sets TAGEBase parameters **before m5 instantiate**. No C++ TAGE algorithm, frontend correction timing or backend code changes.
- The runner `scripts/bpu_b8_tage_isobit_full19.py` uses the same 19 Embench binaries, first ROI and RV64 condition as BPU-4C. No simulator binaries or executable benchmarks are included in this repo.
- `tests/bpu8/test_tage_r1.py` verifies all logical-bit totals, mutation failure, first ROI parsing, and accounting invariants. CI is syntax+synthetic-only, NOT a gem5-linked RISCV integration result.
- G5 = 45,736 bits; new 45K alternatives exactly match G5. The 50K tier = 50,088 bits, deliberately identical to G5 + C3 P1 E256 logical bits; **the C3 P1 measurement was only counterfactual shadow, so it is not a 50K real-M1 cycles comparator**.
- Fixed state for proposed geometries: base 2,048 entries = 2,560b; global history 130b + path 16b; other 22b; tagged entry cost = tag-width + 3b direction + 2b usefulness. The state total is an architectural logical count, not a compiled SRAM area or dynamic power estimate.
- Since tables may be accessed in parallel, adding more banks at fixed bit count may increase tag-comparison, hash, mux and metadata costs. PPA is a separate mandatory stage.

## Safe OCI handoff: isolate all existing branches and evidence

From user's previously working OCI environment with existing benchmark corpus at `$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5`:

```bash
cd ~/gem5-bpu7-c3
git fetch origin refs/heads/little-v052-bpu8-tage-isobit-r1:refs/remotes/origin/little-v052-bpu8-tage-isobit-r1
git worktree add --detach "$HOME/gem5-bpu8-tage" origin/little-v052-bpu8-tage-isobit-r1
cd ~/gem5-bpu8-tage
git rev-parse HEAD
python3 scripts/bpu_b8_tage_isobit_full19.py --list | tail -1
python3 -m unittest discover -s tests/bpu8 -p 'test_*.py' -v
```

Then smoke (separate immutable output path; two preselected workloads × 10 profiles = 20 first ROIs):

```bash
set -o pipefail
python3 scripts/bpu_b8_tage_isobit_full19.py --jobs 2 \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --smoke --out "$HOME/bpu8_tage_smoke_r1" \
  2>&1 | tee "$HOME/bpu8_tage_smoke_r1.log"
RC=${PIPESTATUS[0]}
echo "BPU8_SMOKE_EXIT_CODE=$RC"
```

On smoke PASS only, the full experiment is the **same frozen geometry** with all 19 workloads × 10 profiles =190 first ROIs:

```bash
set -o pipefail
python3 scripts/bpu_b8_tage_isobit_full19.py --jobs 2 --no-build \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu8_tage_full19_r1" \
  2>&1 | tee "$HOME/bpu8_tage_full19_r1.log"
RC=${PIPESTATUS[0]}
echo "BPU8_FULL19_EXIT_CODE=$RC"
```

- New output paths are required when anything in a run configuration/source/build changes. `--resume` only accepts the **exact old manifest** including benchmark, build, repo HEAD, config and runner hashes. Failed run folders must be inspected and retained rather than silently reused.
- Results: output `manifest.json`, `results.csv`, `summary.txt`, and every profile/workload directory with `stats.txt`, `roi.stats`, `stdout.txt`, `stderr.txt`, `command.json`, `returncode.txt`, `.verified.json`.
- `BPU8_TAGE_ISOBIT_SMOKE=PASS` means 20 real gem5 first ROIs passed, not Full-19. `BPU8_TAGE_ISOBIT_FULL19=PASS` means 190 first-ROI geometries fully validated.
- Always report actual `storageBits` and subcomponent counts. If any profile fails to instantiate, crashes, reports a different size, changes committed instructions or fails metadata/history gates: **NO performance decision**; fix the source on a new commit, rerun with a new immutable output path.
- For publication: compute geometric mean from actual first ROI simTicks under identical clock, disclose each workload and worst tail, keep an unseen non-Embench holdout, perform physical RTL/PPA comparison. No post-result parameter search hidden in this pre-result R1 matrix.

## Candidate decisions and archival rule

Before marking a TAGE geometry rejected, record all 19 workload measurements, exact competitor and equal state budget, effect magnitude, first-ROI logs and immutable SHA256 archives in the [BPU-7 Evidence Ledger](https://app.notion.com/p/3f46f08ed244813dbcd6e9b46a261f31). Historical C3 P0/P1 remain *NEGATIVE SHADOW / HOLD*, P2 raw audit remains immutable, and P3 remains *DEFERRED UNRUN*. All 8 new shapes remain **UNTESTED on real gem5** until smoke/full19 outputs arrive.
