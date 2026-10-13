#!/usr/bin/env python3
"""R3C P7B: explicit human review packet and corpus-lock seal candidate.

--init-review writes PENDING answers only. --seal cannot succeed unless the
operator has personally reviewed every pinned LICENSE and accepts the
documented, bounded historical-exposure scope. The lock produced by --seal
MUST be separately committed to Git and validated by a future execution gate.
No simulations run; no legal opinion or absolute unseen-input assertion.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p7a_lock_draft as p7a

EXPECTED_DRAFT_SHA256="ab10c2b7ed79430932d5ed29a3f714e7c2ab1daeab1689bc77501c65d538fbc8"
REVIEW_KIND="BPU8_R3C_P7B_PERSONAL_REVIEW_PACKET"
REVIEW_CASE_DECISION="REVIEWED_FOR_PRIVATE_INTERNAL_ACADEMIC_RESEARCH_NO_REDISTRIBUTION"
REVIEW_SCOPE_DECISION="ACCEPT_LIMITED_FIVE_ARCHIVES_AND_84_PRE_R3C_GIT_FILES"
REVIEW_PROTOCOL_DECISION="FREEZE_UNCHANGED_ELEVEN_CASES_SIX_PROFILES_BEFORE_ANY_TG_COMPARISON"
EXPECTED_CASES=tuple(p2.ORDER)
EXPECTED_PROFILES=tuple(p7a.EXPECTED_6)

def check(ok:bool,description:str):
    if not ok:raise ValueError(description)

def load_json(path:Path):
    check(path.is_file(),"file missing: "+str(path))
    obj=json.loads(path.read_text())
    check(isinstance(obj,dict),"JSON object expected: "+str(path))
    return obj

def verify_draft(draft:dict, digest:str):
    check(digest==EXPECTED_DRAFT_SHA256,
          "P7A bytes do not match observed OCI PASS SHA; do not replace draft silently")
    check(draft.get("kind")=="BPU8_R3C_P7A_LOCK_DRAFT_REQUIRES_REVIEW"
          and draft.get("verdict")=="PRE_RESULT_11x6_CONFIG_DRAFT_NOT_LOCKED_NOT_AUTHORIZED"
          and draft.get("corpus_lock")=="NOT_CREATED"
          and draft.get("authorized_holdout_jobs")==0
          and draft.get("actual_six_profile_jobs")==0
          and draft.get("holdout_result_inspected") is False,
          "P7A source isn't the previously PASSed pre-result draft")
    check(draft.get("target_case_count")==11
          and draft.get("target_profiles_per_case")==6
          and draft.get("target_jobs")==66
          and tuple(draft.get("profile_order",[]))==EXPECTED_PROFILES
          and list(x.get("case") for x in draft.get("case_list",[]))==list(EXPECTED_CASES)
          and draft.get("linked_simulator_gem5_sha256")==p7a.EXPECTED_GEM5,
          "P7A case order/simulator/66-job contract mismatch")
    check(draft.get("scope")=="INTERNAL_RESEARCH_FIRST_ROI_ONLY_NOT_OFFICIAL_COREMARK"
          and draft.get("manual_historical_scope_acceptance")=="REQUIRED_FOR_FUTURE_LOCK"
          and draft.get("manual_license_and_use_conditions_acceptance")=="REQUIRED_FOR_FUTURE_LOCK"
          and draft.get("source_limited_prior_exposure",{}).get("absolute_unseen_claim") is False
          and draft.get("source_limited_prior_exposure",{}).get("five_named_archives_checked")==5
          and draft.get("source_limited_prior_exposure",{}).get("pre_R3C_Git_files_checked")==84,
          "P7A bounded no-absolute-unseen or manual condition drift")
    check(all(draft.get("source_evidence_sha256",{}).get(k)==v
              for k,v in p7a.ORIGINAL_PASS_SHA256.items()),
          "P7A 4 historical provenance SHAs drift")
    for c in draft["case_list"]:
        check(c["elf"]["sha256"] and c["elf"]["size"]>0
              and c["correctness_gate"] and c["g5_reference_outputs"]["first_roi_sha256"]
              and c["license"]["files"]
              and c["license"]["case_terms"]=="MANUAL_REVIEW_PENDING"
              and c["license"]["publication_or_binary_redistribution"]=="NOT_APPROVED",
              c["case"]+": incomplete pre-result input/license pin")
    check(draft["case_list"][5]["case"]=="patricia"
          and draft["case_list"][5]["expected_process_exit_code"]==1,
          "Patricia expected exit 1 was lost")
    check(draft["case_list"][-1]["case"]=="coremark_performance"
          and draft["case_list"][-1]["correctness_gate"].startswith(
                "EEMBC_UPSTREAM_2K_PERFORMANCE_CRC"),
          "CoreMark internal correctness gate changed")
    return True

def review_template(draft):
    return {
        "kind":REVIEW_KIND,
        "status":"REVIEW_REQUIRED_NOT_A_LOCK",
        "p7a_lock_draft_sha256":EXPECTED_DRAFT_SHA256,
        "reviewer_identifier":"", 
        "review_date_utc":"",
        "intended_use":"PRIVATE_INTERNAL_ACADEMIC_RESEARCH_ONLY_NO_THIRD_PARTY_REDISTRIBUTION",
        "historical_exposure_review":{
            "decision":"PENDING",
            "review_notes":"",
            "limitations":{
                "inspected_5_archives":True,
                "inspected_84_pre_R3C_git_files":True,
                "unarchived_OCI_runs_coverage":"UNKNOWN",
                "absolute_unseen_input_proof":False,
                "claim":"NO_KNOWN_OVERLAP_IN_EXPLICITLY_REVIEWED_RECORDS_ONLY",
            },
        },
        "protocol_review":{
            "decision":"PENDING",
            "review_notes":"",
            "no_geometry_retuning":True,
            "no_holdout_metric_peek":True,
            "coremark_result":"INTERNAL_10_ITERATION_FIRST_ROI_NOT_OFFICIAL_SCORE",
        },
        "per_case_license_review":[{
            "case":c["case"],
            "license_files":[{"path":f["path"],"sha256":f["sha256"]}
                             for f in c["license"]["files"]],
            "decision":"PENDING",
            "review_notes":"",
            "redistribution_permission":"NOT_REQUESTED_NOT_GRANTED",
        } for c in draft["case_list"]],
        "explicit_limits":[
            "This self-attestation is not independent legal advice or blanket redistribution rights",
            "A zero hash hit among selected prior records does not prove all possible prior executions were unseen",
            "Licenses must be read at pinned paths and internal research suitability decided separately",
            "If any case is incompatible, STOP before lock; do not silently omit or substitute",
        ],
    }

def validate_review(draft, review, review_digest=None):
    check(review.get("kind")==REVIEW_KIND
          and review.get("status")=="REVIEW_REQUIRED_NOT_A_LOCK"
          and review.get("p7a_lock_draft_sha256")==EXPECTED_DRAFT_SHA256
          and review.get("intended_use")==
              "PRIVATE_INTERNAL_ACADEMIC_RESEARCH_ONLY_NO_THIRD_PARTY_REDISTRIBUTION",
          "review identity/intended-use mismatch")
    check(isinstance(review.get("reviewer_identifier"),str)
          and len(review["reviewer_identifier"].strip())>=3
          and isinstance(review.get("review_date_utc"),str)
          and review["review_date_utc"].endswith("Z"),
          "explicit reviewer ID and ISO UTC review date required")
    hist=review.get("historical_exposure_review",{})
    expected_scope=review_template(draft)["historical_exposure_review"]["limitations"]
    check(hist.get("limitations")==expected_scope
          and hist.get("decision")==REVIEW_SCOPE_DECISION
          and len(str(hist.get("review_notes","")).strip())>=20,
          "bounded historical exposure scope not personally reviewed and attested")
    proto=review.get("protocol_review",{})
    check(proto.get("decision")==REVIEW_PROTOCOL_DECISION
          and len(str(proto.get("review_notes","")).strip())>=20
          and proto.get("no_geometry_retuning") is True
          and proto.get("no_holdout_metric_peek") is True
          and proto.get("coremark_result")==
              "INTERNAL_10_ITERATION_FIRST_ROI_NOT_OFFICIAL_SCORE",
          "no-metric-peek fixed 11x6 protocol not explicitly reviewed")
    items=review.get("per_case_license_review",[])
    check(isinstance(items,list) and len(items)==11
          and [x.get("case") for x in items]==list(EXPECTED_CASES),
          "eleven individual licensing acknowledgements must be in original order")
    for orig, entry in zip(draft["case_list"],items):
        expect=[{"path":f["path"],"sha256":f["sha256"]}
                for f in orig["license"]["files"]]
        check(entry.get("license_files")==expect
              and entry.get("decision")==REVIEW_CASE_DECISION
              and entry.get("redistribution_permission")=="NOT_REQUESTED_NOT_GRANTED"
              and len(str(entry.get("review_notes","")).strip())>=20,
              orig["case"]+": license terms not reviewed, redist boundary or pinned license differs")
        # Source must still be available with the original exact SHA.
        for f in entry["license_files"]:
            path=Path(f["path"])
            check(path.is_file() and p2.sha(path)==f["sha256"],
                  orig["case"]+": original license bytes changed after reviewing")
    return True

def seal(draft, review, draft_sha, review_sha):
    verify_draft(draft,draft_sha)
    validate_review(draft,review)
    # Git must commit this file as a separate act. Runner verifies exact
    # HEAD tree+manifest SHA before allowing a single six-profile job.
    return {
        "kind":"BPU8_R3C_FIXED_CORPUS_LOCK_V01",
        "verdict":"SEALED_PRE_RESULT_INPUTS_PENDING_GIT_COMMIT_AND_RUNNER_GATE",
        "lock_created_utc":datetime.now(timezone.utc).isoformat(),
        "original_p7a_sha256":draft_sha,
        "signed_review_packet_sha256":review_sha,
        "reviewer_identifier":review["reviewer_identifier"],
        "review_date_utc":review["review_date_utc"],
        "review_scope":"BOUNDED_HISTORICAL_NO_KNOWN_OVERLAP_NOT_ABSOLUTE_UNSEEN",
        "approved_usage_scope":"PRIVATE_INTERNAL_ACADEMIC_RESEARCH_NO_CODE_BINARY_DISTRIBUTION",
        "coremark_presentation_scope":"INTERNAL_FIRST_ROI_NOT_OFFICIAL_SCORE",
        "manual_case_reviews":[{
            "case":c["case"],"license_files":c["license_files"],
            "decision":c["decision"],"review_notes":c["review_notes"],
            "redistribution_permission":"NOT_REQUESTED_NOT_GRANTED",
        } for c in review["per_case_license_review"]],
        "historical_scope_review":review["historical_exposure_review"],
        "protocol_review":review["protocol_review"],
        "source_evidence_sha256":draft["source_evidence_sha256"],
        "frozen_r3_geometry_sha256":draft["frozen_r3_geometry_sha256"],
        "frozen_geometry_profiles":draft["frozen_geometry_profiles"],
        "profile_order":draft["profile_order"],
        "linked_simulator_gem5_sha256":draft["linked_simulator_gem5_sha256"],
        "source_revisions":draft["source_revisions"],
        "case_list":draft["case_list"],
        "cases":11,"profiles_per_case":6,"planned_jobs":66,
        "simulator_runs_executed_at_sealing":0,
        "approved_for_execution_only_after":"LOCK_FILE_GIT_COMMITTED_AND_RUNNER_SOURCE_VERIFIED",
        "third_party_redistribution_rights":"NOT_GRANTED",
        "not_little_v052_original_cpu_architecture_freeze":True,
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init-review",action="store_true")
    mode.add_argument("--seal",action="store_true")
    ap.add_argument("--draft",type=Path,required=True)
    ap.add_argument("--review",type=Path,required=True)
    ap.add_argument("--out",type=Path,
                    help="For seal: exact repo path docs/r3c_corpus_lock.json")
    args=ap.parse_args()
    draft_path=args.draft.expanduser().resolve()
    review_path=args.review.expanduser().resolve()
    draft=load_json(draft_path)
    draft_sha=p2.sha(draft_path)
    verify_draft(draft,draft_sha)
    if args.init_review:
        check(args.out is None,"--out not used with --init-review")
        check(not review_path.exists(),"never overwrite a previously generated review")
        review_path.parent.mkdir(parents=True,exist_ok=True)
        with review_path.open("x") as f:
            json.dump(review_template(draft),f,indent=2,sort_keys=True,ensure_ascii=False)
            f.write("\n")
        print("R3C_P7B_REVIEW_TEMPLATE="+str(review_path))
        print("R3C_P7B_VERDICT=REVIEW_REQUIRED_NOT_A_LOCK")
        print("NO CLAIM: legal approval, corpus lock or simulator performance")
        return
    check(args.out is not None,"--seal requires --out docs/r3c_corpus_lock.json")
    repo_lock=p2.ROOT/"docs/r3c_corpus_lock.json"
    dest=args.out.expanduser().resolve()
    check(dest==repo_lock.resolve(),
          "sealing may write ONLY docs/r3c_corpus_lock.json in current Git repo")
    check(not dest.exists(),"refuse to overwrite prior lock")
    review=load_json(review_path)
    result=seal(draft,review,draft_sha,p2.sha(review_path))
    with dest.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.write("\n")
    print("R3C_P7B_UNCOMMITTED_SEAL="+str(dest))
    print("R3C_P7B_LOCK_SHA256="+p2.sha(dest))
    print("R3C_P7B_VERDICT=SEALED_PENDING_GIT_COMMIT_NOT_YET_RUNNABLE")
    print("NEXT: separate Git commit + strict runner git-HEAD-lock gate; NO sim yet")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError) as e:
        print("R3C_P7B_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
