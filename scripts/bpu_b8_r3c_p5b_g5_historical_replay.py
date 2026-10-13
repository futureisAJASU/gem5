#!/usr/bin/env python3
"""R3C P5B: replay historical G5 native Full19 with revised gem5.opt.

Only one existing frozen control predictor (G5 native) is simulated. For each
Embench workload, compare the NEW linked simulator's deterministic counters
with ORIGINAL R3 Full19 RAW rather than overwriting historical evidence.
NO G5/TG7 comparison, NO external holdout, NO corpus lock.
"""
from __future__ import annotations
import argparse,json,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
import bpu_b8_r3_g5_lock_full19 as r3
import bpu_b8_r3c_p2_build as p2
from bpu_b8_r3c_p4b_g5_se_feasibility import extract_sim_exit

CURRENT_SHA="12681de7975d5082b64dee6e085585dbbd1d078fa7be7f477f4553ab98344a1a"
HISTORICAL_SHA="f8e3b38e373fd13d9658c4832826703ef2a3d2443601b6b6c3153131b983ba85"
CONTROL="g5_native"
FIELDS=(
    "simTicks","simInsts","committedConditionalPredictions",
    "committedConditionalWrong","finalConditionalWrong",
    "predictionMetadataChecks","historyRestoreChecks","historyStateRestores",
    "storageBits","taggedStorageBits","bimodalStorageBits",
    "historyStorageBits","otherStorageBits",
    "r3PseudoNewAlloc","r3AlternateDisagreements","r3AlternateWouldFix",
    "r3AllocAttempts","r3Allocations","r3ForcedUsefulClears","r3CauseJson",
)

def check(ok,msg):
    if not ok:raise ValueError(msg)

