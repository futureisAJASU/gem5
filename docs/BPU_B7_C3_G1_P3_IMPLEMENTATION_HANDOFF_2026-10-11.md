# Little v0.52 — BPU-7 C3 P3 G1 STRONG5 Veto OCI Handoff (2026-10-11)

**STATUS: implementation source committed; CI status must be checked from GitHub Actions. OCI benchmark is NOT RUN. Real N+1 M1 frontend correction / RTL PPA are NOT implemented.**

## Evidence custody / immutability
- The user-described 378-line Markdown handoff `Little_v052_BPU_R1-R2C_G5_LOCK_C3_HANDOFF_2026-10-11.md`, SHA256 `e6240cb0201d0af1fc95d826e170e1927c36d999ca60a587e1f7fb24c89d36a8`, exists as a Notion *index entry*; its exact original bytes were **not reattached** in this conversation. Notion index: https://app.notion.com/p/3f66f08ed2448122a4fcd6eb1dd9d625
- Research comparator G5 is **tage5-iso45k**, FIVE tagged banks, 45,736 persistent logical bits, `fixedIndexHashLogSize=0` native; G7 seven-table 65,192-bit candidate retained independently. This is not frozen CPU RTL or silicon.
- R1 190/190 ORIGINAL first ROI RAW independent audit PASS (330,016 checks), R2A 209/209 RAW audit PASS (369,512), R2B 304/304 RAW audit PASS (544,562). R2C 152/152 first-ROI *console independently recomputed* and 16/16 Smoke PASS, original ROI stats/config archive **not yet independently RAW audited**. These are the historic research evidence, not new P3 results.
- P0 SHADOW original E64/E128/E256 net `-1650/-1491/-1367`; P1 SHADOW `-447/-414/-281`. P1 E256 `2803 fix / 3084 break`. NEVER report these as measured corrected frontend cycles.
- P2 trace 258,016 G0-eligible committed events is **WHOLE EXECUTION** NOT first-ROI. Four exploratory workloads WEAK net +363, MEDIUM net +2, STRONG providerStrength5 net -510; posthoc subgroup statistics justify *preregistration*, not a prediction of P3 Full19 result. P2 qrduino whole trace +40 whereas first-ROI -37, clear example of incompatible denominators.
- P1 A→B→A same-tag in-flight stale training (**ABA**) remains **UNFIXED**. Preserve existing directed exposure test; generation protection is a separate budget/semantics change. C3 not globally rejected.

## P3 pre-result frozen experiment
Reference Notion: https://app.notion.com/p/3f46f08ed2448164a802ee0489fe4c89

Exactly 8 profiles×19 unchanged RV64 Embench = **152 first-ROI**; 2-workload `--smoke` selects huffbench and qrduino across all 8 = **16 smoke ROI**. Exact persistent logical storage bits:
| Profile | Name | Bits |
| --- | --- | ---: |
| G5 | `tage5-iso45k` | 45,736 |
| G7 | `tage7-iso65k` | 65,192 |
| P1 E64/E128/E256 | `tage5-c3-pcchooser-shadow-e*` | 46,824 / 47,912 / 50,088 |
| P3 G1 E64/E128/E256 | `tage5-c3-g1-strong5-veto-e*` | 46,824 / 47,912 / 50,088 |

These exclude the cost of G1 combinational logic, fanout, transient branch-history snapshot, SRAM macro and ports. No read-energy reduction is expected from *acceptance-only* veto because G0 read already occurred.

G0 original eligibility and C3 chooser lookup, training, updates, allocation and eviction remain intact. G1 operates on **prediction-time snapshot** only when original P1 has `wouldOverride`: veto exactly `providerConfidence==STRONG && providerStrength==5`. Committed first-ROI counters include original raw proposal fix/break, accepted fix/break, vetoed fix/break and per-confidence breakdown. Enforce exact raw=accepted+veto and fix/break conservation; P1 and P3 must show identical original read/write/chooser/stale/G5 ticks, instructions and mispredictions at matched size and benchmark. Source tests cannot replace these simulation assertions.

G1 doesn't change `finalPred`, fetch direction, cycles, or actual history speculative rollback. A positive accepted shadow net for any E requires fresh, independent real M1 design with N+1 redirect/history rollback/ABA closure and physical area/energy/timing verification before performance claims. If all three E sizes <=0 accepted net, stop only this narrow G1 variant; do not reject whole C3 family. Full19 is already inspected development corpus, **not unseen holdout**.

## OCI commands (execute manually on machine with existing pinned Embench binaries)
```bash
cd "$HOME/gem5-bpu7-c3"
git fetch origin little-v052-bpu7-c3-g1-strong5-veto-p3
git worktree add --detach "$HOME/gem5-bpu7-c3-p3" origin/little-v052-bpu7-c3-g1-strong5-veto-p3
cd "$HOME/gem5-bpu7-c3-p3"

python3 scripts/bpu_b7_c3_p3_g1_full19.py --list
python3 scripts/bpu_b7_c3_p3_g1_full19.py --smoke --list

# 16 first-ROI Smoke — isolated evidence output; compiles new linked RISCV binary
python3 scripts/bpu_b7_c3_p3_g1_full19.py --smoke --jobs 2 \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu7_c3_p3_g1_smoke_01"

# 152 first-ROI Full-19; separate immutable evidence directory
python3 scripts/bpu_b7_c3_p3_g1_full19.py --jobs 2 \
  --embench-build "$HOME/gem5-bpu7-c3/benchmarks/external/embench-iot/bd-rv64-gem5" \
  --out "$HOME/bpu7_c3_p3_g1_full19_01"
```

`--resume` requires matching original immutable run manifest, binary hashes, exact command and per-case `.verified.json`. Never overwrite an old failed/incomplete output. Source-ci and linked build must independently pass. OCI 16 Smoke/152 Full19 must **not** be labelled PASS until actually run and inspected.

## Original RAW archival after actual execution
```bash
cd "$HOME"
test "$(find bpu7_c3_p3_g1_full19_01 -name roi.stats | wc -l)" -eq 152
test "$(find bpu7_c3_p3_g1_full19_01 -name config.ini | wc -l)" -eq 152
tar -czf bpu7_c3_p3_g1_full19_evidence.tar.gz bpu7_c3_p3_g1_full19_01
sha256sum bpu7_c3_p3_g1_full19_evidence.tar.gz
```
Retain originals including `stats.txt`, `roi.stats`, `config.ini`, stdout/stderr, `command.json`, `manifest.json`, `results.csv`, per-case verified SHA snapshots, and independently measured source/ELF/build hashes. Console summaries alone are not original RAW audit.
