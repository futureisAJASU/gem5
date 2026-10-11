#!/usr/bin/env python3
"""BPU-8 R3 G5-lock native-hash x bank-count experiment; opt-in R3B cause counters.

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
MATRIX_FILE = ROOT / "docs/bpu8_r3_g5_lock_v01.json"
R1_MATRIX_FILE = ROOT / "docs/bpu8_tage_isobit_r1.json"
CONFIG_FILE = ROOT / "configs/02_little_v052_rv64_proxy.py"
BASE_FIELDS = ("simTicks", "simInsts", "committedConditionalPredictions",
               "committedConditionalWrong", "finalConditionalWrong",
               "predictionMetadataChecks", "historyRestoreChecks",
               "historyStateRestores", "storageBits", "taggedStorageBits",
               "bimodalStorageBits", "historyStorageBits", "otherStorageBits")
DIAG_SCALARS = ("r3PseudoNewAlloc", "r3AlternateDisagreements",
                "r3AlternateWouldFix", "r3AllocAttempts", "r3Allocations",
                "r3ForcedUsefulClears")
DIAG_VECTORS = ("r3HitBank", "r3HitBankWrong", "r3SelectedBankWrong",
                "r3AltBank", "r3AllocByBank")
CSV_FIELDS = ("profile", "workload", *BASE_FIELDS, *DIAG_SCALARS,
              "r3CauseJson", "mpki", "roi_sha256")


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
    m = json.loads(Path(path).read_text())
    r1 = json.loads(R1_MATRIX_FILE.read_text())
    if (m.get("experiment") != "BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01"
            or m.get("status") != "PRE_REGISTERED_NOT_RUN"
            or m.get("parent_source_commit") != "883d685d31dc026a0e7a30d201c00abdc9c2bd68"
            or m["workloads"] != r1["workloads"]
            or m["frontend"] != r1["frontend"]):
        raise ValueError("R3 preregistered identity/workloads/frontend drift")
    names = ("g5_native", "g5_h11", "tg6_native", "tg6_h11",
             "tg7_native", "tg7_h11")
    if (list(m["profiles"]) != list(names)
            or m["expected_full19_jobs"] != 114
            or m["expected_smoke_jobs"] != 12
            or m["smoke_workloads"] != ["huffbench", "qrduino"]):
        raise ValueError("R3 fixed 6-profile/19-workload factorial mutated")
    for name in names:
        p = m["profiles"][name]
        source = {"g5":"tg5_45", "tg6":"tg6_45",
                  "tg7":"tg7_45"}[name.split("_")[0]]
        expected = dict(r1["profiles"][source],
            source_profile=source,
            bp_type="tage-r3-" + ("h11" if name.endswith("h11") else "native")
                    + "-" + source.replace("_", "-"),
            fixed_index_hash_log_size=11 if name.endswith("h11") else 0,
            r3_diagnostics=True)
        if p != expected or p["total_bits"] != 45736:
            raise ValueError("R3 exact geometry/hash or diagnostics drift: " + name)
        if (2560 + 146 + 22 +
                sum(e * (t+5) for e,t in zip(p["entries"],p["tag_bits"]))
                != 45736):
            raise ValueError("R3 physical tagged geometry logical bit budget invalid")
    cmp_expected = {"native_fixed":[["g5_native","g5_h11"],
                                    ["tg6_native","tg6_h11"],
                                    ["tg7_native","tg7_h11"]],
                    "same_hash":[["g5_native","tg6_native"],
                                 ["g5_native","tg7_native"],
                                 ["g5_h11","tg6_h11"],
                                 ["g5_h11","tg7_h11"]]}
    if m["comparisons"] != cmp_expected:
        raise ValueError("R3 registered comparisons mutated")
    return m

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


def vector_values(stats, name, n):
    values = []
    for i in range(n+1):
        suffix = f".{name}::{i}"
        hits = [v for k,v in stats.items() if k.endswith(suffix)]
        if len(hits) != 1:
            raise ValueError(f"expected one ROI vector {suffix}; found {len(hits)}")
        d = Decimal(hits[0])
        if not d.is_finite() or d != int(d) or int(d) < 0:
            raise ValueError("invalid R3 vector count: "+suffix)
        values.append(int(d))
    return values


def validate_r3_ini(path, profile, profiles):
    ini = configparser.ConfigParser(interpolation=None, strict=True)
    if not ini.read(path):
        raise ValueError("missing config.ini")
    sections = [x for x in ini.sections()
                if x.endswith(".branchPred.conditionalBranchPred.tage")]
    if len(sections) != 1:
        raise ValueError("expected exactly one active TAGE SimObject section")
    z = profiles[profile]
    x = ini[sections[0]]
    expected = {
        "nHistoryTables":str(len(z["entries"])),
        "maxHist":"130", "minHist":"5",
        "logTagTableSizes":" ".join(str(v.bit_length()-1)
                        for v in [2048]+z["entries"]),
        "tagTableTagWidths":" ".join(str(v) for v in [0]+z["tag_bits"]),
        "explicitHistLengths":" ".join(str(v) for v in z["histories"]),
        "tagTableCounterBits":"3", "tagTableUBits":"2",
        "logRatioBiModalHystEntries":"2",
        "maxNumAlloc":"1", "pathHistBits":"16",
        "fixedIndexHashLogSize":str(z["fixed_index_hash_log_size"]),
        "speculativeHistUpdate":"true", "perceptronEnabled":"false",
        "r3TageDiagnosticsEnabled":"true", "instShiftAmt":"1"
    }
    for key,value in expected.items():
        if x.get(key) != value:
            raise ValueError(f"{profile}: {key}: instantiated {x.get(key)!r} != {value!r}")
    return True


def inspect_row(stats, profile, workload, geo, roi_sha):
    v = {k:unique_int(stats,k) for k in BASE_FIELDS}
    pbits = geo["total_bits"]
    if v["storageBits"] != pbits or sum(v[k] for k in
            ("taggedStorageBits","bimodalStorageBits",
             "historyStorageBits","otherStorageBits")) != pbits:
        raise ValueError("R3 persistent state bit accounting mismatch")
    if (v["bimodalStorageBits"] != 2560 or
            v["historyStorageBits"] != 146 or
            v["otherStorageBits"] != 22):
        raise ValueError("R3 non-tagged state budget mismatch")
    total,wrong=v["committedConditionalPredictions"],v["committedConditionalWrong"]
    if (v["simTicks"] <= 0 or v["simInsts"] <= 0 or
            total <= 0 or not 0 <= wrong <= total or
            wrong != v["finalConditionalWrong"] or
            total != v["predictionMetadataChecks"] or
            v["historyRestoreChecks"] != v["historyStateRestores"]):
        raise ValueError("R3 actual frontend/metadata/rollback invalid")
    counters={k:unique_int(stats,k) for k in DIAG_SCALARS}
    if any(value < 0 for value in counters.values()):
        raise ValueError("negative R3 diagnostics")
    cause={key:vector_values(stats,key,len(geo["entries"]))
           for key in DIAG_VECTORS}
    if (sum(cause["r3HitBank"]) != total or
            sum(cause["r3HitBankWrong"]) != wrong or
            sum(cause["r3SelectedBankWrong"]) != wrong or
            sum(cause["r3AllocByBank"]) != counters["r3Allocations"] or
            cause["r3AltBank"][0] != 0 or
            cause["r3AllocByBank"][0] != 0 or
            not 0 <= counters["r3AlternateWouldFix"] <=
                    counters["r3AlternateDisagreements"] <= total or
            not 0 <= counters["r3ForcedUsefulClears"] <=
                    counters["r3AllocAttempts"] or
            counters["r3Allocations"] > counters["r3AllocAttempts"]):
        raise ValueError("R3B commit/alternate/allocation conservation failed")
    for i in range(len(cause["r3HitBank"])):
        if cause["r3HitBankWrong"][i] > cause["r3HitBank"][i]:
            raise ValueError("R3B per-bank wrong > predictions")
    return dict(profile=profile,workload=workload,**v,**counters,
                r3CauseJson=json.dumps(cause,sort_keys=True,separators=(",",":")),
                mpki=f"{wrong*1000/v['simInsts']:.9f}",roi_sha256=roi_sha)

def write_csv(out, rows):
    with (out / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def summarize(out, rows, profiles, workloads, expected):
    d={(r["profile"],r["workload"]):r for r in rows}
    lines=["BPU-8 R3 G5 LOCK — REAL TAGE FIRST-ROI / R3B COMMIT COUNTERS",
           f"ROI_CHECKED={len(rows)}/{expected}",
           "All six profiles: 45,736 logical state bits. R3B is observation only.",
           "profile       samples  GM_ticks/G5_native   W/L/T  worst_pct"]
    if all(("g5_native",w) in d for w in workloads):
        for p in profiles:
            samples=[w for w in workloads if (p,w) in d]
            ratios=[d[p,w]["simTicks"]/d["g5_native",w]["simTicks"]
                    for w in samples]
            if not ratios:continue
            gm=math.exp(sum(math.log(x) for x in ratios)/len(ratios))
            wl=sum(x<1 for x in ratios),sum(x>1 for x in ratios),sum(x==1 for x in ratios)
            lines.append(f"{p:13s} {len(samples):2d}  {gm:.9f}  "
                         f"{wl[0]}/{wl[1]}/{wl[2]}  {(max(ratios)-1)*100:+.5f}")
    if len(rows)==expected:
        matrix=load_matrix()
        for label,pairs in matrix["comparisons"].items():
            lines.extend(("",f"PRE-REGISTERED PAIRED: {label}"))
            for a,b in pairs:
                diffs=[d[b,w]["simTicks"]/d[a,w]["simTicks"]
                       for w in workloads]
                gm=math.exp(sum(math.log(x) for x in diffs)/len(diffs))
                lines.append(f"{a:12s} -> {b:12s} "
                             f"GM delta={(gm-1)*100:+.7f}% "
                             f"W/L/T={sum(x<1 for x in diffs)}/"
                             f"{sum(x>1 for x in diffs)}/"
                             f"{sum(x==1 for x in diffs)}")
        hot=("huffbench","qrduino","sglib-combined")
        if len(workloads)==19:
            lines.extend(("", "Development hot3 vs remaining16 (posthoc known group)"))
            for p in ("tg6_native","tg7_native","tg6_h11","tg7_h11"):
                anchor="g5_h11" if p.endswith("h11") else "g5_native"
                for name,ws in (("hot3",hot),("other16",tuple(x for x in workloads if x not in hot))):
                    gm=math.exp(sum(math.log(d[p,w]["simTicks"]/d[anchor,w]["simTicks"])
                                    for w in ws)/len(ws))
                    lines.append(f"{p:12s} vs {anchor:10s} {name:7s}: {(gm-1)*100:+.7f}%")
        lines.extend(("", "R3B cause counters (pooled raw counts, not cross-workload significance)"))
        for p in profiles:
            selected=[d[p,w] for w in workloads]
            total=sum(v["committedConditionalPredictions"] for v in selected)
            wrong=sum(v["committedConditionalWrong"] for v in selected)
            allocation=sum(v["r3Allocations"] for v in selected)
            forced=sum(v["r3ForcedUsefulClears"] for v in selected)
            hitwrong=[0]*len(profiles[p]["entries"])
            for v in selected:
                xs=json.loads(v["r3CauseJson"])["r3HitBankWrong"]
                for bank,count in enumerate(xs[1:]):hitwrong[bank]+=count
            lines.append(f"{p:12s} branches={total} wrong={wrong} "
                         f"alloc={allocation} forced_clear={forced} "
                         f"hit_wrong_banks={hitwrong}")
        lines.append("BPU8_R3_FULL19=PASS" if len(workloads)==19
                     else "BPU8_R3_SMOKE=PASS")
    else:
        lines.append("BPU8_R3=INCOMPLETE")
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
    ap.add_argument("--out", type=Path, default=ROOT/("bpu8_r3_g5_lock_"+
                    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="only huffbench and qrduino; never mislabel as Full-19")
    args = ap.parse_args()
    if args.jobs < 1:
        ap.error("--jobs must be positive")
    matrix = load_matrix()
    workloads = tuple(matrix["smoke_workloads"]) if args.smoke else tuple(matrix["workloads"])
    profiles = matrix["profiles"]
    # Each workload's canonical G5 must be verified BEFORE a different
    # geometry is allowed to compare committed instructions against it.
    # Dict registry order is editorial, never a runnable dependency order.
    run_order = ("g5_native",) + tuple(p for p in profiles if p != "g5_native")
    jobs = [(p, w) for w in workloads for p in run_order]
    if args.list:
        # Print the exact executable job order, not the editorial registry order.
        for p, w in jobs:
            print(f"{p:12s} {w}")
        print(f"BPU8_R3_JOBS_PLANNED={len(jobs)} FULL19={not args.smoke}")
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
    manifest = dict(experiment="BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01",
        status="ACTUAL_TAGE_ONLY_FIRST_ROI_NOT_RTL_PPA",
        scope="SMOKE_2_SELECTED_BENCHMARKS_NOT_FULL19" if args.smoke else "FULL19_DEVELOPMENT_CORPUS",
        repo_head=git("rev-parse", "HEAD"), repo_clean=True,
        gem5_sha256=sha(gem5), config_sha256=sha(CONFIG_FILE),
        runner_sha256=sha(Path(__file__)), matrix_sha256=sha(MATRIX_FILE),
         r1_matrix_sha256=sha(R1_MATRIX_FILE),
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

    print(f"[1] BPU8 {len(jobs)} actual TAGE first-ROI jobs; smoke={args.smoke}",
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
        validate_r3_ini(folder/"config.ini",p,profiles)
        stats, roi = parse_first_roi(folder/"stats.txt")
        roi_path = folder/"roi.stats"
        if roi_path.exists():
            if roi_path.read_text() != roi:
                raise RuntimeError("old roi.stats differs from immutable stats.txt")
        else:
            with roi_path.open("x") as fh:
                fh.write(roi)
        row = inspect_row(stats,p,w,profiles[p],sha(roi_path))
        snap = dict(row=row, gem5_sha256=manifest["gem5_sha256"],
                    binary_sha256=manifest["benchmarks"][w])
        proof = folder/".verified.json"
        if proof.exists():
            if json.loads(proof.read_text()) != snap:
                raise RuntimeError(f"{p}/{w}: verified raw result changed")
        else:
            with proof.open("x") as f:
                f.write(json.dumps(snap,sort_keys=True,indent=2)+"\n")
        if p == "g5_native":
            g5_by_w[w] = row
        else:
            if (row["simInsts"] != g5_by_w[w]["simInsts"] or
                    row["committedConditionalPredictions"] !=
                        g5_by_w[w]["committedConditionalPredictions"]):
                raise RuntimeError(f"{p}/{w}: committed inst/branch mismatch vs G5")
        rows.append(row)
        write_csv(out,rows)
        print(f"  [{i:3d}/{len(jobs)}] {p:8s} {w:18s} "
              f"ticks={row['simTicks']} wrong={row['committedConditionalWrong']} "
              f"bits={row['storageBits']}",flush=True)
    summarize(out,rows,profiles,workloads,len(jobs))
    print("BPU8_R3_ACTUAL_FRONTEND_ROI_REPRO=PASS",flush=True)
    print("NO CLAIM: independent workload holdout or physical RTL/PPA",flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError,
            OSError, KeyError) as ex:
        print(f"BPU8_R3_FAIL_CLOSED: {ex}",file=sys.stderr)
        sys.exit(1)
