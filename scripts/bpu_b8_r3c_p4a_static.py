#!/usr/bin/env python3
"""BPU8 R3C P4A static executable SE interface preflight. NO SIMULATION.

Reads the original 11-case P3C audited evidence, verifies every input/binary
SHA and the additive simulator adapter contract, and emits a versioned
per-case G5-only functional feasibility PLAN. DOES NOT run any gem5 workload,
lock corpus, inspect candidate performance, or assert historical disjointness.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2
import bpu_b8_r3c_p3b_remaining9 as p3b
import bpu_b8_r3c_p3a_functional as p3a
import bpu_b8_r3c_p3c_evidence as p3c

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_CONFIG = ROOT / "configs/02_little_v052_rv64_proxy.py"
R3C_CONFIG = ROOT / "configs/02_little_v052_rv64_proxy_r3c.py"
R3_MATRIX = ROOT / "docs/bpu8_r3_g5_lock_v01.json"
CANDIDATE_JSON = ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json"

# This is a strictly non-semantic IO adapter on top of original R3 config.
ADAPTER_HEADER = """# R3C INPUT/OUTPUT CONTROL ADAPTER.
# Entire file copied from the frozen Little v0.52 RV64 proxy configuration
# and modified ONLY to expose gem5's FileResource stdin + simulated stdout/
# stderr file controls. Original configs/02_little_v052_rv64_proxy.py unchanged.
# This file is NOT evidence of physical BPU/RTL or performance.
"""
NEW_IO_ARGS = """    # R3C-specific SE output custody (additive; original R3 config left untouched).
    parser.add_argument(
        "--program-stdin-file", default=None,
        help="Absolute source path to file-backed simulated stdin",
    )
    parser.add_argument(
        "--program-stdout-file", default=None,
        help="Absolute destination path for simulated program stdout",
    )
    parser.add_argument(
        "--program-stderr-file", default=None,
        help="Absolute destination path for simulated program stderr",
    )
"""
IO_GUARD = """    if args.cores != 1 and any(
        (args.program_stdin_file, args.program_stdout_file, args.program_stderr_file)
    ):
        raise ValueError("R3C program IO overrides are single-core only")
    if args.program_stdin_file and not Path(args.program_stdin_file).is_file():
        raise FileNotFoundError("R3C stdin file missing: " + str(args.program_stdin_file))
    for pathname in (args.program_stdout_file, args.program_stderr_file):
        if pathname and not Path(pathname).resolve().parent.is_dir():
            raise FileNotFoundError("R3C output parent missing: " + str(pathname))

"""
NEW_SE_KWARGS = """            stdin_file=(
                FileResource(local_path=str(Path(args.program_stdin_file).resolve()))
                if args.program_stdin_file else None
            ),
            stdout_file=(
                Path(args.program_stdout_file).resolve()
                if args.program_stdout_file else None
            ),
            stderr_file=(
                Path(args.program_stderr_file).resolve()
                if args.program_stderr_file else None
            ),
