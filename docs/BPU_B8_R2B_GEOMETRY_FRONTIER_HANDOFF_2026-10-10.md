# BPU-8 R2B — EXACT-ISO 5/6/7-table geometry frontier handoff (2026-10-10)

**STATUS: IMPLEMENTED / CI SOURCE-ONLY PASS / ACTUAL OCI RISCV GEM5 NOT RUN.**
**Source of truth:** `docs/bpu8_r2b_geometry_frontier_v01.json`, `scripts/bpu_b8_r2b_geometry_full19.py`, and `.github/workflows/bpu8-r2b-frontier.yaml`.

## Scientific question and boundaries

The original R1 Full-19 (190/190) and R2A Full-19 (209/209) first ROI have independent RAW archives audited. R2A strong mid60 (60,072 logical bits, GM ticks vs G5 ~0.988384435) still needs a budget-matched 5/6-table competitor before it can be treated as the 60-Kib logical-state geometry frontier. Other short and long reallocation paths, index-hash dependence, overfitting to the repeated Embench development set, SRAM macro area and lookup timing remain **OPEN**.

This preregistered R2B does **not** alter R1, R2A, historical Little CPU backend, TAGEBase C++ semantics, or BPU-7 C3 experiments. Its results are not available yet; no winner or global knee is claimed.

**Exact logical size:** `2728 + sum_i entries_i * (tag_width_i + 5)` bits (each TAGE counter3/useful2), fixed bimodal 2048 entries, history130, path16, other22. Every new bank depth must be a power of two.

### Registered equal-bit tiers and candidate identities

| Tier | Candidate | Entry sizes (short→long) | Histories | Tag bits | Exact bits |
| --- | --- | --- | --- | --- | ---: |
| B50 | frozen TG5-50 | 256/512/1024/512/1024 | 5/11/25/58/130 | 8/8/9/10/10 | 50,088 |
| B50 | frozen TG6-50 | 256/512/512/512/512/1024 | 5/10/20/39/75/130 | 8/8/9/9/10/10 | 50,088 |
| B50 | frozen TG7-50 | 256/512/512/512/512/512/512 | 5/9/15/25/44/76/130 | 8/8/9/9/9/10/11 | 50,088 |
| B53 | r2b_5a_53 | 256/1024/1024/256/1024 | 5/11/25/58/130 | 8/8/9/10/10 | 52,904 |
| B53 | r2b_5b_53 | 512/1024/512/512/1024 | 5/11/25/58/130 | 8/8/9/10/10 | 52,904 |
| B53 | r2b_6a_53 | 256/1024/512/512/256/1024 | 5/10/20/39/75/130 | 8/8/9/9/10/10 | 52,904 |
| B53 | r2b_6b_53 | 512/512/1024/512/512/512 | 5/10/20/39/75/130 | 8/8/9/9/10/10 | 52,904 |
| B53 | frozen R2A BOTH52 7-bank | 512/512/512/512/512/512/512 | 5/9/15/25/44/76/130 | 8/8/9/9/9/10/10 | 52,904 |
| B60 | r2b_5a_60 | 512/1024/1024/512/1024 | 5/11/25/58/130 | 8/8/9/10/10 | 60,072 |
| B60 | r2b_5b_60 | 512/512/2048/512/512 | 5/11/25/58/130 | 8/8/9/10/10 | 60,072 |
| B60 | r2b_6a_60 | 512/1024/512/512/512/1024 | 5/10/20/39/75/130 | 8/8/9/9/10/10 | 60,072 |
| B60 | r2b_6b_60 | 256/1024/1024/512/256/1024 | 5/10/20/39/75/130 | 8/8/9/9/10/10 | 60,072 |
| B60 | frozen R2A MID60 7-bank | 512/512/512/1024/512/512/512 | 5/9/15/25/44/76/130 | 8/8/9/9/9/10/10 | 60,072 |

Plus **3 non-iso historical anchors:** G5 45,736, stock TAGE 65,192, G7 65,192. Total **16 × 19 = 304 FIRST-ROI runs**; 2 selected smoke workloads ×16 = **32 runs**.

Tiers B53 and B60 have two distinct preselected 5-bank and two 6-bank allocations to expose entry-balance sensitivity rather than rank one arbitrary candidate per table-count. These **do not exhaust every possible TAGE geometry**, and 50K seven-bank tag width11 vs 53/60K width10 means the cross-tier increase is not a pure capacity experiment. Existing BPU-4 prior work showed joint parameter coupling. Comparisons **within a tier** have exactly equal logical state bits (14 preregistered pair comparisons), but do not control physical SRAM width, port count, bank count, M0 mux/access latency, switching power or hash folding.

## CI vs measured reality

