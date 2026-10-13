# BPU-8 R3C P7B/P7C – explicit review and pre-result corpus-lock protocol

Status: SOURCE READY; HUMAN REVIEW AND CORPUS LOCK NOT YET COMPLETED.

## Provenance

Actual OCI P7A draft: /home/ubuntu/bpu8_r3c_p7a_lock_draft_01.json
SHA256: ab10c2b7ed79430932d5ed29a3f714e7c2ab1daeab1689bc77501c65d538fbc8
Exactly 11 candidate source/ELF/input/output contracts and six pre-frozen R3 geometry profiles at 45,736 bits each. P7A is not an experiment or approved corpus lock.

Historical non-exposure evidence is bounded to five exact older archives plus 84 selected earlier Git files. No exact recorded SHA or name hits were observed. Unarchived OCI runs are not proved nonexistent. Do not claim absolute untouched independence.

## P7B human review

Use scripts/bpu_b8_r3c_p7b_explicit_review_seal.py --init-review with --draft and --review arguments. The generated JSON MUST begin with PENDING decisions. Do not use automated mass-approval.

Each of the eleven individual case entries must be based on actually reading its pinned source license file at the captured SHA. After review of suitability for PRIVATE INTERNAL ACADEMIC RESEARCH without redistribution, the human operator can fill decision REVIEWED_FOR_PRIVATE_INTERNAL_ACADEMIC_RESEARCH_NO_REDISTRIBUTION and a nontrivial note. If unsuitable, STOP; excluding a workload would require a prespecified, versioned amendment before results.

Historical scope decision: ACCEPT_LIMITED_FIVE_ARCHIVES_AND_84_PRE_R3C_GIT_FILES (record the unarchived OCI uncertainty in notes). Protocol decision: FREEZE_UNCHANGED_ELEVEN_CASES_SIX_PROFILES_BEFORE_ANY_TG_COMPARISON (record commitment to no tuning, cherry picking or metrics peek in notes). Record reviewer identifier and Z-suffixed UTC date. These are human self-attestations, not a legal opinion.

Review the distinctive terms of SUSAN (research limitations and attribution), GPL language in several MiBench programs, individual FFT/ADPCM/AES notices, and the CoreMark trademark/Acceptable Use Agreement. Never republish sources/binaries or call the 10-iteration simulated CoreMark an official score without separate license/protocol basis.

P7B --seal validates exactly 11 human signoffs, original license byte SHA, the bounded scope acknowledgement, frozen 11x6 agreement, original P7A SHA, and writes ONLY docs/r3c_corpus_lock.json inside the working Git repository. Sealing alone is not execution authorization.

## P7C Git preflight

After a separate Git add/commit of docs/r3c_corpus_lock.json, P7C reads the exact original P7A draft, original human review JSON, original P4A plan, committed lock and gem5 binary. It requires the Git HEAD version of the lock to be byte-identical to the working-tree lock, the tracked repository to be clean, the simulator to match its frozen SHA, all six profiles to match R3, all program/input/LICENSE SHA values to remain unchanged, and the original R3C input/output adapter and frontend config hashes to remain pinned.

Source: scripts/bpu_b8_r3c_p7c_committed_lock_preflight.py. P7B has seven synthetic directed tests; P7C has six local-Git directed tests. New tests source ready, not yet run on OCI.

Neither P7B nor P7C executes any gem5 workload. Future six-profile runner must REPEAT these prelaunch checks and preserve all signed log ratios, W/L/T, worst regressions and original first-ROI RAW. Source/runner commit must be recorded before any paired performance. Independent physical R3P SRAM/RTL PPA remains open.
