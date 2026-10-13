#!/usr/bin/env python3
"""P5A: audit split G5-only first-ROI RAW (8 SSH-interrupted + 3 resumed).

No simulator invocation, no corpus freeze, no comparison profiles. First run
may lack a final manifest after the SSH session disconnected.
"""
import argparse, hashlib, json, sys
from pathlib import Path
import bpu_b8_r3_g5_lock_full19 as r3
import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p4a_static as p4a
import bpu_b8_r3c_p4b_g5_se_feasibility as p4b

FIRST=("basicmath","bitcount","qsort","susan_edges","dijkstra",
       "patricia","rijndael_encrypt","fft")
LAST=("adpcm_encode","stringsearch","coremark_performance")
EXPECTED_GEM5="12681de7975d5082b64dee6e085585dbbd1d078fa7be7f477f4553ab98344a1a"

def require(ok,msg):
    if not ok: raise ValueError(msg)

def console_passes(path):
    require(path.is_file(),"missing original console: "+str(path))
    lines=path.read_text(errors="replace").splitlines()
    return [line[len("R3C_P4B_G5_ONLY "):-len(": PASS")]
            for line in lines if line.startswith("R3C_P4B_G5_ONLY ")
            and line.endswith(": PASS")]

def manifest(path):
    return json.loads(path.read_text()) if path.is_file() else None

