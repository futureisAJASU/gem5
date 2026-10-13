#!/usr/bin/env python3
"""R3C P6A. Reopen G5 actual RAW evidence and stage an UNLOCKED corpus snapshot.

This script never executes gem5, never accesses candidate TG6/TG7 results,
never changes predictor geometry and NEVER grants historical independence.
Output is CUSTODY_READY_NOT_CORPUS_LOCK; external Holdout MUST NOT run yet.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3_g5_lock_full19 as r3
import bpu_b8_r3c_p4a_static as p4a
import bpu_b8_r3c_p4b_g5_se_feasibility as p4b
import bpu_b8_r3c_p5a_split_raw_audit as p5a
import bpu_b8_r3c_p5b_g5_historical_replay as p5b

EXPECTED_P5A="ORIGINAL_FULL11_G5_RAW_PASS_REPEAT3_SIMSTATE_EQUIVALENT_NOT_CORPUS_LOCK"
EXPECTED_P5B="19_OF_19_G5_REPLAY_EXACT_PASS"
EXPECTED_6=("g5_native","g5_h11","tg6_native","tg6_h11","tg7_native","tg7_h11")

def check(ok: bool, message: str):
    if not ok:
        raise ValueError(message)

def load(path: Path) -> dict:
    check(path.is_file(),"missing JSON source: "+str(path))
    content=json.loads(path.read_text())
    check(isinstance(content,dict),"invalid JSON object: "+str(path))
    return content

def validate_ledger(plan: dict, p5: dict, p5b_mf: dict, g5: Path,
                    original_dir: Path, repeat_dir: Path) -> list[dict]:
    """No results visibility: only input/output SHA provenance and 6-way plan."""
    order=tuple(p2.ORDER)
    check(tuple(plan["cases"])==order,"P4A plan order drift")
    check(p5.get("kind")=="BPU8_R3C_P5A_SPLIT_G5_ONLY_RAW_RECOVERY"
          and p5.get("verdict")==EXPECTED_P5A,"P5A not a completed RAW proof")
    check(p5.get("original_run_mode")=="FULL11_COMPLETE_ORIGINAL"
          and p5.get("original_full11_final_manifest_verified") is True
          and p5.get("first_console_witness_complete") is True
          and p5.get("corpus_locked") is False
          and p5.get("six_profile_holdout_executions")==0,
          "P5A provenance tier changed")
    check(p5.get("gem5_sha256")==p5a.EXPECTED_GEM5,
          "P5A linked binary SHA drift")
    check(p5b_mf.get("kind")==
          "BPU8_R3C_P5B_NEW_GEM5_G5_ONLY_HISTORICAL_REPLAY"
          and p5b_mf.get("verdict")==EXPECTED_P5B
          and p5b_mf.get("new_gem5_sha256")==p5a.EXPECTED_GEM5
          and p5b_mf.get("old_r3_gem5_sha256")==p5b.HISTORICAL_SHA
          and p5b_mf.get("profile")=="g5_native"
          and p5b_mf.get("compared_profiles")==[]
          and p5b_mf.get("holdout_jobs")==0,
          "P5B original historical replay provenance changed")
    check(len(p5b_mf.get("cases",{}))==19
          and all(row.get("pass") is True
                  for row in p5b_mf["cases"].values()),
          "P5B 19 individual replay records not PASS")
    check(tuple(plan["future_six_comparators"])==EXPECTED_6,
          "source-predeclared 6 profiles/order drift")
    geometries=r3.load_matrix()["profiles"]
    check(tuple(geometries)==EXPECTED_6,"frozen R3 profile order changed")
    check(all(x["total_bits"]==45736 for x in geometries.values()),
          "geometry bit budget changed")
    check(g5.is_file() and p2.sha(g5)==p5a.EXPECTED_GEM5,
          "linked gem5 SHA mismatch")
    original_mf=original_dir/"g5_functional_manifest.json"
    check(original_mf.is_file()
          and p2.sha(original_mf)==p5.get("original_final_manifest_sha256"),
          "original full11 gem5 manifest changed after P5A")
    check(len(p5.get("cases",[]))==11
          and [c.get("workload") for c in p5["cases"]]==list(order)
          and all(c.get("passed") is True for c in p5["cases"]),
          "P5A original 11 case list/result altered")
    expected_rep=("adpcm_encode","stringsearch","coremark_performance")
    reps=p5.get("three_repeat_cases",[])
    check(len(reps)==3
          and tuple(r.get("case") for r in reps)==expected_rep
          and all(r.get("pass") is True for r in reps),
          "P5A duplicate3 missing")
    for r in reps:
        proof=r.get("roi_semantic_verification",{})
        check(proof.get("all_simulated_roi_bytes_identical_excluding_explicit_host_fields")
              is True and
              set(proof.get("host_only_fields_whitelist",[]))==
              p5a.HOST_ONLY_FIRST_ROI_FIELDS,
              r["case"]+": no host-only ROI equality proof")
        name=r["case"]
        original=original_dir/name/"sim"/"roi.stats"
        repeated=repeat_dir/name/"sim"/"roi.stats"
        actual=p5a.verify_repeat_roi_semantics(original,repeated)
        check(actual==proof
              and p2.sha(original)==r["original_roi_sha256"]
              and p2.sha(repeated)==r["repeat_roi_sha256"],
              name+": repeat3 source ROI content drift")
    rows=[]
    for info in p5["cases"]:
        name=info["workload"]
        row=plan["cases"][name]
        binary=Path(row["binary"])
        check(binary.is_file() and p2.sha(binary)==row["binary_sha256"]
              and info["elf_sha256"]==row["binary_sha256"],
              name+": staged binary ELF SHA wrong")
        inputs=[]
        for inp in row["input_files"]:
            original=Path(inp["source_path"])
            staged=original_dir/name/"work"/inp["name"]
            for candidate in (original,staged):
                check(candidate.is_file() and candidate.stat().st_size==inp["size"]
                      and p2.sha(candidate)==inp["sha256"],
                      name+": source/staged input SHA drift")
            inputs.append(dict(name=inp["name"],sha256=inp["sha256"],
                               size=inp["size"]))
        first=original_dir/name/"sim"/"roi.stats"
        stdout=original_dir/name/"work"/"program.stdout"
        stderr=original_dir/name/"work"/"program.stderr"
        check(first.is_file() and p2.sha(first)==info["roi_sha256"],
              name+": original first ROI SHA drift")
        for part,hash_value in info["raw_sha256"].items():
            raw=original_dir/name/"sim"/part
            check(raw.is_file() and p2.sha(raw)==hash_value,
                  name+": original complete RAW SHA changed for "+part)
        for stream in ("gem5.stdout","gem5.stderr"):
            full=original_dir/name/stream
            check(full.is_file() and p2.sha(full)==info[
                      stream.replace(".","_")+"_sha256"],
                  name+": original gem5 log SHA changed for "+stream)
        check(stdout.is_file() and p2.sha(stdout)==info["app_stdout_sha256"]
              and stderr.is_file() and p2.sha(stderr)==info["app_stderr_sha256"],
              name+": original output SHA drift")
        check(info["storageBits"]==45736,
              name+": G5 accounted bits wrong")
        check(info["source_root"]==str((original_dir/name).resolve()),
              name+": original P5A raw root diverged")
        rows.append({
            "case":name,
            "source_kind":row["source_kind"],
            "rv64_elf_sha256":row["binary_sha256"],
            "rv64_elf_path":str(binary.resolve()),
            "expected_process_exit_code":row["expected_process_exit_code"],
            "argv":row["argv"],
            "stdin_file_relative":row["stdin_file_relative"],
            "input_files":inputs,
            "program_output_file_relative":row["program_output_file_relative"],
            "correctness_gate":row["correctness_gate"],
            "original_g5_stdout_sha256":info["app_stdout_sha256"],
            "original_g5_stderr_sha256":info["app_stderr_sha256"],
            "original_g5_output_file_sha256":info["output_file_sha256"],
            "original_g5_roi_sha256":info["roi_sha256"],
            "raw_first_roi_verified_only_with_G5":True,
            "previous_geometry_development_exact_binary_input_reuse":
                "UNRESOLVED_REQUIRE_PRIOR_RECORD_SEARCH",
        })
    return rows

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("p4a_plan","p5a_ledger","p5b_manifest","first_dir",
                 "remaining_dir","gem5","out"):
        ap.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    x=ap.parse_args()
    v={k:p.expanduser().resolve() for k,p in vars(x).items()}
    check(not v["out"].exists(),
          "output already exists; never silently rewrite a prereg custody file")
    plan=load(v["p4a_plan"])
    p5=load(v["p5a_ledger"])
    hist=load(v["p5b_manifest"])
    check(plan["kind"]=="BPU8_R3C_P4A_STATIC_SE_INTERFACE_NOT_CORPUS_LOCK"
          and plan["corpus_lock"] is False,
          "P4A unexpectedly marks corpus locked")
    check(p5.get("p4a_plan_sha256")==p2.sha(v["p4a_plan"]),
          "P5A vs P4A plan SHA mismatch")
    rows=validate_ledger(plan,p5,hist,v["gem5"],
                         v["first_dir"],v["remaining_dir"])
    prereg=p4a.CANDIDATE_JSON
    candidates=load(prereg)
    check(candidates.get("experiment")=="BPU8_R3C_EXTERNAL_HOLDOUT_P0"
          and candidates.get("no_actual_holdout_runs") is True
          and candidates.get("tracked_bits_each")==45736
          and tuple(candidates.get("fixed_profiles",[]))==EXPECTED_6
          and [i["id"] for i in candidates["suite_candidates"]]==[i["case"] for i in rows],
          "original prereg candidate order, geometry, or null-result status changed")
    data={
        "kind":"R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT",
        "verdict":"11_CASE_CUSTODY_CHECKED_HISTORICAL_INDEPENDENCE_NOT_VERIFIED_NOT_LOCKED",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "prereg_source_sha256":p2.sha(prereg),
        "p4a_plan_sha256":p2.sha(v["p4a_plan"]),
        "p5a_evidence_ledger_sha256":p2.sha(v["p5a_ledger"]),
        "p5b_g5_historical_replay_manifest_sha256":p2.sha(v["p5b_manifest"]),
        "simulator_gem5_sha256":p5a.EXPECTED_GEM5,
        "six_profiles":list(EXPECTED_6),
        "logical_bits_each":45736,
        "case_count":len(rows),"candidate_performance_jobs_NOT_authorized":len(rows)*6,
        "cases":rows,
        "historical_unseen_workload_independence":"UNVERIFIED",
        "historical_manifest_search":"NOT_YET_GROUNDED_IN_EXHAUSTIVE_PRIOR_RECORDS",
        "licenses_prior_art_review":"NOT_SIGNED_OFF",
        "source_and_inputs_immutable_commit":"NOT_CREATED",
        "r3c_corpus_lock":"NOT_CREATED",
        "comparison_performance_started":False,
        "next_actions":[
           "Check EVERY prior relevant development manifest for case source/input and ELF SHA, not name alone",
           "Review upstream license and patch provenance and exact RV64 build flags from P1/P2/P2B",
           "Review ROI semantics and paired instruction counts; document method and any historical exposure",
           "Commit separate fail-closed r3c_corpus_lock.json BEFORE TG6/TG7/h11 simulation",
           "Run fixed six-profile array without retuning or editing case list post-results",
        ],
        "scope_limit":"P6A is nonperformance custody staging. This document IS NOT a corpus lock.",
    }
    dest=v["out"]
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x") as stream:
        json.dump(data,stream,indent=2,ensure_ascii=False,sort_keys=True)
        stream.write("\n")
    print("R3C_P6A_SNAPSHOT="+str(dest),flush=True)
    print("R3C_P6A_SHA256="+p2.sha(dest),flush=True)
    print("R3C_P6A_VERDICT="+data["verdict"],flush=True)
    print("NO CLAIM: historical unseen independence, locked corpus, "
          "six-profile holdout, or SRAM/RTL PPA",flush=True)

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,RuntimeError,KeyError,AssertionError) as error:
        print("R3C_P6A_FAIL_CLOSED: "+str(error),file=sys.stderr)
        sys.exit(1)