Source CI validates Python syntax, R1+R2A+R2B source-only synthetic tests, 304/32 plan counts, no predictor C++ change, all SimObject geometry fixtures and immutable original R1/R2A control equality. It **does not** simulate an ISA workload. Strict runtime independently validates every actual gem5-generated config.ini for each selected profile (including TAGE counters, history lengths, maxNumAlloc, hash mode) plus first ROI SHA, metadata/rollback, exact bit sums and committed instruction count match to G5.

The R2B runner **REQUIRES** the SAME original R1/R2A `gem5.opt` SHA256 `96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced` before any simulation. Do not invoke a new recompile; reuse old R1 compiled binary with `--no-build --gem5`.

## OCI command transcript

**A. Isolated checkout and preflight**

```bash
cd "$HOME/gem5-bpu8-r2a"
git fetch origin refs/heads/little-v052-bpu8-r2b-geometry-frontier:refs/remotes/origin/little-v052-bpu8-r2b-geometry-frontier
git worktree add --detach "$HOME/gem5-bpu8-r2b" origin/little-v052-bpu8-r2b-geometry-frontier
cd "$HOME/gem5-bpu8-r2b"
git rev-parse HEAD
python3 -m unittest discover -s tests/bpu8 -p 'test_*.py' -v
python3 scripts/bpu_b8_r2b_geometry_full19.py --list | tail -1
python3 scripts/bpu_b8_r2b_geometry_full19.py --smoke --list | tail -1
GEM5="$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt"
sha256sum "$GEM5"
test "$(sha256sum "$GEM5" | awk '{print $1}')" = "96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced" || { echo "WRONG GEM5 EXECUTABLE"; exit 1; }
```

**B. Source-compatible 32-ROI smoke** (note: 2 pre-inspected workloads, NOT independent holdout)

```bash
cd "$HOME/gem5-bpu8-r2b"
set -o pipefail
python3 scripts/bpu_b8_r2b_geometry_full19.py \
  --no-build --jobs 2 --smoke \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu8_r2b_smoke_01" \
  2>&1 | tee "$HOME/bpu8_r2b_smoke_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2B_SMOKE_EXIT_CODE=$RC"
```

Expected **ONLY IF REAL GEM5 GATES PASS**:
```
ROI_CHECKED=32/32
BPU8_R2B_GEOMETRY_SMOKE=PASS
BPU8_R2B_ACTUAL_FRONTEND_ROI_REPRO=PASS
BPU8_R2B_SMOKE_EXIT_CODE=0
```

**C. Pre-registered 304-ROI Full-19** (only after valid smoke; no parameter edits triggered by 2-workload look)

```bash
cd "$HOME/gem5-bpu8-r2b"
set -o pipefail
python3 scripts/bpu_b8_r2b_geometry_full19.py \
  --no-build --jobs 2 \
  --gem5 "$HOME/gem5-bpu8-tage/build/RISCV/gem5.opt" \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu8_r2b_full19_01" \
  2>&1 | tee "$HOME/bpu8_r2b_full19_01.log"
RC=${PIPESTATUS[0]}
echo "BPU8_R2B_FULL19_EXIT_CODE=$RC"
```

Expected **ONLY IF** complete:
```
ROI_CHECKED=304/304
BPU8_R2B_GEOMETRY_FULL19=PASS
BPU8_R2B_ACTUAL_FRONTEND_ROI_REPRO=PASS
BPU8_R2B_FULL19_EXIT_CODE=0
```

## Raw archive

Keep unsuccessful profiles and original raw. Only with 304/304 pass, archive complete data:

```bash
cd "$HOME"
set -euo pipefail
test "$(find bpu8_r2b_full19_01 -type f -name roi.stats | wc -l)" -eq 304
test "$(find bpu8_r2b_full19_01 -type f -name config.ini | wc -l)" -eq 304
tar -czf bpu8_r2b_full19_evidence.tar.gz \
  bpu8_r2b_full19_01 bpu8_r2b_full19_01.log
sha256sum bpu8_r2b_full19_evidence.tar.gz
ls -lh bpu8_r2b_full19_evidence.tar.gz
```

Compare original archive SHA OCI→Windows→analyst, all raw stats/first ROI/settings, repeat historical 8 original anchors, record failures and worst tails, use unseen workload holdout and RTL/SRAM PPA before architectural freeze.

## Work continuation

1. Complete and independently audit R2B 304. Do not use the 2-workload smoke to select or delete a profile.
2. Analyze within-tier geometric means, W/L/T and tails; compare R2A mid60 vs exact-budget competitors for a bounded frontier.
3. Separate preregistered `fixedIndexHashLogSize` diagnostic on SAME geometries if source allows; never silently change this parameter inside R2B.
4. Unseen benchmark suite with prechosen, held-out, long workloads and traces.
5. Physical macro area, active lookup energy, bank mux depth and M0 timing across bank counts. Do not treat equal logical state count as area equivalence.
