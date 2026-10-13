#!/usr/bin/env python3
"""R3C P6C: bounded source-history review, NEVER a corpus lock.

Bind the current P6A and P6B SHA evidence, then inspect BPU experimental
scripts/registries as they existed at the pre-R3C R3 source commit. Record
every exact external-candidate name mention and every MiBench/CoreMark root
reference for HUMAN review. Zero hits never proves worldwide/OCI completeness.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2

R3_PRE_R3C="f3f3fa41fcf883a3e077296ac4b2c7a02e74e1d6"
P6A_VERDICT="11_CASE_CUSTODY_CHECKED_HISTORICAL_INDEPENDENCE_NOT_VERIFIED_NOT_LOCKED"
P6B_VERDICT="PRIOR_EVIDENCE_DISCOVERY_REQUIRES_COMPLETENESS_REVIEW_NO_CORPUS_LOCK"
CASE_NAMES=tuple(p2.ORDER)
ROOTS=("mibench","coremark")
ANCIENT_REGISTRIES=("docs/bpu8_tage_isobit_r1.json",
                    "docs/bpu8_r2a_capacity_knee_v01.json",
                    "docs/bpu8_r2b_geometry_frontier_v01.json",
                    "docs/bpu8_r2c_fixed_hash11_freeze_gate_v01.json",
                    "docs/bpu8_r3_g5_lock_v01.json")
def require(ok,reason):
    if not ok:
        raise ValueError(reason)

def git(*args):
    result=subprocess.run(["git",*args],cwd=p2.ROOT,text=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=45)
    require(result.returncode==0,
            "Git historical source unavailable: "+" ".join(args)+" "+result.stderr[:300])
    return result.stdout

def relevant_file(path:str)->bool:
    """Only historic local BPU campaign scripts/docs/test registries."""
    if "r3c" in path.lower():
        return False
    return (
       (path.startswith("scripts/bpu_") and path.endswith((".py",".sh")))
       or (path.startswith("docs/BPU_B") and path.endswith(".md"))
       or (path.startswith("docs/bpu8_") and path.endswith(".json"))
       or (path.startswith("tests/bpu") and path.endswith(".py"))
    )

def corpus_refs(source:str, all_cases=CASE_NAMES)->list[dict]:
    """Find explicit whole-token external benchmark names, never substring-only."""
    results=[]
    for i,line in enumerate(source.splitlines(),1):
        mentions=sorted({case for case in all_cases
                         if re.search(r"(?<![A-Za-z0-9_])"+re.escape(case)+
                                      r"(?![A-Za-z0-9_])",line,re.IGNORECASE)})
        roots=sorted({word for word in ROOTS
                      if re.search(r"\b"+word+r"\b",line,re.IGNORECASE)})
        if mentions or roots:
            results.append({"line":i,"candidate_names":mentions,"source_roots":roots,
                            "excerpt":line[:240]})
    return results

def stage(p6a:dict,p6b:dict,files:dict,pre_r3:dict)->dict:
    require(p6a.get("verdict")==P6A_VERDICT
            and p6a.get("r3c_corpus_lock")=="NOT_CREATED"
            and p6a.get("historical_unseen_workload_independence")=="UNVERIFIED",
            "P6A unresolved-state gate changed")
    require(p6b.get("verdict")==P6B_VERDICT
            and p6b.get("corpus_lock")=="NOT_AUTHORIZED"
            and p6b.get("independence_of_11_cases")=="NOT_DETERMINED"
            and len(p6b.get("prior_sources",[]))>=1,
            "P6B evidence or no-lock guard mutated")
    require(len(files)>0 and all(relevant_file(p) for p in files),
            "historical files missing or include forbidden R3C data")
    workloads=pre_r3["workloads"]
    require(len(workloads)==19 and
            not (set(workloads) & set(CASE_NAMES)),
            "old R3 exact workload name set overlaps external candidates")
    require(pre_r3["experiment"]=="BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01",
            "historic R3 JSON identity drift")
    roots=[]
    flagged=[]
    campaign_scripts=[]
    for path,content in sorted(files.items()):
        uses=corpus_refs(content)
        if path.startswith("scripts/bpu_"):
            campaign_scripts.append(path)
        if uses:
            flagged.append({"path":path,"references":uses})
        if path in ANCIENT_REGISTRIES:
            x=json.loads(content)
            if "workloads" in x:
                refs=x["workloads"]
                require(isinstance(refs,list)
                        and not set(refs).intersection(CASE_NAMES),
                        "earlier registry contains exact candidate workload names")
                roots.append({"path":path,"old_workloads":refs})
    require(set(ANCIENT_REGISTRIES)=={r["path"] for r in roots},
            "required five R1/R2A/R2B/R2C/R3 workload registries incomplete")
    require(len(campaign_scripts)>=12,
            "too few historic BPU campaign scripts examined")
    return {
      "historic_source_file_count":len(files),
      "historic_bpu_scripts_reviewed":len(campaign_scripts),
      "historical_registries_recovered":roots,
      "manual_review_mentions":flagged,
      "reference_file_count":len(flagged),
      "historical_named_benchmarks":workloads,
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p6a",type=Path,required=True)
    ap.add_argument("--p6b",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    p6ap=a.p6a.expanduser().resolve()
    p6bp=a.p6b.expanduser().resolve()
    dest=a.out.expanduser().resolve()
    require(not dest.exists(),"output exists")
    a6=json.loads(p6ap.read_text())
    b6=json.loads(p6bp.read_text())
    require(b6["p6a_sha256"]==p2.sha(p6ap),
            "P6B linked different P6A snapshot")
    require(git("rev-parse",R3_PRE_R3C).strip()==R3_PRE_R3C,
            "expected historical commit unavailable")
    paths=git("ls-tree","-r","--name-only",R3_PRE_R3C).splitlines()
    selected=[p for p in paths if relevant_file(p)]
    require(len(selected)>=20,"historical campaign source inventory unexpectedly small")
    require(all(x in selected for x in ANCIENT_REGISTRIES),
            "historical registry absent")
    data={}
    for path in selected:
        data[path]=git("show",R3_PRE_R3C+":"+path)
    old=json.loads(data["docs/bpu8_r3_g5_lock_v01.json"])
    reviewed=stage(a6,b6,data,old)
    result={
      "kind":"BPU8_R3C_P6C_BOUND_HISTORICAL_SOURCE_AUDIT",
      "verdict":"PRE_R3C_GIT_SOURCE_BOUNDARY_REVIEWED_HISTORICAL_COMPLETENESS_UNVERIFIED_NO_LOCK",
      "created_utc":datetime.now(timezone.utc).isoformat(),
      "historical_git_commit":R3_PRE_R3C,
      "historical_git_commit_tree_sha":git("rev-parse",R3_PRE_R3C+"^{tree}").strip(),
      "p6a_sha256":p2.sha(p6ap),
      "p6b_sha256":p2.sha(p6bp),
      "p6b_archive_count":len(b6["prior_sources"]),
      "p6b_exact_candidate_hash_occurrence_sources":
          len(b6.get("prior_exact_candidate_SHA_occurrences",[])),
      "p6b_skipped_or_unreadable_count":
          len(b6.get("skipped_or_unreadable_members",[])),
      **reviewed,
      "historical_source_file_sha256":{
          name: __import__("hashlib").sha256(content.encode()).hexdigest()
          for name,content in sorted(data.items())},
      "source_review_scope":
          "Tracked BPU experiment scripts/docs and R1–R3 registries at the fixed "
          "pre-R3C R3 commit; plus P6B five user-supplied archive text inventories",
      "not_reviewed":["other privately executed OCI scripts/jobs not archived",
                      "binary ELF content without comparable historic manifest",
                      "any past workload run absent in Git history and five archives",
                      "license terms or upstream distribution permissions",
                      "gem5 architectural config/physical RTL provenance"],
      "qualifying_untouched_holdout":"NOT_PROVEN",
      "corpus_lock":"NOT_CREATED",
      "authorized_six_profile_jobs":0,
    }
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.write("\n")
    print("R3C_P6C_SNAPSHOT="+str(dest))
    print("R3C_P6C_SHA256="+p2.sha(dest))
    print("R3C_P6C_SOURCE_FILES="+str(result["historic_source_file_count"]))
    print("R3C_P6C_REGISTRIES="+str(len(result["historical_registries_recovered"])))
    print("R3C_P6C_REFERENCED_FILES="+str(result["reference_file_count"]))
    print("R3C_P6C_VERDICT="+result["verdict"])
    print("NO CLAIM: exhaustive OCI experiments, source licenses, corpus lock or holdout results")

if __name__=="__main__":
    try:main()
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as e:
        print("R3C_P6C_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