def original_row(golden,case):
    folder=golden/CONTROL/case
    recorded=json.loads((folder/".verified.json").read_text())
    row=recorded["row"]
    check(recorded["gem5_sha256"]==HISTORICAL_SHA,
          case+": historical reference executable identity wrong")
    raw=folder/"roi.stats"
    check(raw.is_file() and p2.sha(raw)==row["roi_sha256"],
          case+": historical ROI SHA drift")
    check((folder/"stats.txt").is_file(),case+": historical stats missing")
    stats,first=r3.parse_first_roi(folder/"stats.txt")
    check(raw.read_text()==first,case+": historical stored first ROI drift")
    return row

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historical-raw-dir",type=Path,required=True)
    ap.add_argument("--embench-build",type=Path,required=True)
    ap.add_argument("--gem5",type=Path,default=p2.ROOT/"build/RISCV/gem5.opt")
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--timeout",type=int,default=1800)
    x=ap.parse_args()
    check(60<=x.timeout<=7200,"invalid timeout 60..7200")
    hist=x.historical_raw_dir.expanduser().resolve()
    build=x.embench_build.expanduser().resolve()
    gem5=x.gem5.expanduser().resolve()
    dest=x.out.expanduser().resolve()
    check(not dest.exists(),"never overwrite original or replay")
    check(not r3.git("status","--porcelain","--untracked-files=no"),
          "tracked source dirty")
    check(gem5.is_file() and p2.sha(gem5)==CURRENT_SHA,
          "current simulator exact SHA not pinned")
    registry=r3.load_matrix()
    profile=registry["profiles"][CONTROL]
    check(list(registry["profiles"])[0]==CONTROL,
          "control ordering changed")
    history=json.loads((hist/"manifest.json").read_text())
    check(history["experiment"]=="BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01"
          and history["gem5_sha256"]==HISTORICAL_SHA
          and history["scope"]=="FULL19_DEVELOPMENT_CORPUS"
          and history["benchmarks"] is not None
          and history["workloads"]==registry["workloads"],"R3 old manifest wrong")
    check(p2.sha(r3.CONFIG_FILE)==history["config_sha256"],
          "historical config source drift")
    check(p2.sha(r3.MATRIX_FILE)==history["matrix_sha256"],
          "R3 exact-geometry matrix drift")
    original={w:original_row(hist,w) for w in registry["workloads"]}
    for workload in registry["workloads"]:
        elf=build/"src"/workload/workload
        check(elf.is_file() and p2.sha(elf)==history["benchmarks"][workload],
              workload+": historic RV64 executable no longer matches")
    dest.mkdir(parents=True)
    report={
        "kind":"BPU8_R3C_P5B_NEW_GEM5_G5_ONLY_HISTORICAL_REPLAY",
        "new_gem5_sha256":CURRENT_SHA,
        "old_r3_gem5_sha256":HISTORICAL_SHA,
        "old_manifest_sha256":p2.sha(hist/"manifest.json"),
        "profile":CONTROL,"compared_profiles":[],
        "holdout_jobs":0,"corpus_locked":False,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "cases":{},"verdict":"NOT_COMPLETE",
    }
    try:
        for workload in registry["workloads"]:
            old=original[workload];target=dest/workload
            target.mkdir()
            elf=build/"src"/workload/workload
            cmd=[str(gem5),"--outdir="+str(target),str(r3.CONFIG_FILE),
                 "--binary",str(elf),"--bp-type",profile["bp_type"],
                 "--bp-inst-shift","1","--bp-cond-shift","1",
                 "--bp-btb-shift","2","--bp-indirect-shift","1",
                 "--btb-entries","4096"]
            (target/"command.json").write_text(json.dumps(cmd,indent=2)+"\n")
            rec={"status":"STARTED","pass":False}
            report["cases"][workload]=rec
            try:
                with (target/"stdout.txt").open("xb") as so, (
                        target/"stderr.txt").open("xb") as se:
                    try:
                        rc=subprocess.run(cmd,cwd=p2.ROOT,stdout=so,stderr=se,
                                          timeout=x.timeout).returncode
                    except subprocess.TimeoutExpired:
                        rc=None
                rec["runner_rc"]=rc
                check(rc==0,workload+": host gem5 failed or timed out")
                check(extract_sim_exit((target/"stdout.txt").read_text(errors="replace"))==0,
                      workload+": guest exit not zero")
                r3.validate_r3_ini(target/"config.ini",CONTROL,registry["profiles"])
                stat,first=r3.parse_first_roi(target/"stats.txt")
                (target/"roi.stats").write_text(first)
                now=r3.inspect_row(stat,CONTROL,workload,profile,p2.sha(target/"roi.stats"))
                differences={key:{"original":old[key],"replay":now[key]}
                             for key in FIELDS if old[key]!=now[key]}
                rec["original_roi_sha256"]=old["roi_sha256"]
                rec["replay_roi_sha256"]=p2.sha(target/"roi.stats")
                rec["raw_sha256"]={name:p2.sha(target/name)
                                   for name in ("stats.txt","config.ini",
                                                "roi.stats","stdout.txt","stderr.txt")}
                rec["counter_differences"]=differences
                rec["pass"]=not bool(differences)
                rec["status"]="G5_ONLY_EXACT_REPLAY_PASS" if rec["pass"] else "DETERMINISTIC_COUNTER_DRIFT"
                if not rec["pass"]:
                    raise ValueError(workload+": "+str(len(differences))+" deterministic counters changed")
            except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as e:
                rec["error"]=str(e)
                rec["pass"]=False
            print("R3C_P5B_G5_HISTORICAL "+workload+": "+
                  ("PASS" if rec["pass"] else "FAIL"),flush=True)
            if not rec["pass"]:break
    finally:
        all_pass=(len(report["cases"])==19
                  and all(r["pass"] for r in report["cases"].values()))
        report["verdict"]=("19_OF_19_G5_REPLAY_EXACT_PASS"
                          if all_pass else "REPLAY_INCOMPLETE_OR_COUNTER_DRIFT")
        mf=dest/"g5_replay_manifest.json"
        mf.write_text(json.dumps(report,indent=2)+"\n")
        print("R3C_P5B_MANIFEST="+str(mf),flush=True)
        print("R3C_P5B_VERDICT="+report["verdict"],flush=True)
        print("NO CLAIM: TG7 holdout, physical SRAM/RTL PPA or final BPU geometry",flush=True)
    return 0 if all_pass else 2

if __name__=="__main__":
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError,KeyError) as error:
        print("R3C_P5B_FAIL_CLOSED: "+str(error),file=sys.stderr);sys.exit(1)
