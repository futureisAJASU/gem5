#!/usr/bin/env python3
"""R3C P7C: verify Git-committed literal corpus lock, NO GEM5 EXECUTION.

Does not create an authorization itself. Future six-way runner must consume
this exact lock+HEAD evidence and independently recheck all checks at launch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p4a_static as p4a
import bpu_b8_r3c_p7a_lock_draft as p7a
import bpu_b8_r3c_p7b_explicit_review_seal as p7b

LOCK_REL="docs/r3c_corpus_lock.json"
EXPECTED_KIND="BPU8_R3C_FIXED_CORPUS_LOCK_V01"
EXPECTED_LOCK_VERDICT="SEALED_PRE_RESULT_INPUTS_PENDING_GIT_COMMIT_AND_RUNNER_GATE"
REVIEW_SCOPE="BOUNDED_HISTORICAL_NO_KNOWN_OVERLAP_NOT_ABSOLUTE_UNSEEN"

def require(ok,msg):
    if not ok:raise ValueError(msg)

def git(*args, binary=False):
    r=subprocess.run(["git",*args],cwd=p2.ROOT,capture_output=True,
                     text=not binary,timeout=40)
    require(r.returncode==0,
            "Git metadata missing or command failed: "+" ".join(args))
    return r.stdout

def verify_committed_lock(lock_file:Path) -> tuple[str,str]:
    require(lock_file.resolve()==(p2.ROOT/LOCK_REL).resolve(),
            "run gate requires exact docs/r3c_corpus_lock.json path")
    require(lock_file.is_file(),"committed lock file missing")
    # Without --error-unmatch, an untracked lock yields an empty list and
    # reaches the explicit, stable fail-closed diagnostic below.
    tracked=git("ls-files","--",LOCK_REL)
    require(tracked.strip()==LOCK_REL,
            "lock is not tracked by Git")
    require(not git("status","--porcelain","--untracked-files=no").strip(),
            "tracked repo has uncommitted modifications, including the lock")
    expected=git("show","HEAD:"+LOCK_REL,binary=True)
    current=lock_file.read_bytes()
    require(expected==current,
            "HEAD-committed lock bytes differ from actual working tree")
    require(not git("diff","--name-only","HEAD","--",LOCK_REL).strip(),
            "staged or changed lock file")
    return git("rev-parse","HEAD").strip(),hashlib.sha256(current).hexdigest()

def attest_config(lock:dict,draft:dict,review:dict,plan:dict,gem5:Path,
                  draft_digest:str,review_digest:str,plan_digest:str):
    p7b.verify_draft(draft,draft_digest)
    p7b.validate_review(draft,review)
    require(lock.get("kind")==EXPECTED_KIND
            and lock.get("verdict")==EXPECTED_LOCK_VERDICT
            and lock.get("original_p7a_sha256")==draft_digest
            and lock.get("signed_review_packet_sha256")==review_digest,
            "lock original draft/manual-review hash chain altered")
    require(lock.get("review_scope")==REVIEW_SCOPE
            and lock.get("third_party_redistribution_rights")=="NOT_GRANTED"
            and lock.get("approved_usage_scope")==
                "PRIVATE_INTERNAL_ACADEMIC_RESEARCH_NO_CODE_BINARY_DISTRIBUTION"
            and lock.get("coremark_presentation_scope")==
                "INTERNAL_FIRST_ROI_NOT_OFFICIAL_SCORE",
            "review scope or publication boundary improperly expanded")
    require(lock.get("planned_jobs")==66 and lock.get("cases")==11
            and lock.get("profiles_per_case")==6
            and lock.get("simulator_runs_executed_at_sealing")==0
            and lock.get("approved_for_execution_only_after")==
                "LOCK_FILE_GIT_COMMITTED_AND_RUNNER_SOURCE_VERIFIED",
            "locked experiment job counts or chronology inconsistent")
    require(lock.get("reviewer_identifier")==review["reviewer_identifier"]
            and lock.get("review_date_utc")==review["review_date_utc"]
            and lock.get("manual_case_reviews")==[{
                  "case":r["case"],
                  "license_files":r["license_files"],
                  "decision":r["decision"],
                  "review_notes":r["review_notes"],
                  "redistribution_permission":"NOT_REQUESTED_NOT_GRANTED",
                } for r in review["per_case_license_review"]],
            "actual signed manual case reviews differ from lock")
    require(lock.get("historical_scope_review")==review["historical_exposure_review"]
            and lock.get("protocol_review")==review["protocol_review"],
            "human manual historical scope/protocol acknowledgement modified")
    for key in ("profile_order","frozen_geometry_profiles",
                "frozen_r3_geometry_sha256","source_evidence_sha256",
                "linked_simulator_gem5_sha256","source_revisions","case_list"):
        require(lock.get(key)==draft.get(key),
                "signed lock differs from P7A immutable candidate spec: "+key)
    require(tuple(lock["profile_order"])==tuple(p7a.EXPECTED_6)
            and all(row["total_bits"]==45736
                    for row in lock["frozen_geometry_profiles"].values()),
            "six frozen R3 predictor geometry budgets changed")
    require(gem5.is_file()
            and p2.sha(gem5)==lock["linked_simulator_gem5_sha256"]
            and p2.sha(gem5)==p7a.EXPECTED_GEM5,
            "gem5 binary modified from prereg G5-tested simulator")
    require(p2.sha(p4a.R3_MATRIX)==lock["frozen_r3_geometry_sha256"],
            "R3 matrix SHA changed since prior lock")
    matrix=json.loads(p4a.R3_MATRIX.read_text())
    require(matrix["profiles"]==lock["frozen_geometry_profiles"],
            "R3 geometry configuration not equal original source matrix")
    require(plan_digest==draft["source_evidence_sha256"]["p4a"]
            and plan["r3c_se_config_sha256"]==p2.sha(p4a.R3C_CONFIG)
            and plan["original_config_sha256"]==p2.sha(p4a.ORIGINAL_CONFIG)
            and plan["original_r3_geometry_matrix_sha256"]==
                lock["frozen_r3_geometry_sha256"],
            "P4A original simulator frontend/IO adaptor contract SHA differs")
    require([case["case"] for case in lock["case_list"]]==list(p2.ORDER),
            "case order changed")
    for entry in lock["case_list"]:
        case=entry["case"]
        elf=Path(entry["elf"]["path"])
        require(elf.is_file()
                and elf.stat().st_size==entry["elf"]["size"]
                and p2.sha(elf)==entry["elf"]["sha256"],
                case+": prior-RV64 executable changed")
        for inp in entry["input_files"]:
            source=Path(inp["source_path"])
            require(source.is_file()
                    and source.stat().st_size==inp["size"]
                    and p2.sha(source)==inp["sha256"],
                    case+": source input bytes changed")
        require(entry["license"]["publication_or_binary_redistribution"]=="NOT_APPROVED"
                and entry["license"]["case_terms"]=="MANUAL_REVIEW_PENDING",
                case+": original pre-review terms changed in immutable draft")
        for lic in entry["license"]["files"]:
            p=Path(lic["path"])
            require(p.is_file() and p2.sha(p)==lic["sha256"],
                    case+": license terms changed after reviewer attestation")
    return {"case_count":11,"profile_count":6,"planned_jobs":66}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("draft","review","p4a","gem5","out"):
        ap.add_argument("--"+key,type=Path,required=True)
    args=ap.parse_args()
    paths={k:v.expanduser().resolve() for k,v in vars(args).items()}
    require(not paths["out"].exists(),"never overwrite a previous evidence packet")
    draft=p7b.load_json(paths["draft"])
    review=p7b.load_json(paths["review"])
    plan=p7b.load_json(paths["p4a"])
    lock_file=p2.ROOT/LOCK_REL
    head,lock_sha=verify_committed_lock(lock_file)
    lock=p7b.load_json(lock_file)
    report=attest_config(lock,draft,review,plan,paths["gem5"],
                         p2.sha(paths["draft"]),p2.sha(paths["review"]),
                         p2.sha(paths["p4a"]))
    result={
        "kind":"BPU8_R3C_P7C_COMMITTED_LOCK_PREFLIGHT_NO_SIM_RUN",
        "verdict":"LOCK_FILE_IN_GIT_AND_INPUTS_REHASHED_RUNNER_NOT_EXECUTED",
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "repo_commit_head":head,
        "git_lock_path":LOCK_REL,
        "committed_lock_sha256":lock_sha,
        "review_sha256":p2.sha(paths["review"]),
        "original_draft_sha256":p2.sha(paths["draft"]),
        "simulator_sha256":p2.sha(paths["gem5"]),
        **report,
        "comparison_executions_completed_by_this_tool":0,
        "future_runner_must_recheck_every_gate":True,
        "physical_SRAM_RTL_PPA":"NOT_MEASURED",
    }
    with paths["out"].open("x") as f:
        json.dump(result,f,indent=2,ensure_ascii=False,sort_keys=True)
        f.write("\n")
    print("R3C_P7C_PREFLIGHT="+str(paths["out"]))
    print("R3C_P7C_PREFLIGHT_SHA256="+p2.sha(paths["out"]))
    print("R3C_P7C_COMMITTED_LOCK_SHA256="+lock_sha)
    print("R3C_P7C_VERDICT="+result["verdict"])
    print("NO CLAIM: any TG6/TG7 performance result or RTL/PPA signoff")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError,KeyError,RuntimeError,subprocess.SubprocessError) as e:
        print("R3C_P7C_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
