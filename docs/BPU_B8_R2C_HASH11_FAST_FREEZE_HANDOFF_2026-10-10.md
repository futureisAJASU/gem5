# BPU-8 R2C — Short fixed-hash11 gate before returning to auxiliary predictor

**STATUS: SOURCE IMPLEMENTED, PRE-REGISTERED, GITHUB SYNTHETIC CI 16/16 PASS; OCI FIRST ROI NOT RUN.** Do not confuse canonical G5 (5-bank 45,736 bits) with the current best full19 7-bank configurations, or freeze any candidate before measured validation. No original R1/R2A/R2B file or C++ TAGEBase was modified.

## Why R2C is intentionally small

RAW audit already completed for BPU-8 R1 190, R2A 209, and R2B 304 actual first ROI. Re-running all native-hash0 controls a fourth time is low value. Instead, the R2C runner independently verifies and reuses the entire **original R2B 304-ROI RAW directory** for every relevant native control, and reruns only **7 matched geometries with fixedIndexHashLogSize=11** plus one native canonical G5 baseline for reproducibility. The 7×19 original native/geometry comparators come from previously measured R2B RAW. **8 profiles ×19 = 152 actual new first ROIs**, smoke 8×2=**16**. There are 7 one-factor hash0↔hash11 pairs (identical geometry) and 2 equal-bit 6-vs-7 table pairs under hash11.

**Hash11 is safe in the historical gem5 source:** TAGEBase requires `fixedIndexHashLogSize >= log2(physical tagged entries)` and `fixedIndexHashLogSize > bank index`. The tested shapes have up to 1024 entries (some earlier R2B shapes had 2048, but excluded) and at most seven tagged banks. The original fixed-log hash implements common-width folding and still masks physical table depth. The native `fixedIndexHashLogSize=0` implementation remains untouched. **Hash11 is a research diagnostic mode, NOT a proposed hardware design or free logical area optimization.**

## Pre-registered variants

| Native original R2B RAW profile | Fixed-hash11 new profile | Bits | Interpretation |
| --- | --- | ---: | --- |
| tg5_45 (canonical G5) | tg5_45_h11 | 45,736 | tests five-bank G5 index-hash dependence |
| tg7_50 | tg7_50_h11 | 50,088 | tests 7-bank best 50K |
| r2a_both52 | r2a_both52_h11 | 52,904 | tests 7-bank 53K |
| r2b_6b_53 | r2b_6b_53_h11 | 52,904 | tests competing 6-bank 53K |
| r2a_mid60 | r2a_mid60_h11 | 60,072 | tests 7-bank 60K |
| r2b_6b_60 | r2b_6b_60_h11 | 60,072 | tests competing 6-bank 60K |
| g7 | g7_h11 | 65,192 | tests high-bit G7 index-hash sensitivity |

Also rerun original native tg5_45 (no hash11) once per workload as G5 first-ROI execution and inst-count control. This should match the raw R2B tg5_45 19/19 exactly or **fail closed**.

**Predeclared comparisons:** native-vs-hash11 for all 7 identities, then fixedHash11 7-bank vs 6-bank at 52,904 and 60,072 bits, both exact logical state. Report full 19 geomean simTicks and W/L/T/worst, and hot3 vs other16 as *descriptive* only. No post-result profile deletion or Geometry retuning. Preserve all negative outcomes.

## Runtime source-level gates

- Same previously observed Embench 19 (NOT a holdout), first-ROI only.
- SHA256 of simulator must be **`96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced`**, original R1/R2A/R2B. No new compilation permitted in instructions.
- `--native-r2b-dir` points to original **`$HOME/bpu8_r2b_full19_01`**, mandatory (not a newly regenerated CSV). Before a single new gem5 execution the script checks original R2B immutable manifest experiment, scope, commit, SHA of original R2B preregistered matrix, gem5/each ELF SHA, exactly 304 rows, original `.verified.json`/ROI SHA/first-ROI bytes/CSV for all planned native comparators and workloads.
- Each new run must pass actual instantiated `config.ini` including per-bank histories, entries, tags, hash11 setting; complete ROI, metadata, rollback and state accounting and matching `simInsts`, committed conditionals and total bit count vs same native control; G5 control matches original R2B RAW on all 13 core fields. Invalid data must halt execution and leave original files intact.
- Source CI [workflow file](../.github/workflows/bpu8-r2c-hash11.yaml) checks 16 Python tests across R1/R2A/R2B/R2C, 152/16 planning and additive-only hash11 config. **CI success does not mean new gem5 simulation performed.**

