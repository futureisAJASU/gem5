#!/usr/bin/env python3
"""R3C P3A: correctness feasibility for the TWO LP64-overlay cases.

Compare identical, P1-pinned MiBench input bytes using:
* native AArch64 static build of the SAME staged patched sources
* QEMU-user execution of the already built static RV64 LP64D ELF

No gem5 run, no predictor performance measurement, no corpus lock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2

KEY = "1234567890abcdeffedcba09876543211234567890abcdeffedcba0987654321"
CASES = ("patricia", "rijndael_encrypt")


def execute(cmd: list[str], cwd: Path, name: str, out: Path, timeout: int) -> dict:
    try:
        cp = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("execution timeout: " + name) from exc
    out.mkdir(parents=True, exist_ok=True)
    stdout_path = out / (name + ".stdout")
    stderr_path = out / (name + ".stderr")
    stdout_path.write_bytes(cp.stdout)
    stderr_path.write_bytes(cp.stderr)
    return {
        "id": name,
        "cmd": cmd,
        "cwd": str(cwd),
        "returncode": cp.returncode,
        "stdout_sha256": p2.sha(stdout_path),
        "stderr_sha256": p2.sha(stderr_path),
        "stdout_size": len(cp.stdout),
        "stderr_size": len(cp.stderr),
    }


def patricia_ok(native: dict, rv64: dict) -> bool:
    # The upstream patricia_test.c deliberately ends with exit(1).
    return (native["returncode"] == rv64["returncode"] == 1
            and native["stdout_size"] > 0
            and native["stdout_sha256"] == rv64["stdout_sha256"]
            and native["stderr_sha256"] == rv64["stderr_sha256"]
            and native["stderr_size"] == rv64["stderr_size"] == 0)


def file_record(p: Path) -> dict:
    if not p.is_file():
        return {"exists": False, "path": str(p)}
    return {"exists": True, "path": str(p), "size": p.stat().st_size,
            "sha256": p2.sha(p)}


def validate_source_gate(p1: dict, p1path: Path, mibench: Path, coremark: Path,
                         p2b: dict, p2b_path: Path, p2b_root: Path) -> None:
    p2.verify_p1(p1, mibench, coremark)
    if p2b.get("verdict") != "OVERLAY_ELF_2_OF_2_PASS_NOT_FUNCTIONAL":
        raise ValueError("P2B gate not passed")
    if p2b.get("p1_snapshot_sha256") != p2.sha(p1path):
        raise ValueError("P2B refers to a different P1 source inventory")
    if p2b.get("mibench_head") != p1["mibench"]["git_head"]:
        raise ValueError("P2B MiBench source revision differs from P1")
    if p2b.get("prereg_sha256") != p1["prereg_sha256"]:
        raise ValueError("P2B original prereg drift")
    if len(p2b.get("patches", [])) != 7:
        raise ValueError("P2B expected exactly seven explicit patch records")
    for patch in p2b["patches"]:
        patch_path = Path(patch["file"]).resolve()
        if not patch_path.is_relative_to(p2b_root.resolve()):
            raise ValueError("P2B patch path outside immutable sidecar tree")
        if not patch_path.is_file() or p2.sha(patch_path) != patch["patched_sha256"]:
            raise ValueError("P2B stage patch mismatch: " + str(patch_path))
    builds = {rec["case"]: rec for rec in p2b.get("builds", [])}
    if set(builds) != set(CASES):
        raise ValueError("P2B expected exactly two built cases")
    for name in CASES:
        elf = p2b_root / (name + ".rv64.elf")
        record = builds[name]
        if (record.get("compile_returncode") != 0
                or record.get("static_rv64_lp64d") is not True
                or not elf.is_file() or p2.sha(elf) != record.get("elf_sha256")):
            raise ValueError("P2B ELF custody mismatch: " + name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1", type=Path, required=True)
    parser.add_argument("--p2b-dir", type=Path, required=True)
    parser.add_argument("--mibench-dir", type=Path, required=True)
    parser.add_argument("--coremark-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not (1 <= args.timeout <= 3600):
        raise ValueError("timeout must be 1..3600 seconds")

    p1path = args.p1.expanduser().resolve()
    p2b_root = args.p2b_dir.expanduser().resolve()
    p2b_path = p2b_root / "portability_manifest.json"
    mibench = args.mibench_dir.expanduser().resolve()
    coremark = args.coremark_dir.expanduser().resolve()
    p1 = json.loads(p1path.read_text())
    p2b = json.loads(p2b_path.read_text())
    validate_source_gate(p1, p1path, mibench, coremark, p2b, p2b_path, p2b_root)

    host_gcc = shutil.which("gcc")
    qemu = shutil.which("qemu-riscv64")
    if not host_gcc or not qemu:
        raise ValueError(f"missing P3A executor: gcc={host_gcc}, qemu-riscv64={qemu}; "
                         "install/configure qemu-user separately before running")
    # Verify actual target before creating an output directory.
    probe = subprocess.run([qemu, "--version"], capture_output=True,
                           text=True, timeout=10, check=True)
    output = args.out.expanduser().resolve()
    if output.exists():
        raise ValueError("P3A output exists; never overwrite earlier evidence")
    output.mkdir(parents=True)

    manifest: dict = {
        "kind": "BPU8_R3C_P3A_LP64_CORRECTNESS_FEASIBILITY_NO_PERF",
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "p1_sha256": p2.sha(p1path),
        "p2b_manifest_sha256": p2.sha(p2b_path),
        "gcc_version": subprocess.check_output([host_gcc, "--version"], text=True).splitlines()[0],
        "host_gcc_sha256": p2.sha(Path(host_gcc).resolve()),
        "qemu_version": probe.stdout.splitlines()[0],
        "qemu_sha256": p2.sha(Path(qemu).resolve()),
        "gem5_runs": 0,
        "predictor_comparisons": 0,
        "holdout_corpus_locked": False,
        "results": {},
        "verdict": "INCOMPLETE",
    }
    try:
        for name in CASES:
            source_root = p2b_root / "overlay_source" / "mibench"
            stage = source_root / p2.SPECS[name][0]
            native = output / (name + ".native.elf")
            buildcmd, cwd = p2.build_cmd(name, source_root, coremark, host_gcc, native)
            # The target-specific ISA flags have no meaning for the host AArch64 build.
            cmd = [x for x in buildcmd if x not in ("-march=rv64gc", "-mabi=lp64d")]
            bp = subprocess.run(cmd, cwd=cwd, capture_output=True,
                                timeout=180, text=True)
            (output / (name + ".native.compile.stdout")).write_text(bp.stdout)
            (output / (name + ".native.compile.stderr")).write_text(bp.stderr)
            if bp.returncode != 0 or not native.is_file():
                raise RuntimeError(f"{name}: native control build failed rc={bp.returncode}")
            rv = p2b_root / (name + ".rv64.elf")
            result: dict = {
                "native_build_cmd": cmd,
                "native_elf": file_record(native),
                "rv64_elf": file_record(rv),
                "observations": [],
                "passed": False,
            }
            manifest["results"][name] = result
            work_native = output / (name + ".work.native")
            work_rv = output / (name + ".work.rv64")
            work_native.mkdir()
            work_rv.mkdir()

            if name == "patricia":
                input_name = "small.udp"
                src = stage / input_name
                if not src.is_file():
                    raise RuntimeError(f"{name}: missing original input {src}")
                for w in (work_native, work_rv):
                    shutil.copy2(src, w / input_name)
                result["input"] = file_record(src)
                a = execute([str(native), input_name], work_native,
                            "patricia.native", output, args.timeout)
                b = execute([qemu, str(rv), input_name], work_rv,
                            "patricia.rv64", output, args.timeout)
                result["observations"] = [a, b]
                result["passed"] = patricia_ok(a, b)
                result["note"] = ("upstream patricia_test.c has intentional exit(1); "
                                  "cross-machine identical stdout is provisional "
                                  "equivalence, not independent IPv4 correctness")
            else:
                input_name = "input_small.asc"
                src = stage / input_name
                if not src.is_file():
                    raise RuntimeError(f"{name}: missing original input {src}")
                for w in (work_native, work_rv):
                    shutil.copy2(src, w / input_name)
                result["input"] = file_record(src)
                commands = [
                    ([str(native), input_name, "encrypted.bin", "e", KEY],
                     work_native, "aes.native.enc"),
                    ([str(native), "encrypted.bin", "decrypted.bin", "d", KEY],
                     work_native, "aes.native.dec"),
                    ([qemu, str(rv), input_name, "encrypted.bin", "e", KEY],
                     work_rv, "aes.rv64.enc"),
                    ([qemu, str(rv), "encrypted.bin", "decrypted.bin", "d", KEY],
                     work_rv, "aes.rv64.dec"),
                    ([str(native), "encrypted.bin", "native_by_rv64.dec", "d", KEY],
                     work_rv, "aes.rv64_to_native.dec"),
                    ([qemu, str(rv), "encrypted.bin", "rv64_by_native.dec", "d", KEY],
                     work_native, "aes.native_to_rv64.dec"),
                ]
                # Cross-configuration decrypt commands use the opposite executable
                # against the ciphertext in the selected working directory.
                a = [execute(cmd, work, id_, output, args.timeout)
                     for cmd, work, id_ in commands]
                result["observations"] = a
                outputs = [file_record(w / file) for w, file in (
                    (work_native, "encrypted.bin"),
                    (work_native, "decrypted.bin"),
                    (work_native, "rv64_by_native.dec"),
                    (work_rv, "encrypted.bin"),
                    (work_rv, "decrypted.bin"),
                    (work_rv, "native_by_rv64.dec"),
                )]
                result["output_files"] = outputs
                orig_hash = p2.sha(src)
                result["passed"] = (
                    all(x["returncode"] == 0 for x in a)
                    and all(x["exists"] for x in outputs)
                    and outputs[0]["sha256"] == outputs[3]["sha256"]
                    and all(outputs[i]["sha256"] == orig_hash for i in (1, 2, 4, 5))
                )
                result["note"] = ("same patched source, deterministic ciphertext, "
                                  "bidirectional roundtrip checked; independent "
                                  "published AES known-answer vector NOT yet verified")
            print(f"R3C_P3A_FUNCTIONAL {name}: "
                  f"{'PASS_PROVISIONAL' if result['passed'] else 'FAIL'}", flush=True)
    finally:
        success = set(manifest["results"]) == set(CASES) and all(
            item["passed"] for item in manifest["results"].values()
        )
        manifest["verdict"] = (
            "CROSS_HOST_EQUIVALENCE_2_OF_2_PASS_NOT_CORPUS_LOCK"
            if success else "INCOMPLETE_OR_FUNCTIONAL_MISMATCH"
        )
        (output / "functional_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
        print("R3C_P3A_MANIFEST=" + str(output / "functional_manifest.json"))
        print("R3C_P3A_VERDICT=" + manifest["verdict"])
        print("NO CLAIM: independent algorithm proof, official score, corpus lock, gem5 performance or RTL/PPA")
    return 0 if success else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print("R3C_P3A_FAIL_CLOSED: " + str(error), file=sys.stderr)
        sys.exit(1)
