#!/usr/bin/env python3
"""BPU-8 R2A controlled 7-bank capacity paths, Full-19 first ROI; no C3/M1.

Preserves every raw successful or failed gem5 run. An existing output directory
may ONLY be revisited with --resume and exact source/binary/runner identity.
No existing BPU-4/BPU-7 freeze or 21-profile R1 matrix is modified.
"""
import argparse
import csv
import configparser
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MATRIX_FILE = ROOT / "docs/bpu8_r2a_capacity_knee_v01.json"
R1_MATRIX_FILE = ROOT / "docs/bpu8_tage_isobit_r1.json"
CONFIG_FILE = ROOT / "configs/02_little_v052_rv64_proxy.py"
BASE_FIELDS = ("simTicks", "simInsts", "committedConditionalPredictions",
               "committedConditionalWrong", "finalConditionalWrong",
               "predictionMetadataChecks", "historyRestoreChecks",
               "historyStateRestores", "storageBits", "taggedStorageBits",
               "bimodalStorageBits", "historyStorageBits", "otherStorageBits")
CSV_FIELDS = ("profile", "workload", *BASE_FIELDS, "mpki", "roi_sha256")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fd:
        for block in iter(lambda: fd.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True,
                                   stderr=subprocess.PIPE).strip()


def load_matrix(path=MATRIX_FILE):
    matrix = json.loads(Path(path).read_text())
    r1 = json.loads(R1_MATRIX_FILE.read_text())
    if matrix.get("experiment") != "BPU8_R2A_CAPACITY_KNEE_V01" or (
            matrix.get("status") != "PRE_REGISTERED_NOT_RUN"):
        raise ValueError("invalid R2A preregistration header")
    if matrix.get("from_r1_commit") != "6aeed4f092c86f8c3b25654cf71f9398457bdc06":
        raise ValueError("R1 source baseline changed")
    if (matrix.get("workloads") != r1["workloads"] or
            len(matrix["workloads"]) != 19 or
            len(set(matrix["workloads"])) != 19 or
            matrix["frontend"] != r1["frontend"]):
        raise ValueError("workload/frontend mismatch with frozen R1")
    p = matrix["profiles"]
    if len(p) != 11 or set(p) != {
            "r2a_dn43", "r2a_ref45", "r2a_sh49", "r2a_lg49",
            "r2a_both52", "r2a_mid60", "r2a_long60",
            "tg7_50", "tg5_45", "stock", "g7"}:
        raise ValueError("R2A exactly 11 profiles required")
    for ref in ("tg7_50", "tg5_45", "stock", "g7"):
        if p[ref] != r1["profiles"][ref]:
            raise ValueError("frozen R1 control mismatch: " + ref)
    if (matrix["method"]["tag_widths_fixed_for_seven_banks"] !=
            [8, 8, 9, 9, 9, 10, 10] or
            matrix["method"]["history_lengths_fixed_for_seven_banks"] !=
            [5, 9, 15, 25, 44, 76, 130] or
            matrix["method"]["hash_log_size"] != 0):
        raise ValueError("R2A seven-bank identity or index mode changed")
    entry_options = {
        "r2a_dn43": ([256, 512, 512, 512, 512, 512, 128], 43816),
        "r2a_ref45": ([256, 512, 512, 512, 512, 512, 256], 45736),
        "r2a_sh49": ([512, 512, 512, 512, 512, 512, 256], 49064),
        "r2a_lg49": ([256, 512, 512, 512, 512, 512, 512], 49576),
        "r2a_both52": ([512, 512, 512, 512, 512, 512, 512], 52904),
        "r2a_mid60": ([512, 512, 512, 1024, 512, 512, 512], 60072),
        "r2a_long60": ([512, 512, 512, 512, 512, 1024, 512], 60584),
    }
    if p["r2a_ref45"] != dict(r1["profiles"]["tg7_45"],
            bp_type="tage-geo-tg7-45"):
        raise ValueError("reference TG7-45 geometry mismatch")
    seen_types = set()
    for profile, (entries, bits) in entry_options.items():
        val = p[profile]
        want = "tage-geo-tg7-45" if profile == "r2a_ref45" else (
            "tage-r2a-" + profile.replace("_", "-"))
        if (val["bp_type"] != want or val["entries"] != entries or
                val["tag_bits"] != [8, 8, 9, 9, 9, 10, 10] or
                val["histories"] != [5, 9, 15, 25, 44, 76, 130] or
                val["base_entries"] != 2048 or
                val["total_bits"] != bits or
                not all(x > 0 and x & (x - 1) == 0 for x in entries)):
            raise ValueError("R2A preregistered geometry drift: " + profile)
        actual = 2728 + sum(e * (5 + t) for e, t in
                            zip(val["entries"], val["tag_bits"]))
        if actual != val["total_bits"]:
            raise ValueError("R2A storage budget mismatch: " + profile)
        seen_types.add(want)
    expected_pairs = [
        ("r2a_dn43", "r2a_ref45"),
        ("r2a_ref45", "r2a_sh49"),
        ("r2a_ref45", "r2a_lg49"),
        ("r2a_lg49", "tg7_50"),
        ("r2a_sh49", "r2a_both52"),
        ("r2a_lg49", "r2a_both52"),
        ("r2a_both52", "r2a_mid60"),
        ("r2a_both52", "r2a_long60"),
    ]
    if [(e["from"], e["to"]) for e in matrix["paired_comparisons"]] != expected_pairs:
        raise ValueError("R2A predeclared pairwise comparisons changed")
    return matrix


