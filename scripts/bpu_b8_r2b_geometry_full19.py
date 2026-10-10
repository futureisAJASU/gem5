#!/usr/bin/env python3
"""BPU-8 R2B exact-budget 5/6/7-bank geometry frontier, Full-19 first ROI.

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
MATRIX_FILE = ROOT / "docs/bpu8_r2b_geometry_frontier_v01.json"
R1_MATRIX_FILE = ROOT / "docs/bpu8_tage_isobit_r1.json"
R2A_MATRIX_FILE = ROOT / "docs/bpu8_r2a_capacity_knee_v01.json"
PINNED_GEM5_SHA = "96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced"
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
    r2a = json.loads(R2A_MATRIX_FILE.read_text())
    if (matrix.get("experiment") != "BPU8_R2B_GEOMETRY_FRONTIER_V01"
            or matrix.get("status") != "PRE_REGISTERED_NOT_RUN"
            or matrix.get("base_commit") !=
                "774a296ae0309a45acff8643227b0c28d1cf8ab7"):
        raise ValueError("invalid R2B pre-result source contract")
    if (matrix.get("workloads") != r1["workloads"]
            or len(matrix["workloads"]) != 19
            or len(set(matrix["workloads"])) != 19
            or matrix.get("frontend") != r1["frontend"]):
        raise ValueError("R2B Full19 workload/frontend changed")
    profiles = matrix["profiles"]
    original = {
        "tg5_50": r1["profiles"]["tg5_50"],
        "tg6_50": r1["profiles"]["tg6_50"],
        "tg7_50": r1["profiles"]["tg7_50"],
        "r2a_both52": r2a["profiles"]["r2a_both52"],
        "r2a_mid60": r2a["profiles"]["r2a_mid60"],
        "tg5_45": r1["profiles"]["tg5_45"],
        "stock": r1["profiles"]["stock"],
        "g7": r1["profiles"]["g7"],
    }
    fixed = {
        "r2b_5a_53": (52904,[256,1024,1024,256,1024]),
        "r2b_5b_53": (52904,[512,1024,512,512,1024]),
        "r2b_6a_53": (52904,[256,1024,512,512,256,1024]),
        "r2b_6b_53": (52904,[512,512,1024,512,512,512]),
        "r2b_5a_60": (60072,[512,1024,1024,512,1024]),
        "r2b_5b_60": (60072,[512,512,2048,512,512]),
        "r2b_6a_60": (60072,[512,1024,512,512,512,1024]),
        "r2b_6b_60": (60072,[256,1024,1024,512,256,1024]),
    }
    if len(profiles) != 16 or set(profiles) != set(original) | set(fixed):
        raise ValueError("R2B requires exactly 16 preregistered profiles")
    for name, canonical in original.items():
        if profiles[name] != canonical:
            raise ValueError("R1/R2A original control drift: " + name)
    for name, (target, entries) in fixed.items():
        p = profiles[name]
        depth = len(entries)
        if depth == 5:
            tags, histories = [8,8,9,10,10], [5,11,25,58,130]
        else:
            tags, histories = [8,8,9,9,10,10], [5,10,20,39,75,130]
        computed = 2728 + sum(
            e*(5+t) for e,t in zip(entries,tags))
        if (p.get("bp_type") != "tage-r2b-"+name.replace("_","-")
                or p.get("base_entries") != 2048
                or p.get("entries") != entries
                or p.get("tag_bits") != tags
                or p.get("histories") != histories
                or p.get("total_bits") != target
                or computed != target
                or not all(e > 0 and e & (e-1) == 0 for e in entries)):
            raise ValueError("R2B fixed exact-bit geometry changed: " + name)
    expected_tiers = {
        "B50_50088": (50088, "tg7_50", ["tg5_50","tg6_50"]),
        "B53_52904": (52904, "r2a_both52",
            ["r2b_5a_53","r2b_5b_53","r2b_6a_53","r2b_6b_53"]),
        "B60_60072": (60072, "r2a_mid60",
            ["r2b_5a_60","r2b_5b_60","r2b_6a_60","r2b_6b_60"]),
    }
    pairs = []
    for name, (bits, ref, others) in expected_tiers.items():
        if matrix["tiers"].get(name) != dict(
                bits=bits,reference=ref,comparators=others):
            raise ValueError("R2B preregistered budget tier changed: " + name)
        if any(profiles[p]["total_bits"] != bits for p in [ref]+others):
            raise ValueError("R2B not truly iso-bit: " + name)
        pairs.extend((name,ref,p,True) for p in others)
    for tier,ref,p in [
        ("B53_52904","r2b_5a_53","r2b_5b_53"),
        ("B53_52904","r2b_6a_53","r2b_6b_53"),
        ("B60_60072","r2b_5a_60","r2b_5b_60"),
        ("B60_60072","r2b_6a_60","r2b_6b_60"),
    ]:
        pairs.append((tier,ref,p,True))
    if (len(matrix["paired_comparisons"]) != 14 or
            [(x["tier"],x["reference"],x["candidate"],x["same_budget"])
             for x in matrix["paired_comparisons"]] != pairs):
        raise ValueError("R2B paired iso-bit comparisons changed")
    if (matrix["method"]["capacity_budgets_bits"] !=
            [50088,52904,60072] or
            matrix["method"]["base_bimodal_entries"] != 2048 or
            matrix["method"]["logical_fixed_bits"] != 2728):
        raise ValueError("R2B fixed budget framing changed")
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


def summarize(out,rows,profiles,workloads,expected):
    d = {(r["profile"],r["workload"]): r for r in rows}
    lines = ["BPU-8 R2B EXACT-ISO 5/6/7-TABLE FRONTIER — FIRST-ROI ACTUAL FRONTEND",
             f"ROI_CHECKED={len(rows)}/{expected}",
             "profile      valid   bits    geomeanTicks/G5 geomeanTicks/G7 W/L/T_vs_G5 worst_vs_G5"]
    if all(("tg5_45",w) in d for w in workloads):
        for p in profiles:
            ratios = [d[p,w]["simTicks"]/d["tg5_45",w]["simTicks"]
                      for w in workloads if (p,w) in d]
            r7 = [d[p,w]["simTicks"]/d["g7",w]["simTicks"]
                  for w in workloads if (p,w) in d]
            if not ratios:
                continue
            gm = math.exp(sum(math.log(x) for x in ratios)/len(ratios))
            gm7 = math.exp(sum(math.log(x) for x in r7)/len(r7))
            wins = sum(x<1 for x in ratios)
            loss = sum(x>1 for x in ratios)
            lines.append(f"{p:12s} {len(ratios):3d} {profiles[p]['total_bits']:7d} "
                         f"{gm:.9f} {gm7:.9f} "
                         f"{wins}/{loss}/{len(ratios)-wins-loss} "
                         f"{(max(ratios)-1)*100:+.5f}%")
    if len(rows) == expected:
        mat = load_matrix()
        lines.extend(("", "R2B PREDECLARED EXACT-ISO BUDGET COMPARISONS",
                      "tier           reference      candidate      GM Δticks% W/L/T  worstΔ%"))
        for spec in mat["paired_comparisons"]:
            group,ref,p=spec["tier"],spec["reference"],spec["candidate"]
            if profiles[ref]["total_bits"] != profiles[p]["total_bits"]:
                raise ValueError("iso-budget violation: "+group)
            v = [d[p,w]["simTicks"]/d[ref,w]["simTicks"] for w in workloads]
            gm = math.exp(sum(math.log(x) for x in v)/len(v))
            wins=sum(x<1 for x in v)
            losses=sum(x>1 for x in v)
            lines.append(f"{group:14s} {ref:14s} {p:14s} "
                         f"{(gm-1)*100:+.6f}% "
                         f"{wins}/{losses}/{len(v)-wins-losses} "
                         f"{(max(v)-1)*100:+.5f}%")
        lines.append("BPU8_R2B_GEOMETRY_FULL19=PASS" if len(workloads)==19
                     else "BPU8_R2B_GEOMETRY_SMOKE=PASS")
    else:
        lines.append("BPU8_R2B_GEOMETRY=INCOMPLETE")
    (out/"summary.txt").write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--prepare-if-missing", action="store_true")
    ap.add_argument("--gem5", type=Path, default=ROOT/"build/RISCV/gem5.opt")
    ap.add_argument("--embench-build", type=Path,
                    default=ROOT/"benchmarks/external/embench-iot/bd-rv64-gem5")
    ap.add_argument("--out", type=Path, default=ROOT/("bpu8_r2b_geometry_"+
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
        print(f"BPU8_R2B_JOBS_PLANNED={len(jobs)} FULL19={not args.smoke}")
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
    if sha(gem5) != PINNED_GEM5_SHA:
        raise RuntimeError("R2B needs EXACT R1/R2A gem5.opt SHA256: "
                           + PINNED_GEM5_SHA + "; got " + sha(gem5))
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
    manifest = dict(experiment="BPU8_R2B_GEOMETRY_FRONTIER_V01",
        status="ACTUAL_TAGE_ONLY_FIRST_ROI_NOT_RTL_PPA",
        scope="SMOKE_2_SELECTED_BENCHMARKS_NOT_FULL19" if args.smoke else "FULL19_DEVELOPMENT_CORPUS",
        repo_head=git("rev-parse", "HEAD"), repo_clean=True,
        gem5_sha256=sha(gem5), config_sha256=sha(CONFIG_FILE),
        runner_sha256=sha(Path(__file__)), matrix_sha256=sha(MATRIX_FILE), r1_matrix_sha256=sha(R1_MATRIX_FILE),
        r2a_matrix_sha256=sha(R2A_MATRIX_FILE),
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

    print(f"[1] BPU8 R2B {len(jobs)} actual TAGE first-ROI jobs; smoke={args.smoke}",
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
    print("BPU8_R2B_ACTUAL_FRONTEND_ROI_REPRO=PASS",flush=True)
    print("NO CLAIM: independent workload holdout or physical RTL/PPA",flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            OSError, KeyError) as ex:
        print(f"BPU8_R2B_GEOMETRY_FAIL_CLOSED: {ex}",file=sys.stderr)
        sys.exit(1)
