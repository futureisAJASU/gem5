#!/usr/bin/env python3
"""BPU-8 R3C P3B: nine ORIGINAL-source cases, QEMU RV64 vs ARM64 functionality.

This is a pre-result reference-output qualification tool, NOT gem5 performance.
Builds native controls from P1-pinned original sources.  The nine RV64 ELFs
must match the P2 original full11 manifest. Never changes external source trees.
No geometry choice is made here. Failures stay in the corpus eligibility ledger.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2

CASES = (
    "basicmath", "bitcount", "qsort", "susan_edges", "dijkstra",
    "fft", "adpcm_encode", "stringsearch", "coremark_performance",
)
# Reference parameters are fixed BEFORE observing any P3B output.
# FFT: max(1e-4 absolute, 1e-5 relative) for each finite printed float.
FFT_ATOL = 1.0e-4
FFT_RTOL = 1.0e-5
# CoreMark 2K known-answer CRCs from EEMBC core_main.c:
# known_id=3 (performance seeds), known_id=4 (validation seeds).
COREMARK_EXPECTED = {
    "performance": dict(seedcrc="e9f5", crclist="e714",
                        crcmatrix="1fd7", crcstate="8e3a"),
    "validation": dict(seedcrc="18f2", crclist="e3c1",
                       crcmatrix="0747", crcstate="8d84"),
}
COREMARK_ARGUMENTS = {
    "performance": ["0x0", "0x0", "0x66", "10", "7", "1", "2000"],
    "validation": ["0x3415", "0x3415", "0x66", "10", "7", "1", "2000"],
}
FLOAT_RE = re.compile(rb"(?<![a-zA-Z0-9_])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")

# Execute exactly one preselected case/parameter combination per source case,
# except CoreMark, where BOTH EEMBC seeds are required as a correctness gate.
TASKS = {
    "basicmath": dict(argv=[], inputs=[], output=None),
    "bitcount": dict(argv=["75000"], inputs=[], output=None),
    "qsort": dict(argv=["input_small.dat"], inputs=["input_small.dat"], output=None),
    "susan_edges": dict(argv=["input_small.pgm", "edges.pgm", "-e"],
                        inputs=["input_small.pgm"], output="edges.pgm"),
    "dijkstra": dict(argv=["input.dat"], inputs=["input.dat"], output=None),
    "fft": dict(argv=["4", "4096"], inputs=[], output=None),
    "adpcm_encode": dict(argv=[], inputs=["data/small.pcm"],
                         stdin="data/small.pcm", output=None),
    "stringsearch": dict(argv=[], inputs=[], output=None),
}


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ensure_p2_gate(p1: dict, p1_path: Path, p2data: dict,
                   p2_path: Path, p2dir: Path,
                   mibench: Path, coremark: Path) -> dict:
    p2.verify_p1(p1, mibench, coremark)
    if p2data.get("kind") != "BPU8_R3C_P2_BUILD_ONLY_NOT_FUNCTIONAL_OR_HOLDOUT":
        raise ValueError("P2 full11 kind invalid")
    if p2data.get("p1_snapshot_sha256") != p2.sha(p1_path):
        raise ValueError("P2 full11 source custody does not match P1")
    if p2data.get("source_commits") != {
        "mibench": p1["mibench"]["git_head"],
        "coremark": p1["coremark"]["git_head"],
    }:
        raise ValueError("P2 external source revisions differ from P1")
    if p2data.get("prereg_sha256") != p1["prereg_sha256"]:
        raise ValueError("P2 prereg drift")
    if p2data.get("gem5_runs") != 0:
        raise ValueError("unexpected gem5 run accounting in P2")
    entries = p2data["results"]
    byname = {r["case"]: r for r in entries}
    if len(byname) != len(entries) or set(byname) != set(p2.ORDER):
        raise ValueError("P2 full11 must include all original 11 candidate attempts")
    for name in CASES:
        rec = byname[name]
        elf = p2dir / (name + ".rv64.elf")
        if not (rec.get("compile_returncode") == 0
                and rec.get("static_rv64_lp64d") is True
                and rec.get("sha256")
                and elf.is_file() and p2.sha(elf) == rec["sha256"]):
            raise ValueError("P2 original-source ELF gate failed: " + name)
    return byname


def execute(argv: list[str], cwd: Path, out: Path, title: str,
            stdin: Path | None, timeout: int) -> dict:
    stdin_file = stdin.open("rb") if stdin is not None else None
    try:
        run = subprocess.run(
            argv, cwd=cwd, stdin=stdin_file, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout,
        )
    finally:
        if stdin_file:
            stdin_file.close()
    so, se = out / (title + ".stdout"), out / (title + ".stderr")
    so.write_bytes(run.stdout)
    se.write_bytes(run.stderr)
    return dict(id=title, argv=argv, cwd=str(cwd), returncode=run.returncode,
                stdout_sha256=p2.sha(so), stderr_sha256=p2.sha(se),
                stdout_size=so.stat().st_size, stderr_size=se.stat().st_size)


def bitcount_signature(raw: bytes) -> tuple[tuple[bytes, bytes], ...]:
    # DO NOT use runtime or host-dependent fastest/slowest rankings.
    # Read all published per-method result counts; at least 3 distinct methods.
    matches = re.findall(
        rb"(?m)^\s*([^>\n]+)>\s*Time:\s*[\d.]+\s*sec\.;\s*Bits:\s*(\d+)\s*$",
        raw,
    )
    signature = tuple((name.strip(), count) for name, count in matches)
    if len(signature) < 3:
        raise ValueError("bitcount expected >=3 method-specific bit counts")
    if len(set(x[0] for x in signature)) != len(signature):
        raise ValueError("bitcount method names duplicated")
    return signature


def fft_signature(a: bytes, b: bytes) -> dict:
    for blob in (a, b):
        if not blob.startswith(b"RealOut:\n") or b"ImagOut:\n" not in blob:
            raise ValueError("FFT output did not include RealOut and ImagOut")
    af = [float(x) for x in FLOAT_RE.findall(a)]
    bf = [float(x) for x in FLOAT_RE.findall(b)]
    if len(af) != len(bf) or len(af) < 256:
        raise ValueError("FFT output vector count mismatch or unexpectedly short")
    if any(not math.isfinite(x) for x in af + bf):
        raise ValueError("FFT produced NaN or infinity")
    max_error = max(abs(x-y) for x, y in zip(af, bf))
    passed = all(math.isclose(x,y,rel_tol=FFT_RTOL,abs_tol=FFT_ATOL)
                 for x,y in zip(af,bf))
    return {"passed":passed, "float_count":len(af),
            "max_abs_difference":max_error,
            "absolute_tolerance":FFT_ATOL, "relative_tolerance":FFT_RTOL,
            "comparison":"all printed floating-point coefficients; finite numbers only"}


def coremark_crc(raw: bytes) -> dict:
    values = {}
    for name, hexval in re.findall(
            rb"(seedcrc|crclist|crcmatrix|crcstate)\s*:\s*0x([0-9a-fA-F]{4})",raw):
        key=name.decode()
        if key in values:
            raise ValueError("duplicate CoreMark field: "+key)
        values[key]=hexval.decode().lower()
    if set(values)!=set(COREMARK_EXPECTED["performance"]):
        raise ValueError("CoreMark expected 4 CRC keys")
    return values


def coremark_evaluate(host_raw: bytes, rv_raw: bytes, mode: str) -> dict:
    expected=COREMARK_EXPECTED[mode]
    host=coremark_crc(host_raw)
    rv=coremark_crc(rv_raw)
    forbidden=(b"ERROR! list crc",b"ERROR! matrix crc",b"ERROR! state crc",
               b"Cannot validate operation for these seed values")
    valid=all(marker not in raw for raw in (host_raw,rv_raw) for marker in forbidden)
    return {
        "passed":valid and host==rv==expected,
        "expected_crc":expected,
        "native_crc":host,
        "rv64_crc":rv,
        "no_crc_errors_or_unknown_seed":valid,
        "official_score_validated":False,
        "note":"SHORT RUN: reject EEMBC official scoring, only exact published CRC values are functional oracle; <=10 second warning expected",
    }


def copy_inputs(task: dict, source: Path, workdir: Path) -> list[dict]:
    output=[]
    for rel in task.get("inputs",[]):
        source_file=source/rel
        if not source_file.is_file():
            raise ValueError("missing P1-pinned source input: "+str(source_file))
        target=workdir/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source_file,target)
        if p2.sha(target)!=p2.sha(source_file):
            raise ValueError("input copy SHA mismatch: "+rel)
        output.append({"path":rel,"sha256":p2.sha(source_file),
                       "size":source_file.stat().st_size})
    return output


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p1",type=Path,required=True)
    ap.add_argument("--p2-full11-dir",type=Path,required=True)
    ap.add_argument("--mibench-dir",type=Path,required=True)
    ap.add_argument("--coremark-dir",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--timeout",type=int,default=300)
    args=ap.parse_args()
    if not 1<=args.timeout<=3600:
        raise ValueError("timeout out of allowed range 1..3600")
    p1path=args.p1.expanduser().resolve()
    p2dir=args.p2_full11_dir.expanduser().resolve()
    mibench=args.mibench_dir.expanduser().resolve()
    coremark=args.coremark_dir.expanduser().resolve()
    p1=json.loads(p1path.read_text())
    p2path=p2dir/"build_manifest.json"
    p2data=json.loads(p2path.read_text())
    ensure_p2_gate(p1,p1path,p2data,p2path,p2dir,mibench,coremark)

    hostgcc=shutil.which("gcc")
    qemu=shutil.which("qemu-riscv64")
    if not hostgcc or not qemu:
        raise ValueError("native GCC and/or qemu-riscv64 missing")
    qemu_info=subprocess.run([qemu,"--version"],capture_output=True,
                             text=True,check=True,timeout=10).stdout.splitlines()[0]
    out=args.out.expanduser().resolve()
    if out.exists():
        raise ValueError("never overwrite previous experimental output")
    out.mkdir(parents=True)
    report={
        "kind":"BPU8_R3C_P3B_9CASE_CROSS_ARCH_REFERENCE_NOT_HOLDOUT",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "p1_sha256":p2.sha(p1path),
        "p2_full11_manifest_sha256":p2.sha(p2path),
        "source_commits":p2data["source_commits"],
        "native_compiler":hostgcc,
        "native_compiler_sha256":p2.sha(Path(hostgcc).resolve()),
        "qemu":qemu,"qemu_version":qemu_info,
        "qemu_binary_sha256":p2.sha(Path(qemu).resolve()),
        "case_order":list(CASES),
        "gem5_jobs":0,"geometry_experiments":0,
        "corpus_locked":False,
        "verdict":"NOT_COMPLETE",
        "results":{},
    }
    try:
        for case in CASES:
            rec={"passed":False,"status":"STARTED"}
            report["results"][case]=rec
            try:
                target_elf=p2dir/(case+".rv64.elf")
                native_elf=out/(case+".aarch64.elf")
                cc,cwd=p2.build_cmd(case,mibench,coremark,hostgcc,native_elf)
                cc=[arg for arg in cc if arg not in ("-march=rv64gc","-mabi=lp64d")]
                compiled=subprocess.run(cc,cwd=cwd,capture_output=True,
                                        text=True,timeout=180)
                (out/(case+".native.build.stdout")).write_text(compiled.stdout)
                (out/(case+".native.build.stderr")).write_text(compiled.stderr)
                rec["native_build"]={"argv":cc,"rc":compiled.returncode,
                                     "elf_sha256":p2.sha(native_elf) if native_elf.is_file() else None}
                if compiled.returncode != 0 or not native_elf.is_file():
                    raise ValueError("native control compile failed, see native.build.stderr")

                native_dir=out/(case+".native.work")
                rv_dir=out/(case+".rv64.work")
                native_dir.mkdir();rv_dir.mkdir()
                source=(coremark if case=="coremark_performance" else mibench/p2.SPECS[case][0])
                if case=="coremark_performance":
                    task_modes=list(COREMARK_ARGUMENTS)
                    task=dict(inputs=[])
                else:
                    task_modes=["small"]
                    task=TASKS[case]
                rec["input_files"]=copy_inputs(task,source,native_dir)
                if copy_inputs(task,source,rv_dir)!=rec["input_files"]:
                    raise ValueError("input manifest differs by architecture")
                rec["runs"]=[]
                rec["checks"]=[]
                for mode in task_modes:
                    argv=COREMARK_ARGUMENTS[mode] if case=="coremark_performance" else task["argv"]
                    stdin_rel=task.get("stdin")
                    npath=(native_dir/stdin_rel) if stdin_rel else None
                    rpath=(rv_dir/stdin_rel) if stdin_rel else None
                    native=execute([str(native_elf),*argv],native_dir,out,
                                   case+"."+mode+".native",npath,args.timeout)
                    rv64=execute([qemu,str(target_elf),*argv],rv_dir,out,
                                 case+"."+mode+".rv64",rpath,args.timeout)
                    rec["runs"].extend([native,rv64])
                    raw_native=(out/(case+"."+mode+".native.stdout")).read_bytes()
                    raw_rv=(out/(case+"."+mode+".rv64.stdout")).read_bytes()
                    check={"mode":mode,"passed":False}
                    if case=="coremark_performance":
                        check.update(coremark_evaluate(raw_native,raw_rv,mode))
                        check["passed"] &= native["returncode"]==rv64["returncode"]==0
                    elif case=="bitcount":
                        bn=bitcount_signature(raw_native)
                        br=bitcount_signature(raw_rv)
                        check.update({"passed":bn==br and native["returncode"]==rv64["returncode"]==0,
                                      "algorithm_bit_counts":len(bn),
                                      "partial_output_oracle":True,
                                      "note":"host-specific runtime & fastest/slowest not used as oracle; method bits only"})
                    elif case=="fft":
                        check.update(fft_signature(raw_native,raw_rv))
                        check["passed"] &= native["returncode"]==rv64["returncode"]==0
                    elif case=="adpcm_encode":
                        check["passed"]=(native["returncode"]==rv64["returncode"]==0
                                         and raw_native==raw_rv
                                         and len(raw_native)>0
                                         and native["stderr_sha256"]==rv64["stderr_sha256"])
                        check["encoded_bytes_exact_match"]=raw_native==raw_rv
                        check["encoder_diagnostics_exact_match"]=(
                            native["stderr_sha256"]==rv64["stderr_sha256"])
                        check["note"]="original encoder prints final predictor state to stderr"
                    elif case=="susan_edges":
                        image_n=native_dir/"edges.pgm"
                        image_r=rv_dir/"edges.pgm"
                        check.update({
                            "image_native":dict(exists=image_n.is_file(),
                                                sha256=p2.sha(image_n) if image_n.is_file() else None),
                            "image_rv64":dict(exists=image_r.is_file(),
                                              sha256=p2.sha(image_r) if image_r.is_file() else None),
                            "passed": native["returncode"]==rv64["returncode"]==0
                                      and image_n.is_file() and image_r.is_file()
                                      and image_n.stat().st_size>100
                                      and p2.sha(image_n)==p2.sha(image_r)
                                      and image_n.read_bytes().startswith(b"P5")
                                      and raw_native==raw_rv,
                        })
                    else:
                        check["passed"]=(native["returncode"]==rv64["returncode"]==0
                                         and raw_native==raw_rv
                                         and len(raw_native)>0
                                         and native["stderr_size"]==rv64["stderr_size"]==0)
                        check["exact_stdout_match"]=raw_native==raw_rv
                    rec["checks"].append(check)
                rec["passed"]=bool(rec["checks"]) and all(c["passed"] for c in rec["checks"])
                rec["status"]="FUNCTIONAL_PASS_PROVISIONAL" if rec["passed"] else "FUNCTIONAL_MISMATCH"
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                rec["status"]="ERROR"
                rec["error"]=str(exc)
            print(f"R3C_P3B_FUNCTIONAL {case}: "+("PASS_PROVISIONAL" if rec["passed"] else "FAIL"),
                  flush=True)
    finally:
        success=(set(report["results"])==set(CASES) and all(
            rec["passed"] for rec in report["results"].values()
        ))
        report["verdict"]=("9_CASE_CROSS_ARCH_FUNCTIONAL_PASS_NOT_CORPUS_LOCK"
                           if success else "FUNCTIONAL_MISMATCH_OR_INCOMPLETE")
        manifest=out/"functional_manifest.json"
        manifest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        print("R3C_P3B_MANIFEST="+str(manifest),flush=True)
        print("R3C_P3B_VERDICT="+report["verdict"],flush=True)
        print("NO CLAIM: full corpus lock, official CoreMark score, gem5 holdout, timing or PPA.",
              flush=True)
    return 0 if success else 2


if __name__=="__main__":
    try:
        sys.exit(main())
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print("R3C_P3B_FAIL_CLOSED: "+str(exc),file=sys.stderr)
        sys.exit(1)