def unique_int(stats, name):
    hits = [v for k, v in stats.items() if k == name or k.endswith("." + name)]
    if len(hits) != 1:
        raise ValueError(f"expected exactly one {name}; found {len(hits)}")
    try:
        val = Decimal(hits[0])
    except InvalidOperation as e:
        raise ValueError(f"invalid numeric {name}={hits[0]}") from e
    if not val.is_finite() or val != int(val):
        raise ValueError(f"non-integer {name}={hits[0]}")
    return int(val)


def parse_first_roi(path):
    lines = Path(path).read_text().splitlines(keepends=True)
    begin = "---------- Begin Simulation Statistics"
    end = "---------- End Simulation Statistics"
    starts = [i for i, x in enumerate(lines) if x.startswith(begin)]
    if not starts:
        raise ValueError("missing gem5 begin-stats marker: " + str(path))
    first = starts[0]
    ends = [i for i in range(first + 1, len(lines))
            if lines[i].startswith(end)]
    if not ends or any(i < ends[0] for i in starts[1:]):
        raise ValueError("incomplete/overlapping first ROI: " + str(path))
    last = ends[0]
    stats = {}
    for line in lines[first + 1:last]:
        words = line.split()
        if len(words) < 2:
            continue
        try:
            Decimal(words[1])
        except InvalidOperation:
            continue
        if words[0] in stats:
            raise ValueError("duplicate ROI metric: " + words[0])
        stats[words[0]] = words[1]
    if not stats:
        raise ValueError("empty first ROI")
    return stats, "".join(lines[first:last + 1])



