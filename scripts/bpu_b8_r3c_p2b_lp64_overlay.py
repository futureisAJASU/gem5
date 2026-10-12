#!/usr/bin/env python3
"""BPU-8 R3C P2B: source-pinned, sidecar-only RV64 LP64 portability overlay.

Builds ONLY the two compiler-failing MiBench cases; never touches upstream checkout.
Not a correctness, ROI, timing, or held-out performance test.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import bpu_b8_r3c_p2_build as p2


def single_patch(path: Path, old: bytes, new: bytes, patch_log: list[dict]) -> None:
    original = path.read_bytes()
    n = original.count(old)
    if n != 1:
        raise ValueError(f"patch anchor count {n}, expected exactly one: {path}")
    modified = original.replace(old, new, 1)
    if modified == original:
        raise ValueError(f"patch had no effect: {path}")
    before = p2.sha(path)
    path.write_bytes(modified)
    patch_log.append({
        "file": str(path),
        "source_sha256": before,
        "patched_sha256": p2.sha(path),
        "old": old.decode("utf8"),
        "new": new.decode("utf8"),
    })


def nl(path: Path) -> bytes:
    return b"\r\n" if b"\r\n" in path.read_bytes()[:4096] else b"\n"


def modify_patricia(root: Path, patches: list[dict]) -> None:
    f = root / "patricia_test.c"
    single_patch(f, b"#include <rpc/rpc.h>",
                 b"/* R3C LP64 overlay: unused legacy RPC header omitted. */", patches)


def modify_rijndael(root: Path, patches: list[dict]) -> None:
    header = root / "aes.h"
    single_patch(
        header,
        b"typedef unsigned long   word;           /* must be a 32-bit storage unit */",
        b"#include <stdint.h>" + nl(header)
        + b"typedef uint32_t        word;           /* explicitly 32-bit on RV64 LP64 */",
        patches,
    )
    source = root / "aesxam.c"
    single_patch(
        source,
        b"static unsigned long a[2], mt = 1, count = 4;",
        b"static uint32_t a[2]; static unsigned int mt = 1, count = 4;",
        patches,
    )
    single_patch(
        source,
        b"*(unsigned long*)r = RAND(a[0], a[1]);",
        b"uint32_t sample = RAND(a[0], a[1]);" + nl(source)
        + b"            memcpy(r, &sample, sizeof r);",
        patches,
    )
    single_patch(source, b"fpos_t          flen;", b"long            flen;", patches)
    single_patch(
        source,
        b"fgetpos(fin, &flen);",
        b"flen = ftell(fin);", patches,
    )
    single_patch(
        source,
        b"inbuf[0] = ((char)flen & 15) | (inbuf[0] & ~15);",
        b"if(flen < 0) return -13;" + nl(source)
        + b"    inbuf[0] = ((unsigned char)flen & 15) | (inbuf[0] & ~15);",
        patches,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p1", type=Path, required=True)
    ap.add_argument("--mibench-dir", type=Path, required=True)
    ap.add_argument("--coremark-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    p1_path = args.p1.expanduser().resolve()
    p1 = json.loads(p1_path.read_text())
    mibench = args.mibench_dir.expanduser().resolve()
    coremark = args.coremark_dir.expanduser().resolve()
    p2.verify_p1(p1, mibench, coremark)
    preg = p2.ROOT / "docs/bpu8_r3c_holdout_p0_prereg_v01.json"
    if p2.sha(preg) != p1["prereg_sha256"]:
        raise ValueError("prereg drift since P1")
    if not p1["mibench"]["git_head"] or p1["mibench"]["git_tracked_dirty"]:
        raise ValueError("source custody not pinned clean")
    gcc = shutil.which("riscv64-linux-gnu-gcc")
    readelf = shutil.which("riscv64-linux-gnu-readelf")
    if not gcc or not readelf:
        raise ValueError("RV64 GCC/readelf not available")
    out = args.out.expanduser().resolve()
    if out.exists():
        raise ValueError("never overwrite any P2 experiment output")
    out.mkdir(parents=True)
    stage = out / "overlay_source" / "mibench"
    patches: list[dict] = []
    entries = []
    manifest = {
        "kind": "BPU8_R3C_P2B_LP64_OVERLAY_BUILD_ONLY",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "p1_snapshot_sha256": p2.sha(p1_path),
        "gem5_repo_commit": p2.git_head(p2.ROOT),
        "mibench_head": p1["mibench"]["git_head"],
        "coremark_head": p1["coremark"]["git_head"],
        "prereg_sha256": p1["prereg_sha256"],
        "source_original_tree_untouched": True,
        "compiler_sha256": p2.sha(Path(gcc).resolve()),
        "patches": patches,
        "builds": entries,
        "no_gem5_runs": True,
        "corpus_locked": False,
        "verdict": "NOT_STARTED",
    }
    try:
        for name in ("patricia", "rijndael_encrypt"):
            subdir = p2.SPECS[name][0]
            srcdir = mibench / subdir
            dest = stage / subdir
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(srcdir, dest, symlinks=False)
            if name == "patricia":
                modify_patricia(dest, patches)
            else:
                modify_rijndael(dest, patches)
            elf_file = out / (name + ".rv64.elf")
            cmd, cwd = p2.build_cmd(name, stage, coremark, gcc, elf_file)
            p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=180)
            (out / (name + ".compile.log")).write_text(p.stdout)
            entry = {"case": name, "argv": cmd, "compile_cwd": str(cwd),
                     "compile_returncode": p.returncode}
            if p.returncode == 0 and elf_file.is_file():
                head = subprocess.run([readelf, "-h", str(elf_file)],
                                      check=True, capture_output=True, text=True)
                dyn = subprocess.run([readelf, "-d", str(elf_file)],
                                     check=True, capture_output=True, text=True)
                (out / (name + ".elf-header.txt")).write_text(head.stdout)
                good = p2.is_static_rv64_lp64d(head.stdout, dyn.stdout)
                entry.update(elf_size=elf_file.stat().st_size,
                             elf_sha256=p2.sha(elf_file),
                             static_rv64_lp64d=good)
                if not good:
                    entry["error"] = "ELF validation failed"
            else:
                entry["error"] = "compile failed; inspect .compile.log"
            entries.append(entry)
            print(f"R3C_P2B_BUILD {name}: "
                  f"{'PASS' if entry.get('static_rv64_lp64d') else 'FAIL'}", flush=True)
    finally:
        passed = len(entries) == 2 and all(x.get("static_rv64_lp64d") for x in entries)
        manifest["verdict"] = ("OVERLAY_ELF_2_OF_2_PASS_NOT_FUNCTIONAL"
                               if passed else "OVERLAY_BUILD_INCOMPLETE_OR_FAILED")
        (out / "portability_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"R3C_P2B_MANIFEST={out / 'portability_manifest.json'}")
        print("R3C_P2B_VERDICT=" + manifest["verdict"])
        print("NO CLAIM: functionality, unchanged algorithm, corpus lock, holdout, PPA")
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print("R3C_P2B_FAIL_CLOSED: " + str(exc), file=sys.stderr)
        sys.exit(1)
