#!/usr/bin/env bash
# R3C P7D: Complete *operator-approved* private-only 11x6 technical corpus seal.
# No simulation; no automatic legal advice, no fabricated review signature.
set -euo pipefail

BRANCH="little-v052-bpu8-r3c-holdout-p0"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
REVIEWER="${1:-}"
if [[ ${#REVIEWER} -lt 3 ]]; then
  echo "Usage: $0 <your-researcher-identifier-min3chars>" >&2
  exit 2
fi
if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
  echo "P7D_BLOCKED: branch is not $BRANCH" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "P7D_BLOCKED: working Git-tracked tree must be clean" >&2
  exit 1
fi

DRAFT="$HOME/bpu8_r3c_p7a_lock_draft_01.json"
PENDING="$HOME/bpu8_r3c_p7b_manual_review_01.json"
P4A="$HOME/bpu8_r3c_p4a_static_01.json"
BRIEF="$HOME/bpu8_r3c_p7b_ai_brief_01.json"
SIGNED="$HOME/bpu8_r3c_p7b_assisted_signed_01.json"
GEM5="$ROOT/build/RISCV/gem5.opt"
LOCK="$ROOT/docs/r3c_corpus_lock.json"
PREFLIGHT="$HOME/bpu8_r3c_p7c_committed_lock_preflight_01.json"
for source in "$DRAFT" "$PENDING" "$P4A" "$GEM5"; do
  if [[ ! -f "$source" ]]; then
    echo "P7D_BLOCKED: original evidence missing: $source" >&2; exit 1
  fi
done
for dest in "$BRIEF" "$SIGNED" "$LOCK" "$PREFLIGHT"; do
  if [[ -e "$dest" ]]; then
    echo "P7D_BLOCKED: output already exists; do NOT overwrite: $dest" >&2
    exit 1
  fi
done

echo "ab10c2b7ed79430932d5ed29a3f714e7c2ab1daeab1689bc77501c65d538fbc8  $DRAFT" | sha256sum -c -
python3 tests/bpu8/test_r3c_p7b_explicit_review_seal.py
python3 tests/bpu8/test_r3c_p7b_ai_assisted_ack.py
python3 tests/bpu8/test_r3c_p7c_committed_lock_preflight.py

python3 scripts/bpu_b8_r3c_p7b_ai_assisted_ack.py \
  --prepare --draft "$DRAFT" --pending "$PENDING" --brief "$BRIEF"

# REQUIRES AN ACTUAL HUMAN INTERACTIVE TERMINAL ACK.
# Will stop with P7B PENDING if operator does not personally accept summary.
python3 scripts/bpu_b8_r3c_p7b_ai_assisted_ack.py \
  --ack --draft "$DRAFT" --pending "$PENDING" --brief "$BRIEF" \
  --out "$SIGNED" --reviewer "$REVIEWER"

python3 scripts/bpu_b8_r3c_p7b_explicit_review_seal.py \
  --seal --draft "$DRAFT" --review "$SIGNED" --out "$LOCK"

# Commit literal bytes as a standalone tracked contract; do not amend
# original 2026-09-20 Little CPU frozen architecture.
git add -- docs/r3c_corpus_lock.json
git diff --cached --check
git commit -m "freeze(bpu8-r3c): operator-acknowledged 11-case six-profile pre-result corpus"

python3 scripts/bpu_b8_r3c_p7c_committed_lock_preflight.py \
  --draft "$DRAFT" --review "$SIGNED" --p4a "$P4A" \
  --gem5 "$GEM5" --out "$PREFLIGHT"

echo "R3C_P7D_LOCAL_CORPUS_LOCK_PREFLIGHT=PASS"
echo "R3C_P7D_GIT_HEAD=$(git rev-parse HEAD)"
echo "R3C_P7D_LOCK_SHA256=$(sha256sum "$LOCK" | cut -d' ' -f1)"
echo "R3C_P7D_NEXT=push reviewed lock commit to origin after inspecting status"
echo "NO CLAIM: 66 runs completed, absolute untouchedness, RTL/SRAM PPA, third-party distribution rights"