def validate_gem5_config(path, profile, profiles):
    """Independently check the instantiated SimObject geometry for every run."""
    ini = configparser.ConfigParser(interpolation=None, strict=True)
    if not ini.read(path):
        raise ValueError("missing gem5 instantiated config.ini: " + str(path))
    sections = [section for section in ini.sections()
                if section.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(sections) != 1:
        raise ValueError(f"exactly one instantiated TAGE section required: {sections}")
    x = ini[sections[0]]
    if profile == "stock":
        base, entries = 8192, [512] * 7
        tags = [9, 9, 10, 10, 11, 11, 12]
        hist = [5, 9, 15, 25, 44, 76, 130]
    elif profile == "g7":
        base, entries = 2048, [512, 512, 512, 1024, 512, 512, 512]
        tags = [9, 9, 10, 10, 11, 11, 12]
        hist = [5, 9, 15, 25, 44, 76, 130]
    else:
        z = profiles[profile]
        base, entries, tags, hist = (
            z["base_entries"], z["entries"], z["tag_bits"], z["histories"])
    expected = {
        "nHistoryTables": str(len(entries)),
        "maxHist": str(hist[-1]), "minHist": str(hist[0]),
        "logTagTableSizes": " ".join(map(str, [base.bit_length()-1] +
                                               [e.bit_length()-1 for e in entries])),
        "tagTableTagWidths": " ".join(map(str, [0] + tags)),
        "explicitHistLengths": " ".join(map(str, hist)) if profile != "stock" else "",
        "tagTableCounterBits": "3", "tagTableUBits": "2",
        "logRatioBiModalHystEntries": "2", "maxNumAlloc": "1",
        "pathHistBits": "16", "fixedIndexHashLogSize": "0",
        "speculativeHistUpdate": "true", "perceptronEnabled": "false",
        "instShiftAmt": "1",
    }
    # Stock TAGE gem5 derives its geometric histories rather than setting
    # explicitHistLengths, so its raw list is empty, as in frozen R1.
    for key, value in expected.items():
        got = x.get(key)
        if got != value:
            raise ValueError(
                f"{profile}: instantiated {key}={got!r}, expected {value!r}")
    return True


def inspect_row(stats, profile, workload, expected_bits, roi_sha):
    v = {k: unique_int(stats, k) for k in BASE_FIELDS}
    if v["storageBits"] != expected_bits:
        raise ValueError(f"{workload}/{profile}: storageBits {v['storageBits']} != {expected_bits}")
    subtotal = sum(v[k] for k in ("taggedStorageBits", "bimodalStorageBits",
                                  "historyStorageBits", "otherStorageBits"))
    if subtotal != expected_bits:
        raise ValueError(f"{workload}/{profile}: sub-bank storage sum {subtotal} != {expected_bits}")
    if v["bimodalStorageBits"] != (10240 if profile == "stock" else 2560):
        raise ValueError("bimodal size violates geometry contract")
    if v["historyStorageBits"] != 146 or v["otherStorageBits"] != 22:
        raise ValueError("history / other state differs from pinned contract")
    if (v["simTicks"] <= 0 or v["simInsts"] <= 0
            or v["committedConditionalPredictions"] <= 0
            or not 0 <= v["committedConditionalWrong"] <= v["committedConditionalPredictions"]):
        raise ValueError("empty/impossible committed branch metrics")
    if v["committedConditionalWrong"] != v["finalConditionalWrong"]:
        raise ValueError("TAGE-only direction is unexpectedly being corrected")
    if v["predictionMetadataChecks"] != v["committedConditionalPredictions"]:
        raise ValueError("missing metadata validation")
    if v["historyRestoreChecks"] != v["historyStateRestores"]:
        raise ValueError("speculative-history rollback accounting failure")
    return dict(profile=profile, workload=workload, **v,
                mpki=f"{v['committedConditionalWrong']*1000/v['simInsts']:.9f}",
                roi_sha256=roi_sha)


def write_csv(out, rows):
    with (out / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def summarize(out, rows, profiles, workloads, expected):
    d = {(r["profile"], r["workload"]): r for r in rows}
    lines = ["BPU-8 R2A EXACT-STATE CAPACITY PATHS — FIRST-ROI ACTUAL FRONTEND",
             f"ROI_CHECKED={len(rows)}/{expected}"]
    lines.append("profile      valid  bits    geomeanTicks/G5  geomeanTicks/G7  W/L/T_vs_G5    worst_vs_G5")
    if all(("tg5_45", w) in d for w in workloads):
        for p in profiles:
            rr = [w for w in workloads if (p, w) in d]
            if not rr:
                continue
            ratios = [d[p, w]["simTicks"]/d["tg5_45", w]["simTicks"]
                      for w in rr if ("tg5_45", w) in d]
            ratios7 = [d[p, w]["simTicks"]/d["g7", w]["simTicks"]
                       for w in rr if ("g7", w) in d]
            if not ratios:
                continue
            gm = math.exp(sum(math.log(x) for x in ratios)/len(ratios))
            gm7 = (math.exp(sum(math.log(x) for x in ratios7)/len(ratios7))
                   if ratios7 else float("nan"))
            wins = sum(x < 1 for x in ratios)
            losses = sum(x > 1 for x in ratios)
            ties = len(ratios)-wins-losses
            lines.append(f"{p:12s} {len(rr):3d} {profiles[p]['total_bits']:6d} "
                         f"{gm:.9f} {gm7:.9f} {wins}/{losses}/{ties} "
                         f"{(max(ratios)-1)*100:+.5f}%")
    if len(rows) == expected:
        matrix = load_matrix()
        lines.extend(("", "R2A PREDECLARED PAIRED EDGES (negative ticks = improvement)",
                      "from         to            extraBits   GM Δticks%   GM Δticks%/KiB  W/L/T"))
        for edge in matrix["paired_comparisons"]:
            parent, child = edge["from"], edge["to"]
            delta = profiles[child]["total_bits"] - profiles[parent]["total_bits"]
            if delta <= 0:
                raise ValueError("R2A edge must have positive incremental state")
            ratios = [d[child, w]["simTicks"]/d[parent, w]["simTicks"]
                      for w in workloads]
            rate = (math.exp(sum(math.log(x) for x in ratios)/len(ratios))-1)*100
            wins = sum(x < 1 for x in ratios)
            losses = sum(x > 1 for x in ratios)
            lines.append(f"{parent:12s} {child:12s} {delta:7d} "
                         f"{rate:+.6f}% {rate/(delta/8192):+.6f} "
                         f"{wins}/{losses}/{len(ratios)-wins-losses}")
    if len(rows) == expected:
        lines.append("BPU8_R2A_CAPACITY_FULL19=PASS" if len(workloads) == 19 else
                     "BPU8_R2A_CAPACITY_SMOKE=PASS")
    else:
        lines.append("BPU8_TAGE_ISOBIT=INCOMPLETE")
    (out / "summary.txt").write_text("\n".join(lines)+"\n")
    print("\n".join(lines), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--prepare-if-missing", action="store_true")
    ap.add_argument("--gem5", type=Path, default=ROOT/"build/RISCV/gem5.opt")
    ap.add_argument("--embench-build", type=Path,
                    default=ROOT/"benchmarks/external/embench-iot/bd-rv64-gem5")
    ap.add_argument("--out", type=Path, default=ROOT/("bpu8_r2a_capacity_"+
                    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="only huffbench and qrduino; never mislabel as Full-19")
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error("--jobs must be positive")
    matrix = load_matrix()
    workloads = ("huffbench", "qrduino") if args.smoke else tuple(matrix["workloads"])
    profiles = matrix["profiles"]
    # Each workload's canonical G5 must be verified BEFORE a different
    # geometry is allowed to compare committed instructions against it.
    # Dict registry order is editorial, never a runnable dependency order.
    run_order = ("tg5_45",) + tuple(p for p in profiles if p != "tg5_45")
    jobs = [(p, w) for w in workloads for p in run_order]
    if args.list:
        # Print the exact executable job order, not the editorial registry order.
        for p, w in jobs:
            print(f"{p:12s} {w}")
        print(f"BPU8_R2A_JOBS_PLANNED={len(jobs)} FULL19={not args.smoke}")
        return

    out, gem5, build = args.out.resolve(), args.gem5.resolve(), args.embench_build.resolve()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("refuse to run with dirty tracked repository content")
    if not args.no_build:
        print("[0] Build pinned BPU-8 gem5.opt", flush=True)
        subprocess.run(["scons", "build/RISCV/gem5.opt", "--ignore-style",
                        f"-j{args.jobs}"], check=True, cwd=ROOT)
    if not gem5.is_file():
        raise RuntimeError("gem5 missing " + str(gem5))
    bins = {w: build/"src"/w/w for w in workloads}
    missing = [w for w in workloads if not bins[w].is_file()]
    if missing and args.prepare_if_missing:
        env = os.environ.copy()
        env.update(JOBS=str(args.jobs), EMBENCH_BUILD=str(build),
                   EMBENCH_DIR=str(build.parent))
        subprocess.run(["bash", "scripts/rv64_embench_prepare.sh"],
                       cwd=ROOT, env=env, check=True)
        missing = [w for w in workloads if not bins[w].is_file()]
    if missing:
        raise RuntimeError("missing pinned RV64 Embench binaries: " + str(missing))
    source_dir = build.parent
    embhead = (git("rev-parse", "HEAD", cwd=source_dir)
               if (source_dir/".git").exists() else "NO_GIT_METADATA")
    manifest = dict(experiment="BPU8_R2A_CAPACITY_KNEE_V01",
        status="ACTUAL_TAGE_ONLY_FIRST_ROI_NOT_RTL_PPA",
        scope="SMOKE_2_SELECTED_BENCHMARKS_NOT_FULL19" if args.smoke else "FULL19_DEVELOPMENT_CORPUS",
        repo_head=git("rev-parse", "HEAD"), repo_clean=True,
        gem5_sha256=sha(gem5), config_sha256=sha(CONFIG_FILE),
        runner_sha256=sha(Path(__file__)), matrix_sha256=sha(MATRIX_FILE), r1_matrix_sha256=sha(R1_MATRIX_FILE),
        embench_head=embhead, benchmarks={w:sha(p) for w,p in bins.items()},
        profiles=profiles, workloads=workloads, job_count=len(jobs),
        frontend=matrix["frontend"])
    mf = out/"manifest.json"
    if args.resume:
        if not mf.is_file() or json.loads(mf.read_text()) != json.loads(
                json.dumps(manifest)):
            raise RuntimeError("resume refused: exact manifest/input hashes differ")
    else:
        if out.exists():
            raise RuntimeError("output already exists; use --resume or new --out")
        out.mkdir(parents=True)
        mf.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")

    print(f"[1] BPU8 R2A {len(jobs)} actual TAGE first-ROI jobs; smoke={args.smoke}",
          flush=True)
    rows = []
    g5_by_w = {}
    for i,(p,w) in enumerate(jobs,1):
        bp = profiles[p]["bp_type"]
        folder = out/p/w
        cmd = [str(gem5), f"--outdir={folder}", str(CONFIG_FILE),
               "--binary", str(bins[w]), "--bp-type", bp,
               "--bp-inst-shift", "1", "--bp-cond-shift", "1",
               "--bp-btb-shift", "2", "--bp-indirect-shift", "1",
               "--btb-entries", "4096"]
        existing = folder.exists()
        if existing and not args.resume:
            raise RuntimeError("existing raw folder without --resume: " + str(folder))
        if not existing:
            folder.mkdir(parents=True)
            (folder/"command.json").write_text(json.dumps(cmd,indent=2)+"\n")
            with (folder/"stdout.txt").open("x") as stdout, (
                    folder/"stderr.txt").open("x") as stderr:
                rc = subprocess.run(cmd, cwd=ROOT, stdout=stdout,
                                    stderr=stderr).returncode
            (folder/"returncode.txt").write_text(str(rc)+"\n")
            if rc:
                raise RuntimeError(f"{p}/{w}: gem5 exited {rc}; raw retained")
        elif not (folder/"returncode.txt").is_file():
            raise RuntimeError(f"{p}/{w}: incomplete previous run; raw retained, inspect")
        if (int((folder/"returncode.txt").read_text()) != 0
                or json.loads((folder/"command.json").read_text()) != cmd
                or not (folder/"stats.txt").is_file()
                or "SIMULATION_EXIT_CODE=0" not in
                    (folder/"stdout.txt").read_text()):
            raise RuntimeError(f"{p}/{w}: failed exit, command or ROI raw verification")
        validate_gem5_config(folder/"config.ini", p, profiles)
        stats, roi = parse_first_roi(folder/"stats.txt")
        roi_path = folder/"roi.stats"
        if roi_path.exists():
            if roi_path.read_text() != roi:
                raise RuntimeError("old roi.stats differs from immutable stats.txt")
        else:
            with roi_path.open("x") as fh:
                fh.write(roi)
        row = inspect_row(stats,p,w,profiles[p]["total_bits"],sha(roi_path))
        snap = dict(row=row, gem5_sha256=manifest["gem5_sha256"],
                    binary_sha256=manifest["benchmarks"][w])
        proof = folder/".verified.json"
        if proof.exists():
            if json.loads(proof.read_text()) != snap:
                raise RuntimeError(f"{p}/{w}: verified raw result changed")
        else:
            with proof.open("x") as f:
                f.write(json.dumps(snap,sort_keys=True,indent=2)+"\n")
        if p == "tg5_45":
            g5_by_w[w] = row
        else:
            if row["simInsts"] != g5_by_w[w]["simInsts"]:
                raise RuntimeError(f"{p}/{w}: committed inst mismatch vs G5")
        rows.append(row)
        write_csv(out,rows)
        print(f"  [{i:3d}/{len(jobs)}] {p:8s} {w:18s} "
              f"ticks={row['simTicks']} wrong={row['committedConditionalWrong']} "
              f"bits={row['storageBits']}",flush=True)
    summarize(out,rows,profiles,workloads,len(jobs))
    print("BPU8_R2A_ACTUAL_FRONTEND_ROI_REPRO=PASS",flush=True)
    print("NO CLAIM: independent workload holdout or physical RTL/PPA",flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            OSError, KeyError) as ex:
        print(f"BPU8_R2A_CAPACITY_FAIL_CLOSED: {ex}",file=sys.stderr)
        sys.exit(1)
