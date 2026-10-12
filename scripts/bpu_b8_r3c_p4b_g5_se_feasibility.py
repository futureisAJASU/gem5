#!/usr/bin/env python3
"""R3C P4B: G5 ONLY gem5 SE functional + first-ROI feasibility, no geometry pairing.

Consumes P4A's immutable prelock plan. Verifies exact gem5 binary/config,
stages input bytes, runs only g5_native, checks program output against the
prior QEMU RV64 reference, checks reported SE program exit, validates first
ROI and R3 diagnostics, preserves every raw artifact. Never prints metrics,
never runs TG6/TG7/hash11, never locks holdout corpus.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import bpu_b8_r3_g5_lock_full19 as r3
import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p3b_remaining9 as p3b
import bpu_b8_r3c_p4a_static as p4a

ORDER=tuple(p2.ORDER)
EXPECTED_CONTROL="g5_native"


def check(ok: bool, description: str):
    if not ok:
        raise ValueError(description)


def reference_paths(case: str, p3a: Path, p3b: Path, ref: dict):
    """Require identical SHA of saved QEMU evidence that was audited at P3C."""
    if case in ("patricia", "rijndael_encrypt"):
        mode="patricia.rv64" if case=="patricia" else "aes.rv64.enc"
        root=p3a
    else:
        mode=case + (".performance.rv64" if case=="coremark_performance" else ".small.rv64")
        root=p3b
    observations=[r for r in ref["observations"] if r["id"]==mode]
    check(len(observations)==1, case+": QEMU reference identity wrong")
    prior=observations[0]
    files={}
    for stream in ("stdout","stderr"):
        file=root/(mode+"."+stream)
        check(file.is_file() and p2.sha(file)==prior[stream+"_sha256"]
              and file.stat().st_size==prior[stream+"_size"],
              case+": saved P3C reference changed: "+stream)
        files[stream]=file
    return files


def expected_output_file(case: str, p3a: Path, p3b: Path, ref: dict) -> Path|None:
    if case=="susan_edges":
        f=p3b/"susan_edges.rv64.work"/"edges.pgm"
        records=[x for x in ref["reference_checks"] if x["mode"]=="small"]
        check(len(records)==1 and
              records[0]["image_rv64"]["sha256"]==p2.sha(f),
              "SUSAN reference image SHA drift")
        return f
    if case=="rijndael_encrypt":
        matches=[x for x in ref["files"] if x["relative_path"]==
                 "rijndael_encrypt.work.rv64/encrypted.bin"]
        check(len(matches)==1, "AES reference output not in P3C snapshot")
        f=p3a/matches[0]["relative_path"]
        check(f.is_file() and p2.sha(f)==matches[0]["sha256"],
              "AES reference ciphertext SHA drift")
        return f
    return None


def compare_program(case: str, actual_stdout: bytes, actual_stderr: bytes,
                    qstdout: bytes, qstderr: bytes,
                    expected_file: Path|None, written_file: Path|None) -> dict:
    result={"case":case, "passed":False,
            "stdout_sha256":hashlib.sha256(actual_stdout).hexdigest(),
            "stderr_sha256":hashlib.sha256(actual_stderr).hexdigest(),
            "rv64_qemu_stdout_sha256":hashlib.sha256(qstdout).hexdigest(),
            "rv64_qemu_stderr_sha256":hashlib.sha256(qstderr).hexdigest()}
    if case=="coremark_performance":
        eval_=p3b.coremark_evaluate(actual_stdout,qstdout,"performance")
        result.update(eval_)
        result["passed"]=bool(eval_["passed"])
        result["stderr_equal_to_qemu"]=actual_stderr==qstderr
        result["passed"] &= result["stderr_equal_to_qemu"]
    elif case=="bitcount":
        native=p3b.bitcount_signature(actual_stdout)
        qemu=p3b.bitcount_signature(qstdout)
        result["method_count"]=len(native)
        result["passed"]=native==qemu and actual_stderr==qstderr
    elif case=="fft":
        eval_=p3b.fft_signature(actual_stdout,qstdout)
        result.update(eval_)
        result["passed"] &= actual_stderr==qstderr
    else:
        # The upstream Patricia C source intentionally exits with status 1.
        # The wrapper validates that separately, not as a stdout mismatch.
        result["passed"]=actual_stdout==qstdout and actual_stderr==qstderr
        result["stdout_equal_to_qemu"]=actual_stdout==qstdout
        result["stderr_equal_to_qemu"]=actual_stderr==qstderr
        if case=="adpcm_encode":
            result["passed"] &= len(actual_stdout)>0
        if case=="patricia":
            result["passed"] &= len(actual_stdout)>0
    if expected_file is not None:
        require_files=(written_file is not None and written_file.is_file()
                       and expected_file.is_file())
        result["program_output_present"]=bool(require_files)
        if require_files:
            result["program_output_sha256"]=p2.sha(written_file)
            result["reference_output_sha256"]=p2.sha(expected_file)
            result["program_output_equal_to_qemu"]=(p2.sha(written_file)==p2.sha(expected_file))
            result["passed"] &= result["program_output_equal_to_qemu"]
        else:
            result["passed"]=False
    return result


def extract_sim_exit(sim_stdout: str) -> int:
    matches=re.findall(r"(?m)^SIMULATION_EXIT_CODE=(-?\d+)\s*$",sim_stdout)
    check(len(matches)==1,"missing/duplicate SIMULATION_EXIT_CODE")
    check("SIMULATION_EXIT_CAUSE=" in sim_stdout,
          "missing gem5 SE exit cause")
    return int(matches[0])


def build_command(gem5: Path, adapter: Path, case_row: dict, sim_dir: Path,
                  work: Path, profile: dict) -> list[str]:
    binary=Path(case_row["binary"])
    args=[str(gem5), "--outdir="+str(sim_dir), str(adapter),
          "--binary",str(binary),
          "--bp-type",profile["bp_type"],
          "--bp-inst-shift","1","--bp-cond-shift","1",
          "--bp-btb-shift","2","--bp-indirect-shift","1",
          "--btb-entries","4096",
          "--program-stdout-file="+str(work/"program.stdout"),
          "--program-stderr-file="+str(work/"program.stderr")]
    for a in case_row["argv"]:
        args.append("--program-arg="+str(a))
    if case_row["stdin_file_relative"]:
        args.append("--program-stdin-file="+str((work/case_row["stdin_file_relative"]).resolve()))
    return args


def verify_plan(plan: dict, gem5: Path, p4a_path: Path,
                p3a: Path, p3b: Path):
    check(plan["kind"]=="BPU8_R3C_P4A_STATIC_SE_INTERFACE_NOT_CORPUS_LOCK"
          and plan["status"]=="STATIC_PLAN_READY_GEM5_EXECUTION_NOT_YET_CHECKED",
          "P4A static plan not valid")
    check(plan["control_geometry"]==EXPECTED_CONTROL and
          plan["actual_gem5_executions"]==0 and
          plan["actual_r3c_paired_performance_runs"]==0 and
          plan["corpus_lock"] is False, "P4A violated zero-run constraint")
    check(list(plan["cases"])==list(ORDER), "P4A suite case order drift")
    original=p4a.ORIGINAL_CONFIG.read_text()
    adapter=p4a.R3C_CONFIG.read_text()
    p4a.adapter_contract(original,adapter)
    check(p2.sha(p4a.ORIGINAL_CONFIG)==plan["original_config_sha256"]
          and p2.sha(p4a.R3C_CONFIG)==plan["r3c_se_config_sha256"],
          "source config SHA mismatch")
    matrix=r3.load_matrix()
    check(p2.sha(r3.MATRIX_FILE)==plan["original_r3_geometry_matrix_sha256"],
          "frozen R3 geometry changed")
    check(list(matrix["profiles"])==plan["future_six_comparators"],
          "six profiles changed")
    check(gem5.is_file(),"gem5 binary missing")
    check((p3a/"functional_manifest.json").is_file() and
          (p3b/"functional_manifest.json").is_file(),
          "P3 references missing")
    for case, row in plan["cases"].items():
        elf=Path(row["binary"]).resolve()
        check(elf.is_file() and p2.sha(elf)==row["binary_sha256"],
              case+": RV64 binary custody mismatch")
        check(row["perf_allowed"] is False,case+": performance permitted")
        for record in row["input_files"]:
            src=Path(record["source_path"]).resolve()
            check(src.is_file() and p2.sha(src)==record["sha256"] and
                  src.stat().st_size==record["size"],
                  case+": input source digest mismatch")
        # Fail on any unexpected case or mode, rather than cherry-pick later.
        check(case in ORDER,case+": case not in original prereg")
    return matrix["profiles"][EXPECTED_CONTROL]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p4a-plan",type=Path,required=True)
    parser.add_argument("--p3a-dir",type=Path,required=True)
    parser.add_argument("--p3b-dir",type=Path,required=True)
    parser.add_argument("--gem5",type=Path,default=p2.ROOT/"build/RISCV/gem5.opt")
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--only",nargs="+",choices=ORDER,default=None,
                        help="feasibility subset, not a corpus eligibility change")
    parser.add_argument("--timeout",type=int,default=1800)
    args=parser.parse_args()
    check(1<=args.timeout<=7200,"timeout outside 1..7200s")
    plan_path=args.p4a_plan.expanduser().resolve()
    p3a=args.p3a_dir.expanduser().resolve()
    p3b=args.p3b_dir.expanduser().resolve()
    gem5=args.gem5.expanduser().resolve()
    out=args.out.expanduser().resolve()
    check(not out.exists(),"P4B output exists; never overwrite old RAW")
    plan=json.loads(plan_path.read_text())
    profile=verify_plan(plan,gem5,plan_path,p3a,p3b)
    check(not r3.git("status","--porcelain","--untracked-files=no"),
          "dirty tracked gem5 source; refusing P4B")
    order=[case for case in ORDER if args.only is None or case in args.only]
    out.mkdir(parents=True)
    manifest={
        "kind":"BPU8_R3C_P4B_G5_ONLY_SE_FIRST_ROI_FEASIBILITY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "repo_head":p2.git_head(p2.ROOT),
        "gem5_sha256":p2.sha(gem5),
        "r3c_adapter_sha256":p2.sha(p4a.R3C_CONFIG),
        "p4a_plan_sha256":p2.sha(plan_path),
        "p3a_manifest_sha256":p2.sha(p3a/"functional_manifest.json"),
        "p3b_manifest_sha256":p2.sha(p3b/"functional_manifest.json"),
        "control_profile":EXPECTED_CONTROL,
        "control_bp_type":profile["bp_type"],
        "attempted_cases":order,
        "cases":{},
        "compared_profiles":[],
        "simulated_performance_claims":0,
        "corpus_locked":False,
        "verdict":"NOT_FINISHED",
    }
    try:
        for case in order:
            row=plan["cases"][case]
            case_dir=out/case
            case_dir.mkdir()
            work=case_dir/"work"
            sim=case_dir/"sim"
            work.mkdir();sim.mkdir()
            state={"case":case,"pass":False,"status":"STARTED",
                   "binary_sha256":row["binary_sha256"]}
            manifest["cases"][case]=state
            try:
                for infile in row["input_files"]:
                    dst=work/infile["name"]
                    check(not Path(infile["name"]).is_absolute()
                          and ".." not in Path(infile["name"]).parts,
                          case+": invalid relative input")
                    dst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(infile["source_path"],dst)
                    check(p2.sha(dst)==infile["sha256"],case+": copied input drift")
                reference=reference_paths(case,p3a,p3b,row["reference"])
                target=expected_output_file(case,p3a,p3b,row["reference"])
                output_name=row["program_output_file_relative"]
                output_path=work/output_name if output_name else None
                cmd=build_command(gem5,p4a.R3C_CONFIG,row,sim,work,profile)
                (case_dir/"command.json").write_text(
                    json.dumps({"argv":cmd,"cwd":str(work),"expected_exit":
                                row["expected_process_exit_code"]},indent=2)+"\n")
                with (case_dir/"gem5.stdout").open("xb") as so, (
                        case_dir/"gem5.stderr").open("xb") as se:
                    try:
                        run=subprocess.run(cmd,cwd=work,stdout=so,stderr=se,
                                           timeout=args.timeout)
                        runner_rc=run.returncode
                        timeout_hit=False
                    except subprocess.TimeoutExpired:
                        runner_rc=None
                        timeout_hit=True
                state["gem5_runner_rc"]=runner_rc
                state["timeout"]=timeout_hit
                if timeout_hit:
                    raise ValueError(case+": G5 SE feasibility timed out")
                state["gem5_stdout_sha256"]=p2.sha(case_dir/"gem5.stdout")
                state["gem5_stderr_sha256"]=p2.sha(case_dir/"gem5.stderr")
                sim_stdout=(case_dir/"gem5.stdout").read_text(errors="replace")
                if runner_rc!=0:
                    raise ValueError(case+": gem5 host process nonzero exit "+
                                     str(runner_rc))
                exit_status=extract_sim_exit(sim_stdout)
                state["simulated_exit_code"]=exit_status
                check(exit_status==row["expected_process_exit_code"],
                      case+": simulated process exit status differs from prereg")
                for stream in ("stdout","stderr"):
                    check((work/("program."+stream)).is_file(),
                          case+": simulated "+stream+" not written")
                check((sim/"stats.txt").is_file() and (sim/"config.ini").is_file(),
                      case+": gem5 raw stats or config.ini missing")
                r3.validate_r3_ini(sim/"config.ini",EXPECTED_CONTROL,
                                   r3.load_matrix()["profiles"])
                stats,roi=r3.parse_first_roi(sim/"stats.txt")
                roi_file=sim/"roi.stats"
                roi_file.write_text(roi)
                inspected=r3.inspect_row(stats,EXPECTED_CONTROL,case,
                                         profile,p2.sha(roi_file))
                # Keep audited totals private to the raw records, NOT print or
                # compare performance against any candidate geometry.
                state["g5_r3_conservation"]=True
                state["raw"]={x:p2.sha(sim/x) for x in
                             ("stats.txt","config.ini","roi.stats")}
                state["roi_inspect_sha256"]=hashlib.sha256(
                    json.dumps(inspected,sort_keys=True).encode()).hexdigest()
                evaluated=compare_program(
                    case,(work/"program.stdout").read_bytes(),
                    (work/"program.stderr").read_bytes(),
                    reference["stdout"].read_bytes(),
                    reference["stderr"].read_bytes(),
                    target,output_path,
                )
                state["functional"]=evaluated
                check(evaluated["passed"],case+": gem5 result differs from QEMU RV64")
                state["pass"]=True
                state["status"]="G5_SE_FUNCTIONAL_ROI_PASS_NO_COMPARISON"
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                state["status"]="FAILED_PRESERVE_RAW"
                state["error"]=str(error)
            print("R3C_P4B_G5_ONLY "+case+": "+
                  ("PASS" if state["pass"] else "FAIL"),flush=True)
            if not state["pass"]:
                # Stop at first failure to prevent wasting simulator cycles or
                # accidental selection on partial feasibility outcomes.
                break
    finally:
        passed=(len(manifest["cases"])==len(order)
                and all(x["pass"] for x in manifest["cases"].values()))
        manifest["verdict"]=("G5_ONLY_FEASIBILITY_PASS_NO_CORPUS_LOCK"
                             if passed else "INCOMPLETE_OR_G5_FEASIBILITY_FAIL")
        filename=out/"g5_functional_manifest.json"
        filename.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
        print("R3C_P4B_MANIFEST="+str(filename),flush=True)
        print("R3C_P4B_VERDICT="+manifest["verdict"],flush=True)
        print("NO CLAIM: 6-profile holdout, unseen-set independence, immutable corpus lock, RTL/PPA",
              flush=True)
    return 0 if passed else 2


if __name__=="__main__":
    try:
        sys.exit(main())
    except (KeyError,OSError,RuntimeError,ValueError,subprocess.SubprocessError) as e:
        print("R3C_P4B_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
