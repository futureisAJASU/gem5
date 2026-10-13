#!/usr/bin/env python3
"""P6D — source license/provenance inventory, NOT a license or corpus signoff.

Uses pinned P1 git/source custody plus passed P6A/B/C discovery evidence.
Produces one final manual-review dossier without inspecting TG6/TG7
performance, creating corpus_lock.json, or running any gem5 job.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2

P6A_VERDICT="11_CASE_CUSTODY_CHECKED_HISTORICAL_INDEPENDENCE_NOT_VERIFIED_NOT_LOCKED"
P6B_VERDICT="PRIOR_EVIDENCE_DISCOVERY_REQUIRES_COMPLETENESS_REVIEW_NO_CORPUS_LOCK"
P6C_VERDICT="PRE_R3C_GIT_SOURCE_BOUNDARY_REVIEWED_HISTORICAL_COMPLETENESS_UNVERIFIED_NO_LOCK"
LIC_NAMES=("LICENSE","LICENSE.md","LICENSE.txt","LICENSE.TXT","license",
           "COPYING","COPYING.txt","COPYRIGHT","Copyright")
EXPECTED_CASES=tuple(p2.ORDER)

def require(ok,msg):
    if not ok:raise ValueError(msg)

def load(path:Path):
    require(path.is_file(),"source JSON absent: "+str(path))
    data=json.loads(path.read_text())
    require(isinstance(data,dict),"source JSON not an object")
    return data

def worktree(head:dict):
    base=Path(head["path"]).resolve()
    require(base.is_dir(),"pinned source checkout missing: "+str(base))
    actual=p2.git_head(base)
    require(actual==head["git_head"],
            "source commit changed: "+str(base))
    status=subprocess.run(
        ["git","status","--porcelain","--untracked-files=no"],cwd=base,
        capture_output=True,text=True,timeout=30,check=True)
    require(not status.stdout.strip(),
            "source checkout has tracked modifications: "+str(base))
    return base

def candidate_license_records(name:str,root:Path,original:dict):
    """Record exactly what each original P1 snapshot hashed, no inference."""
    subset=original["candidate_sources"][name]
    folder=root/subset["source_subdir"]
    require(folder.is_dir(),"source program missing: "+name)
    for f in subset["files"]:
        target=folder/f["path"]
        require(target.is_file() and target.stat().st_size==f["size"]
                and p2.sha(target)==f["sha256"],
                "original P1 source file mutated: "+str(target))
    declared={f["path"]:f for f in subset["files"]}
    licenses=[]
    for candidate in LIC_NAMES:
        if candidate not in declared:
            continue
        licensefile=folder/candidate
        licenses.append({
            "path":str(licensefile.resolve()),
            "sha256":declared[candidate]["sha256"],
            "size":declared[candidate]["size"],
            "human_license_terms_examined":"PENDING",
        })
    return {"case":name,"source_subdir":subset["source_subdir"],
            "source_files_p1_verified":len(declared),
            "license_files":licenses,
            "license_material_present":bool(licenses),
            "license_classification":"REQUIRES_HUMAN_REVIEW",
            "external_distribution_rights":"NOT_DETERMINED"}

def dossier(p1:dict,p6a:dict,p6b:dict,p6c:dict,
            p1sha:str,p6asha:str,p6bsha:str,p6csha:str):
    require(p1.get("kind")=="BPU8_R3C_P1_SOURCE_CUSTODY_NO_COMPILE_NO_RUN"
            and p1.get("verdict")=="SOURCE_TREE_PRESENT_NOT_CORPUS_LOCK"
            and not p1.get("missing_source_paths"),
            "P1 source inventory not valid")
    require(p6a.get("kind")=="R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT"
            and p6a.get("verdict")==P6A_VERDICT
            and p6a.get("r3c_corpus_lock")=="NOT_CREATED"
            and len(p6a.get("cases",[]))==11
            and tuple(x["case"] for x in p6a["cases"])==EXPECTED_CASES,
            "P6A evidence not ready")
    require(p6b.get("verdict")==P6B_VERDICT
            and p6b.get("p6a_sha256")==p6asha
            and p6b.get("corpus_lock")=="NOT_AUTHORIZED"
            and len(p6b.get("prior_sources",[]))==5,
            "P6B prior 5 archive audit missing")
    require(p6c.get("verdict")==P6C_VERDICT
            and p6c.get("p6a_sha256")==p6asha
            and p6c.get("p6b_sha256")==p6bsha
            and p6c.get("corpus_lock")=="NOT_CREATED"
            and p6c.get("qualifying_untouched_holdout")=="NOT_PROVEN"
            and p6c.get("historic_source_file_count",0)>=84
            and len(p6c.get("historical_registries_recovered",[]))==5,
            "P6C source history review incomplete")
    mroot=worktree(p1["mibench"])
    croot=worktree(p1["coremark"])
    records=[candidate_license_records(name,mroot,p1)
             for name in EXPECTED_CASES if name!="coremark_performance"]
    corelic=croot/"LICENSE.md"
    licrec=p1["coremark_sources"]["LICENSE.md"]
    require(corelic.is_file() and p2.sha(corelic)==licrec["sha256"],
            "CoreMark official-use license bytes altered")
    records.append({
        "case":"coremark_performance",
        "source_subdir":".",
        "source_files_p1_verified":len(p1["coremark_sources"]),
        "license_files":[{
           "path":str(corelic.resolve()),"sha256":licrec["sha256"],
           "size":corelic.stat().st_size,
           "human_license_terms_examined":"PENDING"}],
        "license_material_present":True,
        "license_classification":"EEMBC_ACCEPTABLE_USE_REVIEW_REQUIRED",
        "external_distribution_rights":"NOT_DETERMINED",
        "official_coremark_score":"NOT_CLAIMED_INTERNAL_10_ITERATION_ROI",
    })
    require([r["case"] for r in records]==list(EXPECTED_CASES),
            "P6D exact source identity/order drift")
    return {
        "kind":"BPU8_R3C_P6D_FINAL_PRELOCK_SOURCE_AND_LICENSE_DOSSIER",
        "verdict":"EVIDENCE_READY_FOR_MANUAL_LOCK_SIGNOFF_NOT_CORPUS_LOCK",
        "p1_source_sha256":p1sha,
        "p6a_sha256":p6asha,
        "p6b_sha256":p6bsha,
        "p6c_sha256":p6csha,
        "p6a_user_snapshot_claim":"ORIGINAL_11_G5_AND_REPEAT3_VERIFIED",
        "historical_coverage":"FIVE_OLD_ARCHIVES_AND_84_PRE_R3C_GIT_FILES_ONLY",
        "historical_SHA_hits_in_declared_five_archives":
           len(p6b.get("prior_exact_candidate_SHA_occurrences",[])),
        "historical_name_reference_files_at_pre_R3C_commit":
           p6c.get("reference_file_count"),
        "source_checkouts":{
           "mibench":{"url":p1["mibench"].get("git_remote_origin"),
                      "commit":p1["mibench"]["git_head"],
                      "source_status":"PINNED_P1_BYTES_REVERIFIED"},
           "coremark":{"url":p1["coremark"].get("git_remote_origin"),
                       "commit":p1["coremark"]["git_head"],
                       "source_status":"PINNED_P1_BYTES_REVERIFIED"},
        },
        "source_and_licensing_records":records,
        "per_case_binaries_and_inputs_sha_in_p6a":
           [{k:x[k] for k in ("case","rv64_elf_sha256","argv",
                              "input_files","expected_process_exit_code",
                              "correctness_gate","original_g5_roi_sha256")}
            for x in p6a["cases"]],
        "manual_lock_signoff_requirements":[
           "Read and preserve each actual source license; especially MiBench GPL and notice conditions",
           "Decide internal academic use, redistribution conditions, and whether upstream mirror attribution is sufficient",
           "Review historical investigation scope/remaining nonarchived workloads: qualified no-known-exposure, not absolute-unseen",
           "Confirm source P2 original 9 and P2B LP64 2, QEMU output gate scope and input/argv/exit contracts",
           "Review CoreMark short-run limitations and patch-specific license obligations",
           "Commit separate exact hashes and case manifest as r3c_corpus_lock.json before any candidate performance comparison",
        ],
        "manual_license_review":"REQUIRED",
        "manual_historical_exposure_signoff":"REQUIRED",
        "r3c_corpus_lock":"NOT_CREATED",
        "authorized_six_profile_holdout_runs":0,
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("p1","p6a","p6b","p6c","out"):
        ap.add_argument("--"+key,type=Path,required=True)
    args=ap.parse_args()
    v={k:p.expanduser().resolve() for k,p in vars(args).items()}
    require(not v["out"].exists(),"preserve old evidence; choose new --out")
    rows={k:load(v[k]) for k in ("p1","p6a","p6b","p6c")}
    hashes={k:p2.sha(v[k]) for k in ("p1","p6a","p6b","p6c")}
    result=dossier(rows["p1"],rows["p6a"],rows["p6b"],rows["p6c"],
                   hashes["p1"],hashes["p6a"],hashes["p6b"],hashes["p6c"])
    dest=v["out"]
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.write("\n")
    print("R3C_P6D_DOSSIER="+str(dest))
    print("R3C_P6D_SHA256="+p2.sha(dest))
    print("R3C_P6D_CASES="+str(len(result["source_and_licensing_records"])))
    print("R3C_P6D_LIC_MATERIAL_PRESENT="+str(sum(
       1 for row in result["source_and_licensing_records"]
       if row["license_material_present"])))
    print("R3C_P6D_VERDICT="+result["verdict"])
    print("NO CLAIM: legal approval, unrestricted redistribution, absolute historical independence, "
          "corpus lock or six-profile Holdout")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as e:
        print("R3C_P6D_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
