#!/usr/bin/env python3
"""P7B-A. Prepare a source-SHA-anchored AI-assisted license briefing.

--prepare never changes decisions; outputs short review JSON and prints notes.
--ack requires a *real TTY* confirmation AFTER briefing; labels results as an
AI-assisted operator acknowledgement, not as full original-license reading.
No legal approval, source/binary redistribution or simulation is performed.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p7b_explicit_review_seal as p7b

SOURCE=p7b.ASSISTED_NOTES
CONFIRM="I ACCEPT 11 PRIVATE RESEARCH CASES"
BRIEF_KIND="R3C_P7B_PINNED_LICENSE_AI_ASSISTED_BRIEF_V01"

def check(cond,msg):
    if not cond:raise ValueError(msg)

def load(path):
    check(path.is_file(),"file missing: "+str(path))
    return json.loads(path.read_text())

def make_brief(draft, pending, draft_sha, pending_sha):
    p7b.verify_draft(draft,draft_sha)
    policy=load(SOURCE)
    check(policy.get("kind")=="BPU8_R3C_P7B_AI_ASSISTED_LICENSE_NOTES_V01"
          and policy.get("scope")=="PRIVATE_INTERNAL_ACADEMIC_ONLY_NO_SOURCE_OR_BINARY_DISTRIBUTION"
          and len(policy.get("cases",[]))==11,
          "versioned license note source malformed")
    check(pending.get("kind")==p7b.REVIEW_KIND
          and pending.get("status")=="REVIEW_REQUIRED_NOT_A_LOCK"
          and pending.get("p7a_lock_draft_sha256")==draft_sha
          and [c["case"] for c in pending.get("per_case_license_review",[])]==
              list(p7b.EXPECTED_CASES)
          and all(c["decision"]=="PENDING"
                  for c in pending["per_case_license_review"])
          and pending["historical_exposure_review"]["decision"]=="PENDING"
          and pending["protocol_review"]["decision"]=="PENDING",
          "original P7B unsigned review missing or already approved")
    rows=[]
    for spec,existing,proposal in zip(draft["case_list"],
                                      pending["per_case_license_review"],
                                      policy["cases"]):
        name=spec["case"]
        check(name==existing["case"]==proposal["case"],
              "case order or review metadata drift")
        files=existing["license_files"]
        check(files==spec["license"]["files"] and len(files)==1,
              name+": individual P7A license SHA mismatch")
        path=Path(files[0]["path"])
        check(path.is_file() and p2.sha(path)==files[0]["sha256"],
              name+": pinned original license bytes changed")
        text=path.read_text(encoding="utf-8",errors="replace")
        expected=proposal["required_literal_license_phrases"]
        check(all(anchor.casefold() in text.casefold() for anchor in expected),
              name+": pinned original license differs from AI-reviewed source! "
              "STOP and review actual original manually")
        rows.append({
            "case":name,"source_license_sha256":files[0]["sha256"],
            "source_license_path":files[0]["path"],
            "matched_original_literal_phrases":expected,
            "model_summary":proposal["model_summary"],
            "review_status":"AI_ANALYSIS_ONLY_OPERATOR_NOT_YET_ACKNOWLEDGED",
            "publication_or_redistribution":"NOT_APPROVED",
        })
    return {
        "kind":BRIEF_KIND,
        "status":"AI_SOURCE_BRIEF_READY_HUMAN_ACK_REQUIRED",
        "p7a_draft_sha256":draft_sha,
        "pending_original_review_sha256":pending_sha,
        "assistant_summary_source_sha256":p2.sha(SOURCE),
        "source_scope":"ELEVEN_PINNED_LICENSE_FILES_SHA_VERIFIED_AND_REQUIRED_LITERAL_CLAUSES_MATCHED",
        "original_review_method":"AI_ASSISTED_PUBLIC_UPSTREAM_SUMMARY_REVIEW_NOT_FULL_TEXT_ATTESTATION",
        "research_scope":"PRIVATE_INTERNAL_ONLY_NO_REDISTRIBUTION",
        "history_scope":"FIVE_OLD_ARCHIVES_AND_84_SELECTED_PRE_R3C_FILES_ONLY",
        "unarchived_OCI_history":"UNKNOWN",
        "coremark_score_claim":"NOT_OFFICIAL_EEMBC_COREMARK_SCORE",
        "cases":rows,
        "manual_operator_ack_required":True,
    }

def print_brief(brief):
    print("\nR3C P7B — AI-assisted pinned-license briefing")
    print("Eleven SHA-matched pinned license files and literal-phrase guards")
    print("SCOPE: PRIVATE INTERNAL ACADEMIC STUDY ONLY; NO SOURCE/BINARY DISTRIBUTION")
    print("HISTORY: 5 archives + 84 Git files ONLY; unarchived runs unknown")
    for entry in brief["cases"]:
        print(f"\n[{entry['case']}] {entry['model_summary']}")
        print(" pinned_SHA256="+entry["source_license_sha256"])
    print("\nWARNING: AI summary + exact source phrase matching is NOT legal counsel")
    print("NO official CoreMark score; NO TG6/TG7 performance measured")
    print("\nFinal acknowledgement must be given personally on an interactive terminal.\n")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare",action="store_true")
    mode.add_argument("--ack",action="store_true")
    for name in ("draft","pending","brief"):
        ap.add_argument("--"+name,type=Path,required=True)
    ap.add_argument("--out",type=Path,help="Only --ack: fresh acknowledged review output")
    ap.add_argument("--reviewer",help="Only --ack: human-readable operator identifier")
    a=ap.parse_args()
    draft_path=a.draft.expanduser().resolve()
    pending_path=a.pending.expanduser().resolve()
    brief_path=a.brief.expanduser().resolve()
    draft=load(draft_path); pending=load(pending_path)
    fresh=make_brief(draft,pending,p2.sha(draft_path),p2.sha(pending_path))
    if a.prepare:
        check(a.out is None and a.reviewer is None,
              "--prepare accepts neither --out nor --reviewer")
        check(not brief_path.exists(),"refuse to overwrite briefing")
        brief_path.parent.mkdir(parents=True,exist_ok=True)
        with brief_path.open("x") as f:
            json.dump(fresh,f,indent=2,sort_keys=True,ensure_ascii=False)
            f.write("\n")
        print_brief(fresh)
        print("R3C_P7B_ASSISTED_BRIEF="+str(brief_path))
        print("R3C_P7B_ASSISTED_BRIEF_SHA256="+p2.sha(brief_path))
        print("R3C_P7B_ASSISTED_VERDICT=BRIEF_PREPARED_NOT_SIGNED_NOT_LOCKED")
        return
    check(a.out is not None and a.reviewer and
          len(a.reviewer.strip())>=3,"--ack requires --out and explicit --reviewer")
    out=a.out.expanduser().resolve()
    check(not out.exists(),"refuse to overwrite an acknowledged review")
    old=load(brief_path)
    check(old==fresh,"AI summary or original license bytes/notes have changed")
    check(sys.stdin.isatty(),
          "a real interactive terminal is required for human acknowledgement")
    print_brief(fresh)
    print("You acknowledge only the eleven SHORT AI-assisted summaries above,")
    print("not that you personally read all eleven full original license texts.")
    print("Confirm private academic use, no redistribution, no official CoreMark")
    print("score claim, five-archive + 84-file limited prior-exposure scope,")
    print("and no peek/retuning before all six-by-eleven Holdout results.")
    answer=input("TYPE EXACTLY '"+CONFIRM+"' to accept: ").strip()
    check(answer==CONFIRM,"no human approval; review still PENDING")
    signed=deepcopy(pending)
    signed["review_method"]=p7b.ASSISTED_METHOD
    signed["ai_assisted_notes_sha256"]=p2.sha(SOURCE)
    signed["acknowledgement_source"]="USER_INTERACTIVE_TERMINAL_ACK"
    signed["reviewer_identifier"]=a.reviewer.strip()
    signed["review_date_utc"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    hist=signed["historical_exposure_review"]
    hist["decision"]=p7b.REVIEW_SCOPE_DECISION
    hist["review_notes"]=(
      "I reviewed the summary of exactly 5 past archived experiments and "
      "84 pre-R3C Git files. No listed candidate reuse was observed in this "
      "bounded evidence; unarchived OCI runs remain UNKNOWN and no absolute "
      "unseen-workload claim is authorized.")
    proto=signed["protocol_review"]
    proto["decision"]=p7b.REVIEW_PROTOCOL_DECISION
    proto["review_notes"]=(
      "I accept the pre-result fixed 11 cases x six unchanged 45,736-bit "
      "R3 profiles. No geometry retuning, case cherry-picking, unofficial "
      "CoreMark score, or metric peeking is authorized.")
    for target,row in zip(signed["per_case_license_review"],fresh["cases"]):
        target["decision"]=p7b.REVIEW_CASE_DECISION
        target["review_notes"]=(
            "AI_ASSISTED_PINNED_SOURCE_CHECK: I acknowledge the SHA-verified "
            "AI-assisted summary and private-only / no-redistribution limits. "
            +row["model_summary"])
    p7b.validate_review(draft,signed)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:
        json.dump(signed,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.write("\n")
    print("R3C_P7B_ASSISTED_SIGNED_REVIEW="+str(out))
    print("R3C_P7B_ASSISTED_REVIEW_SHA256="+p2.sha(out))
    print("R3C_P7B_ASSISTED_VERDICT=OPERATOR_ACK_RECORDED_NO_LOCK_YET")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError) as e:
        print("R3C_P7B_ASSISTED_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
