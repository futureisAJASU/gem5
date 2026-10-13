#!/usr/bin/env python3
"""R3C P7A: prepare reviewed, immutable-identity lock DRAFT only.

Never executes gem5, never writes r3c_corpus_lock.json, never authorizes
six-profile Holdout. Derives case bytes from P6A SHA custody and checks P6D
explicitly remains UNSIGNED (licenses and historical bounded scope).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p4a_static as p4a
import bpu_b8_r3c_p5a_split_raw_audit as p5a
import bpu_b8_r3c_p6a_prelock_custody as p6a
import bpu_b8_r3c_p6d_final_prelock_license_review as p6d

EXPECTED_P6A=p6a.EXPECTED_P5A
P6A_VERDICT="11_CASE_CUSTODY_CHECKED_HISTORICAL_INDEPENDENCE_NOT_VERIFIED_NOT_LOCKED"
P6D_VERDICT="EVIDENCE_READY_FOR_MANUAL_LOCK_SIGNOFF_NOT_CORPUS_LOCK"
EXPECTED_6=tuple(p6a.EXPECTED_6)
EXPECTED_GEM5=p5a.EXPECTED_GEM5

def require(ok,why):
    if not ok:
        raise ValueError(why)

def load(path:Path):
    require(path.is_file(),"missing JSON: "+str(path))
    result=json.loads(path.read_text())
    require(isinstance(result,dict),"JSON root not object: "+str(path))
    return result

def validate_chain(p1,p4a_plan,p6a_snapshot,p6b,p6c,p6d,
                   fingerprints,gem5,paths):
    """No candidate stats or post-lock results permitted in this procedure."""
    order=tuple(p2.ORDER)
    require(order==("basicmath","bitcount","qsort","susan_edges","dijkstra",
                    "patricia","rijndael_encrypt","fft","adpcm_encode",
                    "stringsearch","coremark_performance"),
            "pre-reg order altered")
    require(p6a_snapshot.get("kind")==
            "R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT"
            and p6a_snapshot.get("verdict")==P6A_VERDICT
            and p6a_snapshot.get("r3c_corpus_lock")=="NOT_CREATED"
            and p6a_snapshot.get("historical_unseen_workload_independence")=="UNVERIFIED"
            and p6a_snapshot.get("comparison_performance_started") is False,
            "P6A not a valid pre-result snapshot")
    require(p6d.get("kind")=="BPU8_R3C_P6D_FINAL_PRELOCK_SOURCE_AND_LICENSE_DOSSIER"
            and p6d.get("verdict")==P6D_VERDICT
            and p6d.get("r3c_corpus_lock")=="NOT_CREATED"
            and p6d.get("manual_license_review")=="REQUIRED"
            and p6d.get("manual_historical_exposure_signoff")=="REQUIRED"
            and p6d.get("authorized_six_profile_holdout_runs")==0,
            "P6D pending human review state changed")
    require(p6d.get("p1_source_sha256")==fingerprints["p1"]
            and p6d.get("p6a_sha256")==fingerprints["p6a"]
            and p6d.get("p6b_sha256")==fingerprints["p6b"]
            and p6d.get("p6c_sha256")==fingerprints["p6c"],
            "P6D chain SHA mismatch")
    require(p6a_snapshot.get("p4a_plan_sha256")==fingerprints["p4a"]
            and p6a_snapshot.get("simulator_gem5_sha256")==EXPECTED_GEM5
            and tuple(p6a_snapshot.get("six_profiles",[]))==EXPECTED_6
            and p6a_snapshot.get("logical_bits_each")==45736
            and p6a_snapshot.get("candidate_performance_jobs_NOT_authorized")==66,
            "P6A input/profile/bit accounting or scope drift")
    require(p6b.get("p6a_sha256")==fingerprints["p6a"]
            and p6c.get("p6a_sha256")==fingerprints["p6a"]
            and p6c.get("p6b_sha256")==fingerprints["p6b"],
            "P6B/C prior-evidence chain mismatch")
    require(p6b.get("verdict")=="PRIOR_EVIDENCE_DISCOVERY_REQUIRES_COMPLETENESS_REVIEW_NO_CORPUS_LOCK"
            and p6b.get("corpus_lock")=="NOT_AUTHORIZED"
            and len(p6b.get("prior_sources",[]))==5
            and len(p6b.get("prior_exact_candidate_SHA_occurrences",[]))==0
            and len(p6b.get("skipped_or_unreadable_members",[]))==0,
            "P6B recorded historical negative evidence not clean")
    require(p6c.get("verdict")==
            "PRE_R3C_GIT_SOURCE_BOUNDARY_REVIEWED_HISTORICAL_COMPLETENESS_UNVERIFIED_NO_LOCK"
            and p6c.get("reference_file_count")==0
            and p6c.get("historic_source_file_count")==84
            and len(p6c.get("historical_registries_recovered",[]))==5,
            "P6C earlier bounded historic source results changed")
    require(p4a_plan.get("kind")=="BPU8_R3C_P4A_STATIC_SE_INTERFACE_NOT_CORPUS_LOCK"
            and p4a_plan.get("corpus_lock") is False
            and list(p4a_plan.get("cases",{}))==list(order)
            and tuple(p4a_plan.get("future_six_comparators",[]))==EXPECTED_6,
            "P4A original case/profiles altered")
    require(gem5.is_file() and p2.sha(gem5)==EXPECTED_GEM5,
            "gem5 binary has changed from actual P5A/P5B tested binary")
    prereg=load(p4a.CANDIDATE_JSON)
    require(prereg.get("status")=="PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED"
            and prereg.get("no_actual_holdout_runs") is True
            and prereg.get("tracked_bits_each")==45736
            and [x["id"] for x in prereg["suite_candidates"]]==list(order)
            and tuple(prereg["fixed_profiles"])==EXPECTED_6
            and p2.sha(p4a.CANDIDATE_JSON)==
                p6a_snapshot["prereg_source_sha256"],
            "pre-result source prereg altered")
    frozen=load(p4a.R3_MATRIX)
    require(frozen["experiment"]=="BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01"
            and tuple(frozen["profiles"])==EXPECTED_6
            and frozen["workloads"]==p4a_plan["dev_full19_names"]
            and len(frozen["workloads"])==19
            and not set(frozen["workloads"]).intersection(order)
            and all(v["total_bits"]==45736 for v in frozen["profiles"].values()),
            "frozen R3 geometry/source unexpectedly changed")
    require(p6a_snapshot.get("case_count")==11
            and [c["case"] for c in p6a_snapshot["cases"]]==list(order),
            "P6A original case set altered")
    require([r["case"] for r in p6d.get("source_and_licensing_records",[])]==
            list(order)
            and all(r["license_material_present"]
                    for r in p6d["source_and_licensing_records"]),
            "P6D original license evidence not 11/11")
    cases=[]
    for idx,pin in enumerate(p6a_snapshot["cases"]):
        name=pin["case"]
        old=p4a_plan["cases"][name]
        lic=p6d["source_and_licensing_records"][idx]
        require(name==lic["case"]
                and pin["rv64_elf_sha256"]==old["binary_sha256"]
                and pin["rv64_elf_path"]==str(Path(old["binary"]).resolve())
                and pin["argv"]==old["argv"]
                and pin["input_files"]==[
                    {k:entry[k] for k in ("name","sha256","size")}
                    for entry in old["input_files"]]
                and pin["expected_process_exit_code"]==
                    old["expected_process_exit_code"]
                and pin["correctness_gate"]==old["correctness_gate"]
                and pin["stdin_file_relative"]==old["stdin_file_relative"]
                and pin["program_output_file_relative"]==
                    old["program_output_file_relative"],
                name+": original P4A/P6A/P6D case custody diverged")
        elf=Path(old["binary"])
        require(elf.is_file() and p2.sha(elf)==pin["rv64_elf_sha256"],
                name+": ELF content differs from G5-proven plan")
        for entry in old["input_files"]:
            src=Path(entry["source_path"])
            require(src.is_file() and src.stat().st_size==entry["size"]
                    and p2.sha(src)==entry["sha256"],
                    name+": source input changed")
        # Output pin hashes are from the P5A PASS custody, not candidate performance.
        cases.append({
            "case":name,"index":idx,
            "elf":{"path":str(elf.resolve()),
                   "sha256":pin["rv64_elf_sha256"],"size":elf.stat().st_size},
            "argv":pin["argv"],
            "input_files":[
                {"name":i["name"],"source_path":str(Path(i["source_path"]).resolve()),
                 "sha256":i["sha256"],"size":i["size"]}
                for i in old["input_files"]],
            "stdin_file_relative":pin["stdin_file_relative"],
            "expected_process_exit_code":pin["expected_process_exit_code"],
            "program_output_file_relative":pin["program_output_file_relative"],
            "correctness_gate":pin["correctness_gate"],
            "g5_reference_outputs":{
                "stdout_sha256":pin["original_g5_stdout_sha256"],
                "stderr_sha256":pin["original_g5_stderr_sha256"],
                "written_file_sha256":pin["original_g5_output_file_sha256"],
                "first_roi_sha256":pin["original_g5_roi_sha256"],
                "source":"P5A original G5-only control (not a TG geometry result)"},
            "source_kind":old["source_kind"],
            "license":{
                "files":[{"sha256":f["sha256"],"path":f["path"]}
                         for f in lic["license_files"]],
                "publication_or_binary_redistribution":"NOT_APPROVED",
                "case_terms":"MANUAL_REVIEW_PENDING"},
        })
    return {
        "kind":"BPU8_R3C_P7A_LOCK_DRAFT_REQUIRES_REVIEW",
        "verdict":"PRE_RESULT_11x6_CONFIG_DRAFT_NOT_LOCKED_NOT_AUTHORIZED",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "locked_case_count":0,
        "target_case_count":11,
        "target_profiles_per_case":6,
        "target_jobs":66,
        "actual_six_profile_jobs":0,
        "source_evidence_sha256":fingerprints,
        "linked_simulator_gem5_sha256":EXPECTED_GEM5,
        "exact_simulator_path":str(gem5),
        "frozen_r3_geometry_sha256":p2.sha(p4a.R3_MATRIX),
        "frozen_geometry_profiles":frozen["profiles"],
        "profile_order":list(EXPECTED_6),
        "source_revisions":p6d["source_checkouts"],
        "source_limited_prior_exposure":{
            "five_named_archives_checked":5,
            "candidate_digest_occurrences_in_scanned_text":0,
            "pre_R3C_Git_files_checked":84,
            "candidate_name_mentions_in_selected_old_Git_files":0,
            "nonarchived_prior_OCI_runs":"NOT_EXHAUSTIVELY_INVENTORIED",
            "absolute_unseen_claim":False},
        "scope":"INTERNAL_RESEARCH_FIRST_ROI_ONLY_NOT_OFFICIAL_COREMARK",
        "third_party_code_or_binary_distribution":"NOT_AUTHORIZED_BY_THIS_DRAFT",
        "manual_historical_scope_acceptance":"REQUIRED_FOR_FUTURE_LOCK",
        "manual_license_and_use_conditions_acceptance":"REQUIRED_FOR_FUTURE_LOCK",
        "case_list":cases,
        "holdout_result_inspected":False,
        "corpus_lock":"NOT_CREATED",
        "authorized_holdout_jobs":0,
        "approval_status":"DRAFT_ONLY",
        "draft_review_checklist":[
           "Confirm manually no known unarchived MiBench/CoreMark exposure for geometry decisions",
           "Confirm internal-run-only handling; each actual LICENSE reviewed for intended usage",
           "Confirm the 11 fixed cases and literal argument/input/file hashes",
           "Confirm 6 inherited R3 geometries and linked gem5 SHA without edits",
           "Commit a separately reviewed r3c_corpus_lock.json BEFORE any six-profile performance",
           "Do not represent 10-iteration internal CoreMark as official CoreMark score",
        ],
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("p1","p4a","p6a","p6b","p6c","p6d","gem5","out"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    v={name:value.expanduser().resolve() for name,value in vars(args).items()}
    require(not v["out"].exists(),"never overwrite original lock draft")
    named={name:load(v[name]) for name in ("p1","p4a","p6a","p6b","p6c","p6d")}
    fingerprints={name:p2.sha(v[name])
                  for name in ("p1","p4a","p6a","p6b","p6c","p6d")}
    result=validate_chain(
        named["p1"],named["p4a"],named["p6a"],named["p6b"],
        named["p6c"],named["p6d"],fingerprints,v["gem5"],v)
    dest=v["out"]
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x") as stream:
        json.dump(result,stream,indent=2,sort_keys=True,ensure_ascii=False)
        stream.write("\n")
    print("R3C_P7A_DRAFT="+str(dest),flush=True)
    print("R3C_P7A_SHA256="+p2.sha(dest),flush=True)
    print("R3C_P7A_CASES="+str(len(result["case_list"])),flush=True)
    print("R3C_P7A_TARGET_JOBS="+str(result["target_jobs"]),flush=True)
    print("R3C_P7A_VERDICT="+result["verdict"],flush=True)
    print("NO CLAIM: human use/license approval, corpus lock, six-profile results, PPA",flush=True)

if __name__=="__main__":
    try: main()
    except (ValueError,OSError,KeyError,RuntimeError) as e:
        print("R3C_P7A_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
