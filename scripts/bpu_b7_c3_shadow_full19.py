#!/usr/bin/env python3
"""BPU-7 C3 PC_BIAS full-19 SHADOW-only sweep and fail-closed evidence gate.

One command: optional incremental gem5 build -> Embench prepare if missing ->
19 workloads x (G5, G7, C3 PC_BIAS E64, E128, E256) = 95 ROI ->
per-row invariant checks -> CSV, human-readable summary and SHA256 provenance.

CRITICAL: Current C3 NEVER overrides G5 frontend prediction, so fixes/breaks
are hypothetical SAME-PATH diagnostics. No M1 speedup, no real correction
performance, no C3 HIST_TAG and no full 21-profile Round-I claim.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = (
    "aha-mont64", "crc32", "cubic", "edn", "huffbench", "matmult-int",
    "minver", "nbody", "nettle-aes", "nettle-sha256", "nsichneu",
    "picojpeg", "qrduino", "sglib-combined", "slre", "st",
    "statemate", "ud", "wikisort",
)
# Keep this order, placing a small sanity workload near the front.
PROFILES = {
    "g5": ("tage5-iso45k", 45736, 0),
    "g7": ("tage7-iso65k", 65192, 0),
    "c3_e64": ("tage5-c3-pcbias-shadow-e64", 46760, 1024),
    "c3_e128": ("tage5-c3-pcbias-shadow-e128", 47784, 2048),
    "c3_e256": ("tage5-c3-pcbias-shadow-e256", 49832, 4096),
}
FIELDS = (
    "profile", "workload", "simTicks", "simInsts", "committedConditionalPredictions",
    "committedConditionalWrong", "finalConditionalWrong", "c3PcBiasStorageBits",
    "storageBits", "c3PcBiasBankReads", "c3PcBiasEligibleCommitted",
    "c3PcBiasTagHits", "c3PcBiasWouldFlip", "c3PcBiasWouldFix",
    "c3PcBiasWouldBreak", "c3PcBiasTrainWrites", "c3PcBiasAllocations",
    "c3PcBiasEvictions", "c3PcBiasCollisionBlocked", "shadowNet",
    "hypotheticalWrong", "hypotheticalMPKI", "roi_sha256",
)
CFG = ROOT / "configs/02_little_v052_rv64_proxy.py"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def git(*params, cwd=ROOT):
    return subprocess.check_output(
        ["git", *params], cwd=cwd, text=True, stderr=subprocess.PIPE
    ).strip()


def unique_int(stats, key):
    matches = [(name, value) for name, value in stats.items()
               if name == key or name.endswith("." + key)]
    if len(matches) != 1:
        raise ValueError(f"expected precisely one stat {key}, found: {matches}")
    val = matches[0][1]
    # All counters used here must be decimal integers. Avoid float rounding.
    try:
        return int(val)
    except ValueError:
        from decimal import Decimal
        n = Decimal(val)
        if n != int(n):
            raise ValueError(f"non-integer stat {key}={val}")
        return int(n)


def parse_first_roi(path):
    # Compare the ORIGINAL gem5 text.cc format, not a guessed full marker.
    # Its real end marker has THREE spaces after 'Statistics':
    # '---------- End Simulation Statistics   ----------'.
    # Historical BPU-4C intentionally matched only the common prefix.
    lines = path.read_text().splitlines(keepends=True)
    begin_prefix = "---------- Begin Simulation Statistics"
    end_prefix = "---------- End Simulation Statistics"
    starts = [i for i, line in enumerate(lines)
              if line.startswith(begin_prefix)]
    if not starts:
        raise ValueError(f"missing begin-stats marker in {path}")
    start = starts[0]
    ends = [i for i in range(start + 1, len(lines))
            if lines[i].startswith(end_prefix)]
    if not ends:
        raise ValueError(f"missing end-stats marker in {path}")
    end = ends[0]
    if any(i < end for i in starts[1:]):
        raise ValueError(f"overlapping stats sections in {path}")
    roi = "".join(lines[start:end + 1])
    stats = {}
    for line in lines[start + 1:end]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            from decimal import Decimal
            Decimal(parts[1])
        except Exception:
            continue
        if parts[0] in stats:
            raise ValueError(f"duplicate statistic {parts[0]} in {path}")
        stats[parts[0]] = parts[1]
    if not stats:
        raise ValueError(f"empty ROI stats {path}")
    return stats, roi

def expect(cond, explanation):
    if not cond:
        raise ValueError(explanation)


def inspect_row(stats, profile, workload, binary_sha, roi_sha):
    expected_all, expected_extra = PROFILES[profile][1:]
    vals = {k: unique_int(stats, k) for k in (
        "simTicks", "simInsts", "committedConditionalPredictions",
        "committedConditionalWrong", "finalConditionalWrong",
        "storageBits", "c3PcBiasStorageBits", "c3PcBiasBankReads",
        "c3PcBiasEligibleCommitted", "c3PcBiasTagHits", "c3PcBiasWouldFlip",
        "c3PcBiasWouldFix", "c3PcBiasWouldBreak", "c3PcBiasTrainWrites",
        "c3PcBiasAllocations", "c3PcBiasEvictions",
        "c3PcBiasCollisionBlocked",
        "predictionMetadataChecks", "historyRestoreChecks",
        "historyStateRestores",
    )}
    v = vals
    expect(v["storageBits"] == expected_all and
           v["c3PcBiasStorageBits"] == expected_extra,
           f"{profile}/{workload}: storage bits mismatch {v['storageBits']}/{v['c3PcBiasStorageBits']}")
    expect(v["simInsts"] > 0 and v["simTicks"] > 0, f"{profile}/{workload}: no work")
    expect(v["committedConditionalWrong"] == v["finalConditionalWrong"],
           f"{profile}/{workload}: shadow changed G5 prediction correctness")
    expect(v["committedConditionalWrong"] <= v["committedConditionalPredictions"],
           f"{profile}/{workload}: impossible TAGE wrong count")
    expect(v["predictionMetadataChecks"] == v["committedConditionalPredictions"],
           f"{profile}/{workload}: predictor metadata checks mismatch")
    expect(v["historyRestoreChecks"] == v["historyStateRestores"],
           f"{profile}/{workload}: history rollback checks mismatch")
    reads = v["c3PcBiasBankReads"]
    elig = v["c3PcBiasEligibleCommitted"]
    hits = v["c3PcBiasTagHits"]
    wants = v["c3PcBiasWouldFlip"]
    fixes = v["c3PcBiasWouldFix"]
    breaks = v["c3PcBiasWouldBreak"]
    writes = v["c3PcBiasTrainWrites"]
    alloc = v["c3PcBiasAllocations"]
    evict = v["c3PcBiasEvictions"]
    blocked = v["c3PcBiasCollisionBlocked"]
    expect(0 <= wants <= hits <= elig, f"{profile}/{workload}: impossible eligibility/hit/flip")
    expect(wants == fixes + breaks, f"{profile}/{workload}: flip fix-break mismatch")
    expect(writes + blocked == elig, f"{profile}/{workload}: training accounting mismatch")
    expect(0 <= evict <= alloc <= writes, f"{profile}/{workload}: allocation accounting")
    expect(reads >= elig, f"{profile}/{workload}: reads less than committed eligible")
    if profile in ("g5", "g7"):
        expect(all(v[k] == 0 for k in (
            "c3PcBiasBankReads", "c3PcBiasEligibleCommitted", "c3PcBiasTagHits",
            "c3PcBiasWouldFlip", "c3PcBiasWouldFix", "c3PcBiasWouldBreak",
            "c3PcBiasTrainWrites", "c3PcBiasAllocations",
            "c3PcBiasEvictions", "c3PcBiasCollisionBlocked",
        )), f"{profile}/{workload}: baseline has C3 activity")
    hypothetical_wrong = v["committedConditionalWrong"] - fixes + breaks
    expect(0 <= hypothetical_wrong <= v["committedConditionalPredictions"],
           f"{profile}/{workload}: impossible hypothetical errors")
    row = {k: v[k] for k in FIELDS if k in v}
    row.update(
        profile=profile,
        workload=workload,
        shadowNet=fixes - breaks,
        hypotheticalWrong=hypothetical_wrong,
        hypotheticalMPKI=f"{1000.0*hypothetical_wrong/v['simInsts']:.9f}",
        roi_sha256=roi_sha,
    )
    return row


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def emit_summary(out, rows, count_expected):
    per_profile = {k: [r for r in rows if r["profile"] == k] for k in PROFILES}
    lines = [
        "BPU-7 C3 PC_BIAS: SHADOW-ONLY DIAGNOSTIC",
        "NOT REAL M1, NOT ACTUAL C3 CORRECTION PERFORMANCE",
        f"ROI_CHECKED={len(rows)}/{count_expected}",
        "",
        "profile       ROI     G5wrong     wouldFix   wouldBreak       net      auxReads",
    ]
    for p, rr in per_profile.items():
        lines.append(
            f"{p:12s} {len(rr):3d}  "
            f"{sum(int(r['committedConditionalWrong']) for r in rr):12d}"
            f" {sum(int(r['c3PcBiasWouldFix']) for r in rr):12d}"
            f" {sum(int(r['c3PcBiasWouldBreak']) for r in rr):12d}"
            f" {sum(int(r['shadowNet']) for r in rr):9d}"
            f" {sum(int(r['c3PcBiasBankReads']) for r in rr):13d}"
        )
    lines += [
        "",
        "Note: fixes/breaks are counterfactual on the G5 prediction path.",
        "No benefit to measured cycles is expected or attributed to C3.",
        "The first ROI stats dump is used, matching the historical BPU-4C methodology.",
        "BPU7_C3_SHADOW_ALL_COMPLETED=" +
        ("PASS" if len(rows) == count_expected else "INCOMPLETE"),
    ]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2, help="SCons build parallelism, default 2")
    parser.add_argument("--no-build", action="store_true",
                        help="Reuse existing gem5.opt without incremental SCons compile")
    parser.add_argument("--prepare-if-missing", action="store_true",
                        help="Run existing pinned RV64 Embench prepare script if any of 19 binaries absent")
    parser.add_argument("--embench-build", type=Path,
                        default=ROOT / "benchmarks/external/embench-iot/bd-rv64-gem5")
    parser.add_argument("--gem5", type=Path, default=ROOT / "build/RISCV/gem5.opt")
    parser.add_argument("--out", type=Path,
                        default=ROOT / ("bpu_b7_c3_shadow_full19_" +
                                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    parser.add_argument("--resume", action="store_true",
                        help="Continue same --out, verifying manifest and completed row hashes")
    parser.add_argument("--list", action="store_true",
                        help="Print planned 95 jobs and exit without building/running")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")
    work = [(profile, workload) for workload in WORKLOADS for profile in PROFILES]
    if args.list:
        for profile, workload in work:
            print(f"{profile:12s} {workload}")
        print(f"SHADOW_ONLY_ROI_PLAN={len(work)}; M1_CORRECTION=NOT_IMPLEMENTED")
        return

    out = args.out.resolve()
    build = args.embench_build.resolve()
    gem5 = args.gem5.resolve()
    head = git("rev-parse", "HEAD")
    binary_map = {w: build / "src" / w / w for w in WORKLOADS}

    print("[0] Check directed C++ state-machine, compile source and pinned Embench inputs",
          flush=True)
    subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-Isrc", "tests/bpu7/c3_pc_bias_directed.cc",
                    "-o", "/tmp/bpu_b7_c3_directed_full19"],
                   cwd=ROOT, check=True)
    subprocess.run(["/tmp/bpu_b7_c3_directed_full19"], check=True)
    if not args.no_build:
        subprocess.run(["scons", "build/RISCV/gem5.opt",
                        "--ignore-style", f"-j{args.jobs}"], cwd=ROOT, check=True)
    if not gem5.is_file():
        raise RuntimeError(f"gem5 binary missing: {gem5}")

    missing = [w for w, p in binary_map.items() if not p.is_file()]
    if missing and args.prepare_if_missing:
        print(f"[1] Missing {len(missing)} Embench binaries; prepare pinned RV64 corpus",
              flush=True)
        environment = os.environ.copy()
        environment["JOBS"] = str(args.jobs)
        # Official repository script uses EMBENCH_BUILD/EMBENCH_DIR overrides.
        environment["EMBENCH_BUILD"] = str(build)
        environment["EMBENCH_DIR"] = str(build.parent)
        subprocess.run(["bash", "scripts/rv64_embench_prepare.sh"],
                       cwd=ROOT, env=environment, check=True)
        missing = [w for w, p in binary_map.items() if not p.is_file()]
    if missing:
        raise RuntimeError(
            "Missing workload binaries: " + ", ".join(missing) +
            ". Use --prepare-if-missing, or point --embench-build to the pinned existing build."
        )

    source_dir = build.parent
    emb_head = git("rev-parse", "HEAD", cwd=source_dir) if (source_dir / ".git").exists() else "NO_GIT_METADATA"
    matrix_file = ROOT / "docs/bpu7_sweep_matrix_v02.json"
    matrix = json.loads(matrix_file.read_text())
    expect(matrix["status"] == "PRE_FREEZE" and matrix["execution_permitted"] is False,
           "official 21-profile matrix unexpectedly changed; this runner must not authorize M1")
    expect(tuple(matrix["workloads"]) == WORKLOADS,
           "workload list changed relative to the frozen BPU-7 experiment matrix")
    manifest = {
        "experiment": "BPU7_C3_PC_BIAS_SHADOW_FULL19",
        "status": "SHADOW_DIAGNOSTIC_NOT_M1",
        "no_measured_real_correction": True,
        "repo_head": head,
        "repo_dirty_tracked": bool(git("status", "--porcelain", "--untracked-files=no")),
        "gem5_sha256": sha(gem5),
        "config_sha256": sha(CFG),
        "matrix_sha256": sha(matrix_file),
        "runner_sha256": sha(Path(__file__)),
        "embench_head": emb_head,
        "benchmarks": {w: sha(p) for w, p in binary_map.items()},
        "job_count": len(work),
        "profiles": {p: {"bp_type": val[0], "total_bits": val[1],
                          "aux_bits": val[2]} for p, val in PROFILES.items()},
        "condition": {
            "bp_inst_shift": 1, "bp_cond_shift": 1,
            "bp_btb_shift": 2, "bp_indirect_shift": 1, "btb_entries": 4096,
        },
    }
    manifest_path = out / "manifest.json"
    if args.resume:
        if not manifest_path.exists():
            raise RuntimeError("--resume requires existing manifest.json")
        old = json.loads(manifest_path.read_text())
        # A parser-only runner hotfix changes source HEAD and script SHA.
        # It DOES NOT change an already-built gem5 binary, its executable
        # configuration, or the recorded Embench binaries. Allow only these
        # two transparent analysis/provenance differences when resuming.
        non_experimental = {"repo_head", "runner_sha256"}
        changes = {
            key: {"original": old.get(key), "current": manifest.get(key)}
            for key in (set(old) | set(manifest))
            if old.get(key) != manifest.get(key)
        }
        material = set(changes) - non_experimental
        if material:
            raise RuntimeError(
                "FAIL-CLOSED: experimental manifest fields changed: " +
                ", ".join(sorted(material)) +
                "; refusing mixed gem5/config/binary evidence"
            )
        if changes:
            # Preserve original manifest.json completely unmodified.
            with (out / "resume_audit.jsonl").open("a") as audit:
                audit.write(json.dumps({
                    "event": "RUNNER_PARSER_HOTFIX",
                    "old_manifest_sha256": sha(manifest_path),
                    "changed_non_experimental_fields": changes,
                    "immutable_inputs_verified": True,
                    "note": "No code changes to the executed gem5 binary. "
                            "Old raw stats preserved and reparsed."
                }, sort_keys=True) + "\n")
            print("[2] Resume: original manifest preserved; gem5, configuration "
                  "and all 19 benchmark SHA256 match. Analysis-source "
                  "change recorded in resume_audit.jsonl", flush=True)
        else:
            print("[2] Resume: exact manifest identity verified", flush=True)
    else:
        if out.exists():
            raise RuntimeError("Output directory already exists. Supply --resume or a new --out.")
        out.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    rows = []
    baseline = {}
    print(f"[3] {len(work)} workloads×profiles (19×5), SHADOW ONLY", flush=True)
    for number, (profile, workload) in enumerate(work, 1):
        bp_type, total_bits, aux_bits = PROFILES[profile]
        d = out / profile / workload
        finished = d / ".verified.json"
        command = [
            str(gem5), f"--outdir={d}", str(CFG),
            "--binary", str(binary_map[workload]),
            "--bp-type", bp_type,
            "--bp-inst-shift", "1",
            "--bp-cond-shift", "1",
            "--bp-btb-shift", "2",
            "--bp-indirect-shift", "1",
            "--btb-entries", "4096",
        ]
        existing_raw = d.exists()
        if existing_raw and not args.resume:
            raise RuntimeError(
                f"Output already exists: {d}; pass --resume to preserve it"
            )
        if not existing_raw:
            d.mkdir(parents=True, exist_ok=False)
            (d / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            print(f"  [{number:3d}/{len(work)}] RUN   {workload}/{profile}",
                  flush=True)
            with (d / "stdout.txt").open("x") as fo, (d / "stderr.txt").open("x") as fe:
                status = subprocess.run(command, cwd=ROOT, stdout=fo, stderr=fe)
            if status.returncode != 0:
                raise RuntimeError(
                    f"{workload}/{profile} failed rc={status.returncode}; "
                    f"inspect {d}/stderr.txt and stdout.txt"
                )
        else:
            print(f"  [{number:3d}/{len(work)}] CHECK {workload}/{profile} "
                  f"(preserving existing raw artifacts)", flush=True)

        cmd_path = d / "command.json"
        if not cmd_path.exists() or json.loads(cmd_path.read_text()) != command:
            raise RuntimeError(
                f"{workload}/{profile}: saved invocation does not match "
                "the frozen profile and paths; refusing reuse"
            )
        if not (d / "stdout.txt").is_file() or not (d / "stats.txt").is_file():
            raise RuntimeError(
                f"{workload}/{profile}: missing raw stdout or stats; "
                "original evidence preserved, manual triage required"
            )
        if "SIMULATION_EXIT_CODE=0" not in (d / "stdout.txt").read_text():
            raise RuntimeError(
                f"{workload}/{profile}: original stdout lacks clean exit marker; "
                "never silently assume incomplete work finished"
            )
        stats, roi = parse_first_roi(d / "stats.txt")
        roi_path = d / "roi.stats"
        # An interrupted earlier parser invocation may have saved a
        # valid roi.stats already. Reuse it byte-for-byte if identical.
        if roi_path.exists():
            if roi_path.read_text() != roi:
                raise RuntimeError(
                    f"{workload}/{profile}: old ROI differs from complete raw "
                    "stats. Evidence preserved, manual triage required"
                )
        else:
            with roi_path.open("x") as f_roi:
                f_roi.write(roi)
        row = inspect_row(stats, profile, workload,
                          manifest["benchmarks"][workload], sha(roi_path))
        verification = {
            "row": row,
            "gem5_sha256": manifest["gem5_sha256"],
            "binary_sha256": manifest["benchmarks"][workload],
        }
        if finished.exists():
            if json.loads(finished.read_text()) != verification:
                raise RuntimeError(
                    f"{workload}/{profile}: prior verified snapshot mismatches "
                    "recomputed raw statistics; refusing silent alteration"
                )
            print(f"  [{number:3d}/{len(work)}] REUSE {workload}/{profile}",
                  flush=True)
        else:
            # Recover the user's FIRST G5 ROI, which had already completed
            # before the former exact-spaces end-marker parser rejected it.
            with finished.open("x") as fv:
                fv.write(json.dumps(verification, indent=2) + "\n")
            print(f"  [{number:3d}/{len(work)}] "
                  f"{'RECOVER' if existing_raw else 'VERIFY'} "
                  f"{workload}/{profile}", flush=True)
        if profile == "g5":
            baseline[workload] = row
        elif profile.startswith("c3_"):
            g5 = baseline[workload]
            for field in (
                "simTicks", "simInsts", "committedConditionalPredictions",
                "committedConditionalWrong", "finalConditionalWrong",
            ):
                expect(int(row[field]) == int(g5[field]),
                       f"BLOCKED: {workload} {profile} shadow differs from G5 on {field}: "
                       f"{row[field]} != {g5[field]}")
        elif profile == "g7":
            expect(int(row["simInsts"]) == int(baseline[workload]["simInsts"]),
                   f"BLOCKED: G7 {workload} committed instruction count mismatch")

        rows.append(row)
        write_csv(out / "results.csv", rows)
        if profile == "c3_e256" or number == len(work):
            emit_summary(out, rows, len(work))
    emit_summary(out, rows, len(work))
    print("\nRESULT_FILES:")
    for name in ("manifest.json", "results.csv", "summary.txt"):
        print(out / name)
    print("PASS = shadow functional and evidence-accounting pass ONLY")
    print("DO NOT REPORT shadow fixes or ticks as actual M1 improvements")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"\nBPU7_C3_SHADOW_SWEEP_FAIL_CLOSED: {exc}", file=sys.stderr)
        sys.exit(1)