"""
# Verify exact text-equivalence of adapted vs original except three IO additions.
def adapter_contract(original: str, adapted: str) -> bool:
    if not adapted.startswith(ADAPTER_HEADER):
        raise ValueError("R3C adapter provenance header wrong")
    rest = adapted[len(ADAPTER_HEADER):]
    parts = [
        ("from gem5.resources.resource import BinaryResource, FileResource",
         "from gem5.resources.resource import BinaryResource"),
        (NEW_IO_ARGS, ""),
        (IO_GUARD, ""),
        (NEW_SE_KWARGS, ""),
    ]
    for modified, initial in parts:
        if rest.count(modified) != 1:
            raise ValueError("R3C adapter inserted or modified non-IO code")
        rest = rest.replace(modified, initial, 1)
    if rest != original:
        raise ValueError("R3C adapter differs from original beyond explicit IO hooks")
    return True


def case_contracts(evidence: dict, original_root: Path,
                   overlay_root: Path, original_elves: Path,
                   mibench: Path, coremark: Path) -> dict:
    items = {}
    for case in p2.ORDER:
        is_overlay = case in p3a.CASES
        sourcedir = ((overlay_root / "overlay_source" / "mibench" /
                      p2.SPECS[case][0]) if is_overlay else
                     (coremark if case == "coremark_performance" else
                      mibench / p2.SPECS[case][0]))
        elf = ((overlay_root if is_overlay else original_elves) /
               (case + ".rv64.elf"))
        prior = evidence[case]
        if not elf.is_file() or p2.sha(elf) != prior["rv64_elf_sha256"]:
            raise ValueError(case + ": P3C vs ELF binary SHA mismatch")
        if is_overlay:
            input_name = "small.udp" if case == "patricia" else "input_small.asc"
            argv = ([input_name] if case == "patricia" else
                    [input_name, "encrypted.bin", "e", p3a.KEY])
            ins = [input_name]
            output_file = "encrypted.bin" if case == "rijndael_encrypt" else None
            expected_exit = 1 if case == "patricia" else 0
        elif case == "coremark_performance":
            argv = p3b.COREMARK_ARGUMENTS["performance"]
            ins = []
            output_file = None
            expected_exit = 0
        else:
            task = p3b.TASKS[case]
            argv = list(task["argv"])
            ins = list(task["inputs"])
            output_file = task.get("output")
            expected_exit = 0

        inputs = []
        for item in ins:
            p = (sourcedir / item).resolve()
            if not p.is_file() or not p.is_relative_to(sourcedir.resolve()):
                raise ValueError(case + ": unsafe or missing input " + item)
            digest = p2.sha(p)
            if is_overlay:
                if digest != prior["input_sha256"]:
                    raise ValueError(case + ": input digest changed since P3C")
            elif not any(x["path"] == item and x["sha256"] == digest
                         and x["size"] == p.stat().st_size
                         for x in prior["inputs"]):
                raise ValueError(case + ": P3C input bytes mismatch")
            inputs.append(dict(name=item, source_path=str(p),
                               sha256=digest,size=p.stat().st_size))

        stdin_name = ("data/small.pcm" if case == "adpcm_encode" else None)
        if stdin_name and stdin_name not in ins:
            raise ValueError("ADPCM standard input must be copied and pinned")
        golden_mode = {
            "bitcount": "ALGORITHM_COUNTS_NOT_HOST_TIMES",
            "fft": "FINITE_FLOAT_VECTORS_ABS_1E-4_REL_1E-5",
            "coremark_performance": "EEMBC_UPSTREAM_2K_PERFORMANCE_CRC_ONLY",
            "susan_edges": "EXACT_P5_EDGES_IMAGE",
            "adpcm_encode": "EXACT_ENCODER_BYTES_PLUS_TERMINAL_STATE",
            "patricia": "NONEMPTY_EXACT_STDOUT_AND_EXPECTED_EXIT_1",
            "rijndael_encrypt": "EXACT_CIPHERTEXT_PLUS_PRIOR_ROUNDTRIPS",
        }.get(case, "EXACT_PREQUALIFIED_QEMU_RV64_STDOUT")
        items[case] = {
            "binary":str(elf.resolve()),
            "binary_sha256":p2.sha(elf),
            "source_kind":"LP64_SIDECAR" if is_overlay else "ORIGINAL_P1_PINNED",
            "argv":argv,
            "stdin_file_relative":stdin_name,
            "input_files":inputs,
            "program_output_file_relative":output_file,
            "expected_process_exit_code":expected_exit,
            "correctness_gate":golden_mode,
            "reference":prior,
            "io_semantics":"stage inputs in per-case cwd before one G5-only gem5 SE run",
            "perf_allowed":False,
        }
    return items


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    for x in ("p1","p2_full11_dir","p2b_dir","p3a_dir","p3b_dir",
              "p3c_snapshot","mibench_dir","coremark_dir","out"):
        ap.add_argument("--"+x.replace("_","-"),type=Path,required=True)
    args=ap.parse_args()
    p1path=args.p1.expanduser().resolve()
    p2root=args.p2_full11_dir.expanduser().resolve()
    p2broot=args.p2b_dir.expanduser().resolve()
    p3aroot=args.p3a_dir.expanduser().resolve()
    p3broot=args.p3b_dir.expanduser().resolve()
    p3cpath=args.p3c_snapshot.expanduser().resolve()
    mibench=args.mibench_dir.expanduser().resolve()
    coremark=args.coremark_dir.expanduser().resolve()
    out=args.out.expanduser().resolve()
    if out.exists():
        raise ValueError("never overwrite a pre-result P4A plan")

    original=ORIGINAL_CONFIG.read_text()
    adapter=R3C_CONFIG.read_text()
    adapter_contract(original, adapter)
    # Compile both syntactically outside gem5's live importer.
    compile(original, str(ORIGINAL_CONFIG), "exec")
    compile(adapter, str(R3C_CONFIG), "exec")

    p1=json.loads(p1path.read_text())
    p2data=json.loads((p2root/"build_manifest.json").read_text())
    p2bdata=json.loads((p2broot/"portability_manifest.json").read_text())
    p3csnap=json.loads(p3cpath.read_text())
    if (p3csnap.get("kind")!="BPU8_R3C_P3C_11CASE_PRELOCK_EVIDENCE_SNAPSHOT"
            or p3csnap.get("status")!="ALL_11_CROSS_HOST_PROVISIONAL_PASS_NOT_CORPUS_LOCK"
            or p3csnap.get("corpus_frozen") is not False
            or p3csnap.get("gem5_performance_jobs_performed_here")!=0
            or p3csnap.get("case_count")!=11):
        raise ValueError("P3C prelock snapshot status not verified")
    expected_files={
        "p1_sha256":p1path,
        "p2_full11_manifest_sha256":p2root/"build_manifest.json",
        "p2b_manifest_sha256":p2broot/"portability_manifest.json",
        "p3a_manifest_sha256":p3aroot/"functional_manifest.json",
        "p3b_manifest_sha256":p3broot/"functional_manifest.json",
        "prereg_sha256":CANDIDATE_JSON,
    }
    for key, file in expected_files.items():
        if p3csnap[key]!=p2.sha(file):
            raise ValueError("P3C snapshot evidence drift: "+key)
    p3a.validate_source_gate(p1,p1path,mibench,coremark,p2bdata,
                             p2broot/"portability_manifest.json",p2broot)
    p3b.ensure_p2_gate(p1,p1path,p2data,p2root/"build_manifest.json",
                       p2root,mibench,coremark)
    if list(p3csnap["cases"])!=list(p2.ORDER):
        raise ValueError("P3C case order changed")
    prereg=json.loads(CANDIDATE_JSON.read_text())
    r3=json.loads(R3_MATRIX.read_text())
    if prereg.get("fixed_profiles")!=list(r3["profiles"]):
        raise ValueError("P4A six frozen geometry identities drifted")
    if prereg["fixed_profiles"][0]!="g5_native":
        raise ValueError("not using pre-registered control geometry")

    dev_names=set(r3["workloads"])
    exact_name_overlap=sorted(dev_names.intersection(p2.ORDER))
    if exact_name_overlap:
        raise ValueError("candidate benchmark name equals prior Embench development: "
                         +str(exact_name_overlap))
    cases=case_contracts(p3csnap["cases"],p2root,p2broot,p2root,mibench,coremark)
    report = {
        "kind":"BPU8_R3C_P4A_STATIC_SE_INTERFACE_NOT_CORPUS_LOCK",
        "status":"STATIC_PLAN_READY_GEM5_EXECUTION_NOT_YET_CHECKED",
        "original_config_sha256":p2.sha(ORIGINAL_CONFIG),
        "r3c_se_config_sha256":p2.sha(R3C_CONFIG),
        "r3c_se_adapter_semantic_diff":"ONLY_STDIN_STDOUT_STDERR_SINGLE_CORE_ARGS",
        "original_r3_geometry_matrix_sha256":p2.sha(R3_MATRIX),
        "p3c_snapshot_sha256":p2.sha(p3cpath),
        "prereg_sha256":p2.sha(CANDIDATE_JSON),
        "control_geometry":"g5_native",
        "future_six_comparators":prereg["fixed_profiles"],
        "dev_full19_names":r3["workloads"],
        "same_string_candidate_vs_full19_overlap":exact_name_overlap,
        "overlap_evidence_limit":"Exact benchmark-name overlap ONLY; cannot prove no previous external input SHA use in other historical experiments",
        "cases":cases,
        "planned_one_profile_feasibility_cases":len(cases),
        "actual_gem5_executions":0,
        "actual_r3c_paired_performance_runs":0,
        "corpus_lock":False,
        "unresolved":[
            "confirm no prior external MiBench/CoreMark source+input bytes used for predictor selection across entire historical BPU corpus",
            "separate reference-G5 gem5 SE executed workload+IO control validation; no six-way comparisons",
            "validate simulated exit status 1 for Patricia and zero for all other cases",
            "verify first ROI and no hidden early exit while retaining output correctness",
            "separate immutable corpus_lock committed before six-profile comparisons",
            "independent AES known-answer and Patricia IPv4 algorithm correctness still not proven",
            "all CoreMark runs remain internal no certified official score",
        ],
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("R3C_P4A_STATIC_PLAN="+str(out))
    print("R3C_P4A_CASES="+str(len(cases)))
    print("R3C_P4A_R3_EMBENCH_EXACT_NAME_OVERLAP="+str(len(exact_name_overlap)))
    print("R3C_P4A_SE_IO_ADAPTER=BYTEWISE_NON_IO_CODE_EQUIVALENT")
    print("R3C_P4A_VERDICT=PREPARED_NOT_EXECUTED_NOT_CORPUS_LOCK")
    print("NO CLAIM: historical complete nonoverlap, first ROI, gem5 functional pass, paired holdout or PPA")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as e:
        print("R3C_P4A_FAIL_CLOSED: "+str(e),file=sys.stderr)
        sys.exit(1)