def recheck_one(case, root, plan, profile, gem5, p3a, p3b, snapshot):
    case_root=root/case; sim=case_root/"sim"; work=case_root/"work"
    contract=plan["cases"][case]
    gate={
        "argv":p4b.build_command(gem5,p4a.R3C_CONFIG,contract,sim,work,profile),
        "cwd":str(work),
        "expected_exit":contract["expected_process_exit_code"],
    }
    require((case_root/"command.json").is_file(),case+" missing command.json")
    require(json.loads((case_root/"command.json").read_text())==gate,
            case+" execution cmd / cwd / G5 profile drift")
    require(p2.sha(contract["binary"])==contract["binary_sha256"],
            case+" target RV64 ELF changed")
    for i in contract["input_files"]:
        src=work/i["name"]
        require(src.is_file() and src.stat().st_size==i["size"]
                and p2.sha(src)==i["sha256"],case+" input bytes changed")
    for f in ("gem5.stdout","gem5.stderr","sim/stats.txt","sim/roi.stats",
              "sim/config.ini","work/program.stdout","work/program.stderr"):
        require((case_root/f).is_file(),case+" missing RAW "+f)
    simulated_exit=p4b.extract_sim_exit(
        (case_root/"gem5.stdout").read_text(errors="replace"))
    require(simulated_exit==contract["expected_process_exit_code"],
            case+" wrong simulated exit code")
    matrix=r3.load_matrix()
    r3.validate_r3_ini(sim/"config.ini","g5_native",matrix["profiles"])
    stats,roi=r3.parse_first_roi(sim/"stats.txt")
    require((sim/"roi.stats").read_text()==roi,
            case+" stored first ROI differs from original stats.txt")
    row=r3.inspect_row(stats,"g5_native",case,profile,p2.sha(sim/"roi.stats"))
    require(row["simTicks"]>0 and row["simInsts"]>0 and row["storageBits"]==45736,
            case+" ROI/geometry invalid")
    reference=p4b.reference_paths(case,p3a,p3b,contract["reference"])
    output=p4b.expected_output_file(case,p3a,p3b,contract["reference"])
    actual=work/contract["program_output_file_relative"] if contract["program_output_file_relative"] else None
    evaluated=p4b.compare_program(case,
          (work/"program.stdout").read_bytes(),(work/"program.stderr").read_bytes(),
          reference["stdout"].read_bytes(),reference["stderr"].read_bytes(),
          output,actual)
    require(evaluated["passed"],case+" QEMU RV64 functional reference mismatch")
    actual_raw={f:p2.sha(sim/f) for f in ("stats.txt","roi.stats","config.ini")}
    if snapshot is not None:
        require(snapshot["pass"] is True
             and snapshot["status"]=="G5_SE_FUNCTIONAL_ROI_PASS_NO_COMPARISON"
             and snapshot["gem5_runner_rc"]==0 and snapshot["timeout"] is False
             and snapshot["simulated_exit_code"]==simulated_exit,
             case+" final runner status mismatch")
        require(snapshot["raw"]==actual_raw
             and snapshot["roi_inspect_sha256"]==hashlib.sha256(
                json.dumps(row,sort_keys=True).encode()).hexdigest(),
             case+" original ROI disagrees with runner snapshot")
        require(snapshot["gem5_stdout_sha256"]==p2.sha(case_root/"gem5.stdout")
             and snapshot["gem5_stderr_sha256"]==p2.sha(case_root/"gem5.stderr"),
             case+" gem5 console SHA drift")
    return {
        "workload":case,"source_root":str(case_root),
        "runner_evidence":"verified_runner_manifest_and_original_RAW" if snapshot
                else "original_console_PASS_and_original_RAW_no_final_manifest",
        "simulated_exit_code":simulated_exit,
        "elf_sha256":contract["binary_sha256"],
        "simTicks":row["simTicks"],"simInsts":row["simInsts"],
        "committedConditionalPredictions":row["committedConditionalPredictions"],
        "committedConditionalWrong":row["committedConditionalWrong"],
        "mpki":row["mpki"],"storageBits":row["storageBits"],
        "r3CauseJson":row["r3CauseJson"],
        "historyRestoreChecks":row["historyRestoreChecks"],
        "historyStateRestores":row["historyStateRestores"],
        "roi_sha256":actual_raw["roi.stats"],
        "raw_sha256":actual_raw,
        "app_stdout_sha256":p2.sha(work/"program.stdout"),
        "app_stderr_sha256":p2.sha(work/"program.stderr"),
        "output_file_sha256":p2.sha(actual) if actual else None,
        "gem5_stdout_sha256":p2.sha(case_root/"gem5.stdout"),
        "gem5_stderr_sha256":p2.sha(case_root/"gem5.stderr"),
        "passed":True,
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ("p4a_plan","p3a_dir","p3b_dir","first_dir","remaining_dir",
                "first_console","remaining_console","gem5","out"):
        ap.add_argument("--"+arg.replace("_","-"),type=Path,required=True)
    args=ap.parse_args()
    v={k:p.expanduser().resolve() for k,p in vars(args).items()}
    require(not v["out"].exists(),"output already exists")
    gem5=v["gem5"];plan_path=v["p4a_plan"]
    require(gem5.is_file() and p2.sha(gem5)==EXPECTED_GEM5,
            "current gem5 binary not the observed SHA")
    require(tuple(p2.ORDER)==FIRST+LAST,"pre-registered case order altered")
    plan=json.loads(plan_path.read_text())
    control=p4b.verify_plan(plan,gem5,plan_path,v["p3a_dir"],v["p3b_dir"])
    require(console_passes(v["first_console"])==list(FIRST),
            "first interrupted console missing expected 8/8 exact PASS")
    require(console_passes(v["remaining_console"])==list(LAST),
            "resumed console missing expected 3/3 exact PASS")
    first=manifest(v["first_dir"]/"g5_functional_manifest.json")
    last=manifest(v["remaining_dir"]/"g5_functional_manifest.json")
    require(last is not None
            and last["verdict"]=="G5_ONLY_FEASIBILITY_PASS_NO_CORPUS_LOCK",
            "resumed runner final manifest not passed")
    for label,m,subset in (("first",first,FIRST),("last",last,LAST)):
        if m is None: continue
        require(m["kind"]=="BPU8_R3C_P4B_G5_ONLY_SE_FIRST_ROI_FEASIBILITY"
                and m["control_profile"]=="g5_native"
                and m["control_bp_type"]==control["bp_type"]
                and m["corpus_locked"] is False
                and m["compared_profiles"]==[]
                and m["simulated_performance_claims"]==0,
                label+" manifest provenance invalid")
        require(m["gem5_sha256"]==EXPECTED_GEM5
                and m["p4a_plan_sha256"]==p2.sha(plan_path)
                and m["r3c_adapter_sha256"]==p2.sha(p4a.R3C_CONFIG)
                and m["p3a_manifest_sha256"]==
                    p2.sha(v["p3a_dir"]/"functional_manifest.json")
                and m["p3b_manifest_sha256"]==
                    p2.sha(v["p3b_dir"]/"functional_manifest.json"),
                label+" SHA custody changed")
        require(m["attempted_cases"]==list(subset) or
                (label=="first" and m["attempted_cases"]==list(FIRST+LAST)),
                label+" unexpected target list")
        require(set(m["cases"])==set(subset),label+" recorded case set mismatch")
    extras=[p.name for p in v["first_dir"].iterdir()
            if p.is_dir() and p.name not in FIRST]
    require(all(x in LAST for x in extras),
            "unknown extra case from interrupted run")
    results=[]
    for case in FIRST+LAST:
        earlier=case in FIRST;folder=v["first_dir"] if earlier else v["remaining_dir"]
        mf=first if earlier else last
        record=recheck_one(case,folder,plan,control,gem5,
                           v["p3a_dir"],v["p3b_dir"],
                           mf["cases"][case] if mf else None)
        results.append(record)
        print("R3C_P5A_RAW "+case+": PASS",flush=True)
    require(len(results)==11 and len({x["workload"] for x in results})==11,
            "not exactly 11 G5-only cases")
    result={
        "kind":"BPU8_R3C_P5A_SPLIT_G5_ONLY_RAW_RECOVERY",
        "verdict":"11_CASE_G5_ONLY_RAW_FUNCTIONAL_PASS_NOT_CORPUS_LOCK",
        "p4a_plan_sha256":p2.sha(plan_path),
        "gem5_sha256":EXPECTED_GEM5,
        "first_manifest_present":first is not None,
        "first_console_sha256":p2.sha(v["first_console"]),
        "remaining_console_sha256":p2.sha(v["remaining_console"]),
        "remaining_manifest_sha256":p2.sha(
            v["remaining_dir"]/"g5_functional_manifest.json"),
        "ignored_partial_case_dirs_after_disconnect":extras,
        "actual_profiles":["g5_native"],"six_profile_holdout_executions":0,
        "corpus_locked":False,"cases":results,
        "limitation":"If interrupted first manifest is absent, original CLI "
                     "PASS+raw proves condition gate but does not independently "
                     "rehash the host subprocess return-code integer.",
    }
    v["out"].parent.mkdir(parents=True,exist_ok=True)
    with v["out"].open("x") as f:
        json.dump(result,f,indent=2,ensure_ascii=False)
        f.write("\n")
    print("R3C_P5A_LEDGER="+str(v["out"]),flush=True)
    print("R3C_P5A_VERDICT="+result["verdict"],flush=True)
    print("NO CLAIM: independent untouched workloads, paired TG7 "
          "performance, locked corpus or SRAM/RTL PPA",flush=True)

if __name__=="__main__":
    try: main()
    except (OSError,ValueError,RuntimeError,KeyError,AssertionError) as e:
        print("R3C_P5A_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