## OCI commands (isolated worktree)

```bash
cd "$HOME/gem5-bpu8-r2b"
git fetch origin refs/heads/little-v052-bpu8-r2c-hash11-freeze-gate:refs/remotes/origin/little-v052-bpu8-r2c-hash11-freeze-gate
git worktree add --detach "$HOME/gem5-bpu8-r2c" origin/little-v052-bpu8-r2c-hash11-freeze-gate
cd "$HOME/gem5-bpu8-r2c"
git rev-parse HEAD
python3 -m unittest discover -s tests/bpu8 -p 'test_*.py' -v
python3 scripts/bpu_b8_r2c_fixed_hash_full19.py --list | tail -1
python3 scripts/bpu_b8_r2c_fixed_hash_full19.py --smoke --list | tail -1
test -f "$HOME/bpu8_r2b_full19_01/manifest.json"
test -f "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt"
sha256sum "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt"
```

Expected `BPU8_R2C_JOBS_PLANNED=152 FULL19=True`; `BPU8_R2C_JOBS_PLANNED=16 FULL19=False`.

**16-ROI smoke**:

```bash
cd "$HOME/gem5-bpu8-r2c"
set -o pipefail
python3 scripts/bpu_b8_r2c_fixed_hash_full19.py \
  --no-build --jobs 2 --smoke \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --native-r2b-dir "$HOME/bpu8_r2b_full19_01" \
  --out "$HOME/bpu8_r2c_hash11_smoke_01" \
  2>&1 | tee "$HOME/bpu8_r2c_hash11_smoke_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2C_SMOKE_EXIT_CODE=$RC"
```

Expected *only after complete actual execution*: `ROI_CHECKED=16/16`, `BPU8_R2C_HASH11_SMOKE=PASS`, `BPU8_R2C_ACTUAL_FRONTEND_ROI_REPRO=PASS`, exit 0.

**152-ROI Full19**, only if smoke passed and no parameter retuning:

```bash
cd "$HOME/gem5-bpu8-r2c"
set -o pipefail
python3 scripts/bpu_b8_r2c_fixed_hash_full19.py \
  --no-build --jobs 2 \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --native-r2b-dir "$HOME/bpu8_r2b_full19_01" \
  --out "$HOME/bpu8_r2c_hash11_full19_01" \
  2>&1 | tee "$HOME/bpu8_r2c_hash11_full19_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2C_FULL19_EXIT_CODE=$RC"
```

Expected only on real success: `ROI_CHECKED=152/152`, `BPU8_R2C_HASH11_FULL19=PASS`, `BPU8_R2C_ACTUAL_FRONTEND_ROI_REPRO=PASS`, exit 0.

**Raw evidence closure:**

```bash
cd "$HOME"
set -euo pipefail
test "$(find bpu8_r2c_hash11_full19_01 -name roi.stats -type f | wc -l)" -eq 152
test "$(find bpu8_r2c_hash11_full19_01 -name config.ini -type f | wc -l)" -eq 152
tar -czf bpu8_r2c_hash11_full19_evidence.tar.gz \
  bpu8_r2c_hash11_full19_01 bpu8_r2c_hash11_full19_01.log
sha256sum bpu8_r2c_hash11_full19_evidence.tar.gz
```

Upload original archive with OCI SHA, transfer to Windows and hash again; independently audit source and native R2B actual ROI.

## BPU freeze checkpoint — avoid blocking auxiliary predictor indefinitely

1. **Research baseline checkpoint only** after R2C RAW audited: TAGE-only geometries, budget and native hash config immutably labeled for subsequent predictor correction experiments. Maintain G5 as canonical historical baseline and Pareto contenders TG7-50/BOTH52/MID60/G7 as distinct identities; do **not** relabel a 7-bank winner "G5" or rewrite frozen Little v0.52 dossier.
2. If fixedHash11 produces rank reversal (same-budget 6-bank beats 7-bank) or unexpected large population changes, document dependence and decide hash choice explicitly **before** any model freeze. If not, retain original native hash0 as the baseline and proceed to auxiliary correction experiments in a new branch even though silicon signoff remains pending.
3. **Never claim final ASIC BPU macro PPA or universal knee** until fresh unseen holdout across a controlled corpus and true RTL SRAM area/critical lookup path/energy are studied.
4. Historic BPU-7 C3/P1 shadow-only negatives are preserved; helper predictor must be tested with actual M1/proxy integration, accounting, speculative recovery and fair first ROI. No old shadow outcome can be silently reclassified as full M1 evidence.
