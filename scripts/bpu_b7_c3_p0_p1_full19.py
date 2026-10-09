#!/usr/bin/env python3
"""BPU-7 C3 P0 residual vs P1 PC chooser: SAME-BINARY SHADOW full-19 audit.

19 Embench workloads x 8 profiles (G5, G7, P0 E64/E128/E256,
P1 E64/E128/E256) = 152 validated ROI. Supports incremental build, existing
cross-built Embench corpus, immutable SHA256 manifest and fail-closed resume.

NO actual C3 direction override, M1 performance result, or frozen Round-I
registration. Do not attribute P0/P1 shadow ticks to actual correction gain.
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
    "p0_e64": ("tage5-c3-pcbias-shadow-e64", 46760, 1024),
    "p0_e128": ("tage5-c3-pcbias-shadow-e128", 47784, 2048),
    "p0_e256": ("tage5-c3-pcbias-shadow-e256", 49832, 4096),
    "p1_e64": ("tage5-c3-pcchooser-shadow-e64", 46824, 1088),
    "p1_e128": ("tage5-c3-pcchooser-shadow-e128", 47912, 2176),
    "p1_e256": ("tage5-c3-pcchooser-shadow-e256", 50088, 4352),
}
FIELDS = (
    "profile", "workload", "simTicks", "simInsts", "committedConditionalPredictions",
    "committedConditionalWrong", "finalConditionalWrong",
    "c3PcBiasStorageBits", "c3PcChooserStorageBits", "storageBits",
    "c3PcBiasBankReads", "c3PcBiasEligibleCommitted",
    "c3PcBiasTagHits", "c3PcBiasWouldFlip", "c3PcBiasWouldFix",
    "c3PcBiasWouldBreak", "c3PcBiasTrainWrites", "c3PcBiasAllocations",
    "c3PcBiasEvictions", "c3PcBiasCollisionBlocked",
    "c3PcChooserReads", "c3PcChooserEligibleCommitted",
    "c3PcChooserTagHits", "c3PcChooserDisagreements",
    "c3PcChooserWouldOverride", "c3PcChooserWouldFix",
    "c3PcChooserWouldBreak", "c3PcChooserRowWrites",
    "c3PcChooserDirectionUpdates", "c3PcChooserChooserUpdates",
    "c3PcChooserAllocations", "c3PcChooserEvictions",
    "c3PcChooserCollisionBlocked", "c3PcChooserStalePredictions",
    "shadowNet", "hypotheticalWrong", "hypotheticalMPKI",
    "roi_sha256",
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
    expected_total, expected_extra = PROFILES[profile][1:]
    is_p0 = profile.startswith("p0_")
    is_p1 = profile.startswith("p1_")
    shared = (
        "simTicks", "simInsts", "committedConditionalPredictions",
        "committedConditionalWrong", "finalConditionalWrong",
        "storageBits", "c3PcBiasStorageBits", "c3PcChooserStorageBits",
        "predictionMetadataChecks", "historyRestoreChecks",
        "historyStateRestores",
    )
    p0_keys = (
        "c3PcBiasBankReads", "c3PcBiasEligibleCommitted", "c3PcBiasTagHits",
        "c3PcBiasWouldFlip", "c3PcBiasWouldFix", "c3PcBiasWouldBreak",
        "c3PcBiasTrainWrites", "c3PcBiasAllocations", "c3PcBiasEvictions",
        "c3PcBiasCollisionBlocked",
    )
    p1_keys = (
        "c3PcChooserReads", "c3PcChooserEligibleCommitted",
        "c3PcChooserTagHits", "c3PcChooserDisagreements",
        "c3PcChooserWouldOverride", "c3PcChooserWouldFix",
        "c3PcChooserWouldBreak", "c3PcChooserRowWrites",
        "c3PcChooserDirectionUpdates", "c3PcChooserChooserUpdates",
        "c3PcChooserAllocations", "c3PcChooserEvictions",
        "c3PcChooserCollisionBlocked", "c3PcChooserStalePredictions",
    )
    v = {key: unique_int(stats, key) for key in shared + p0_keys + p1_keys}
    expect(v["storageBits"] == expected_total,
           f"{profile}/{workload}: combined state bits mismatch")
    expect(v["c3PcBiasStorageBits"] == (expected_extra if is_p0 else 0),
           f"{profile}/{workload}: PC residual bits mismatch")
    expect(v["c3PcChooserStorageBits"] == (expected_extra if is_p1 else 0),
           f"{profile}/{workload}: PC chooser bits mismatch")
    expect(v["simInsts"] > 0 and v["simTicks"] > 0,
           f"{profile}/{workload}: empty execution")
    expect(v["committedConditionalWrong"] == v["finalConditionalWrong"],
           f"{profile}/{workload}: shadow changed G5 correctness")
    expect(v["committedConditionalWrong"] <= v["committedConditionalPredictions"],
           f"{profile}/{workload}: impossible committed branch errors")
    expect(v["predictionMetadataChecks"] == v["committedConditionalPredictions"],
           f"{profile}/{workload}: snapshot accounting mismatch")
    expect(v["historyRestoreChecks"] == v["historyStateRestores"],
           f"{profile}/{workload}: rollback accounting mismatch")

    if is_p0:
        expect(all(v[k] == 0 for k in p1_keys),
               f"{profile}/{workload}: P1 activity on P0 configuration")
        reads, eligible, hits, overrides, fixes, breaks, writes, blocked = (
            v[k] for k in (
                "c3PcBiasBankReads", "c3PcBiasEligibleCommitted", "c3PcBiasTagHits",
                "c3PcBiasWouldFlip", "c3PcBiasWouldFix", "c3PcBiasWouldBreak",
                "c3PcBiasTrainWrites", "c3PcBiasCollisionBlocked",
            )
        )
        expect(0 <= overrides <= hits <= eligible <= reads,
               f"{profile}/{workload}: P0 read/hit/override invalid")
        expect(overrides == fixes + breaks,
               f"{profile}/{workload}: P0 fix/break conservation")
        expect(writes + blocked == eligible,
               f"{profile}/{workload}: P0 commit training conservation")
        expect(0 <= v["c3PcBiasEvictions"] <= v["c3PcBiasAllocations"] <= writes,
               f"{profile}/{workload}: P0 allocation accounting")
    elif is_p1:
        expect(all(v[k] == 0 for k in p0_keys),
               f"{profile}/{workload}: P0 activity on P1 configuration")
        reads, eligible, hits, disagreements, overrides, fixes, breaks = (
            v[k] for k in (
                "c3PcChooserReads", "c3PcChooserEligibleCommitted",
                "c3PcChooserTagHits", "c3PcChooserDisagreements",
                "c3PcChooserWouldOverride", "c3PcChooserWouldFix",
                "c3PcChooserWouldBreak",
            )
        )
        writes = v["c3PcChooserRowWrites"]
        updates = v["c3PcChooserDirectionUpdates"]
        chooses = v["c3PcChooserChooserUpdates"]
        alloc = v["c3PcChooserAllocations"]
        evict = v["c3PcChooserEvictions"]
        blocked = v["c3PcChooserCollisionBlocked"]
        stale = v["c3PcChooserStalePredictions"]
        expect(0 <= overrides <= disagreements <= hits <= eligible <= reads,
               f"{profile}/{workload}: P1 read/disagreement/override invalid")
        expect(overrides == fixes + breaks,
               f"{profile}/{workload}: P1 fix/break conservation")
        expect(writes == eligible and updates + alloc + blocked == eligible,
               f"{profile}/{workload}: P1 training accounting invalid")
        expect(0 <= chooses <= disagreements,
               f"{profile}/{workload}: chooser trained without disagreement")
        expect(0 <= stale <= eligible and 0 <= evict <= alloc <= writes,
               f"{profile}/{workload}: stale/eviction accounting invalid")
    else:
        expect(all(v[k] == 0 for k in p0_keys + p1_keys),
               f"{profile}/{workload}: auxiliary activity in G5/G7 baseline")
        reads = eligible = hits = overrides = fixes = breaks = 0
    potential = v["committedConditionalWrong"] - fixes + breaks
    expect(0 <= potential <= v["committedConditionalPredictions"],
           f"{profile}/{workload}: impossible shadow counterfactual error total")
    row = {k: v[k] for k in FIELDS if k in v}
    row.update(
        profile=profile, workload=workload,
        shadowNet=fixes - breaks, hypotheticalWrong=potential,
        hypotheticalMPKI=f"{1000.0 * potential / v['simInsts']:.9f}",
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
        "BPU-7 C3 P0/P1 SAME-BINARY SHADOW DIAGNOSTIC",
        "NOT M1 REAL FRONTEND CORRECTION; no actual cycle improvements attributed",
        f"ROI_CHECKED={len(rows)}/{count_expected}",
        "",
        "profile   ROI   G5wrong  wouldFix  wouldBreak       net  reads  storageBits",
    ]
    for p, rr in per_profile.items():
        p0 = p.startswith("p0_")
        p1 = p.startswith("p1_")
        key_fix = ("c3PcBiasWouldFix" if p0 else
                   "c3PcChooserWouldFix" if p1 else None)
        key_break = ("c3PcBiasWouldBreak" if p0 else
                     "c3PcChooserWouldBreak" if p1 else None)
        key_reads = ("c3PcBiasBankReads" if p0 else
                     "c3PcChooserReads" if p1 else None)
        lines.append(
            f"{p:9s} {len(rr):3d} "
            f"{sum(int(r['committedConditionalWrong']) for r in rr):9d} "
            f"{sum(int(r[key_fix]) for r in rr) if key_fix else 0:9d} "
            f"{sum(int(r[key_break]) for r in rr) if key_break else 0:11d} "
            f"{sum(int(r['shadowNet']) for r in rr):9d} "
            f"{sum(int(r[key_reads]) for r in rr) if key_reads else 0:6d} "
            f"{PROFILES[p][1]:11d}"
        )
    if len(rows) == count_expected:
        lines.append("")
        lines.append("RECONCILED_SUMMARY=YES; compare per-workload rows in results.csv")
        lines.append("Known P1 limitation: ABA same-PC reallocation still has no generation guard.")
    lines += [
        "All comparisons use G5-path shadow, first ROI dump per workload.",
        "BPU7_C3_P0_P1_SHADOW_ALL_COMPLETED=" +
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
                        default=ROOT / ("bpu_b7_c3_p0_p1_full19_" +
                                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    parser.add_argument("--resume", action="store_true",
                        help="Continue same --out, verifying manifest and completed row hashes")
    parser.add_argument("--list", action="store_true",
                        help="Print planned 152 jobs and exit without building/running")
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
    subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-Isrc", "tests/bpu7/c3_pc_chooser_directed.cc",
                    "-o", "/tmp/bpu_b7_c3_chooser_directed_full19"],
                   cwd=ROOT, check=True)
    subprocess.run(["/tmp/bpu_b7_c3_chooser_directed_full19"], check=True)
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
        "experiment": "BPU7_C3_P0_P1_SAME_BINARY_SHADOW_FULL19",
        "status": "SHADOW_DIAGNOSTIC_NOT_M1",
        "no_measured_real_correction": True,
        "aba_generation_guard": False,
        "study_scope": "P0_P1_8_PROFILE_COMPARISON_NOT_FROZEN_ROUND_I",
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
        if old != manifest:
            raise RuntimeError(
                "FAIL-CLOSED: immutable SHA256 manifest differs from current "
                "source, runner, gem5, config or Embench corpus. "
                "Keep original run and inspect differences before rerunning."
            )
        print("[2] Resume: exact manifest identity verified", flush=True)
    else:
        if out.exists():
            raise RuntimeError("Output directory already exists. Supply --resume or a new --out.")
        out.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    rows = []
    baseline = {}
    print(f"[3] {len(work)} workloads×profiles (19×8), SHADOW ONLY", flush=True)
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
            # Preserve fully executed ROI evidence and verify it in place
            # after a process interruption before .verified.json was written.
            with finished.open("x") as fv:
                fv.write(json.dumps(verification, indent=2) + "\n")
            print(f"  [{number:3d}/{len(work)}] "
                  f"{'RECOVER' if existing_raw else 'VERIFY'} "
                  f"{workload}/{profile}", flush=True)
        if profile == "g5":
            baseline[workload] = row
        elif profile.startswith(("p0_", "p1_")):
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
        if profile == "p1_e256" or number == len(work):
            emit_summary(out, rows, len(work))
    emit_summary(out, rows, len(work))
    print("\nRESULT_FILES:")
    for name in ("manifest.json", "results.csv", "summary.txt"):
        print(out / name)
    print("PASS = same-binary P0/P1 shadow functional and accounting pass ONLY")
    print("DO NOT REPORT P0/P1 shadow fixes or ticks as actual M1 improvements")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"\nBPU7_C3_P0_P1_SHADOW_FAIL_CLOSED: {exc}", file=sys.stderr)
        sys.exit(1)
