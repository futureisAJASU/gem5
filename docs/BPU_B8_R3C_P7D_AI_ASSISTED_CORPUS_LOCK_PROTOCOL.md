# BPU-8 R3C P7D — AI-assisted review, no-result corpus lock, Git-HEAD preflight

**Status 2026-10-13:** Source staged in branch; OCI execution pending. Do not label P7D as PASS until its actual shell log is obtained.

## Why this bounded review path exists

The original P7B required a human to have personally read eleven full original license documents. The owner requested an AI-assisted summary path instead. This **versioned amendment changes the review METHOD, not the existing 11-case or six-profile experiment**. The owner must personally acknowledge the concise briefing from SHA-pinned original OCI license files, the no-redistribution limitation, and the uncertainty concerning unarchived prior experiments. The program may not claim that the owner read all eleven originals or that an AI granted permission to publish or redistribute benchmark code.

Source documents:
- [Original P7A contract and OCI run](https://app.notion.com/p/3f66f08ed24481fda9f7c3209d8f2060): actual PASS, SHA256 `ab10c2b7ed79430932d5ed29a3f714e7c2ab1daeab1689bc77501c65d538fbc8`.
- `docs/bpu8_r3c_p7b_ai_assisted_license_notes_v01.json` has eleven **source-derived** summaries and literal source phrase anchors.
- `scripts/bpu_b8_r3c_p7b_ai_assisted_ack.py` rehashes **each pinned OCI original** and requires exact listed literal phrases; mismatch halts the seal.
- `scripts/bpu_b8_r3c_p7b_explicit_review_seal.py` is now backwards compatible for original direct review, with an explicit alternate `AI_ASSISTED_PINNED_LICENSE_BRIEFING_V01` mode. No hidden conversion of direct to assisted.
- `scripts/bpu_b8_r3c_p7c_committed_lock_preflight.py` validates direct-vs-assisted method, original acknowledged review packet SHA, original P7A SHA, exact Git-HEAD lock bytes, actual simulator/ELF/input/license hashes and unchanged R3 geometry.

## One interactive script, operator must read the brief and confirm

```bash
cd ~/gem5-bpu8-r2c
git pull --ff-only origin little-v052-bpu8-r3c-holdout-p0
bash scripts/bpu_b8_r3c_p7d_finalize_private_lock.sh research_author
```

Use the researcher's preferred non-identifying review identifier instead of `research_author`. This script: (1) checks clean R3C branch and original P7A SHA; (2) runs P7B original seven tests, P7B-assisted six tests and P7C seven Git-HEAD gate tests; (3) builds a fresh AI-assisted 11-case pinned-license summary under HOME; (4) prints the summaries twice; (5) requires the operator to type **`I ACCEPT 11 PRIVATE RESEARCH CASES`** on an actual terminal, making sure this is acceptance of the short notes only, not false self-attestation of full license reading; (6) generates a new signed review packet; (7) generates `docs/r3c_corpus_lock.json`; (8) makes a separate Git commit; (9) performs real P7C committed-lock preflight to `~/bpu8_r3c_p7c_committed_lock_preflight_01.json`.

Do **not** type acceptance if research use or the publication/redistribution boundaries are unacceptable. If any original OCI license differs from the publicly reviewed text markers, the script must fail closed and require source-specific manual review. If any test, Git commit or real P7C preflight fails, stop, preserve all evidence, and report the exact failure. Do not rewrite the original P7A/RAW evidence or silently modify the frozen TAGE geometries to accommodate results.

On actual success, the final shell message is `R3C_P7D_LOCAL_CORPUS_LOCK_PREFLIGHT=PASS`, followed by HEAD and lock digest. **This means locked input/protocol preflight, not a new performance result**. Upload/push commit explicitly after successful P7C:

```bash
git status --short
git push origin little-v052-bpu8-r3c-holdout-p0
```

Only then implement and gate a new paired 66-run Holdout runner; it must independently verify the committed Git lock and all SHA values **at launch**, preserve every run and adverse outcome, and independently audit raw first-ROI stats. R3P RTL SRAM/PPA remains separate. Bounded no-known-prior-input SHA findings do not establish absolute untouched-workload independence.
