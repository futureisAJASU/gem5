#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b5b_g5_temporal_holdout}"
EMBENCH_DIR="${EMBENCH_DIR:-$ROOT/benchmarks/external/embench-iot}"
EMBENCH_BUILD="${EMBENCH_BUILD:-$EMBENCH_DIR/bd-rv64-gem5}"
GEM5="$ROOT/build/RISCV/gem5.opt"
CFG="$ROOT/configs/02_little_v052_rv64_proxy.py"

WORKLOADS=(
  aha-mont64
  crc32
  cubic
  edn
  huffbench
  matmult-int
  minver
  nbody
  nettle-aes
  nettle-sha256
  nsichneu
  picojpeg
  qrduino
  sglib-combined
  slre
  st
  statemate
  ud
  wikisort
)

echo "[0/5] Build current gem5/RISCV"
scons build/RISCV/gem5.opt -j"$JOBS"

echo "[1/5] Verify full Embench corpus binaries"
for w in "${WORKLOADS[@]}"; do
  [[ -x "$EMBENCH_BUILD/src/$w/$w" ]] || {
    echo "ERROR: missing Embench binary for $w" >&2
    exit 2
  }
done

rm -rf "$OUT_ROOT"
mkdir -p "$OUT_ROOT"

extract_first_roi() {
  local src="$1" dst="$2"
  awk '
    /^---------- Begin Simulation Statistics ----------/ {
      section++
      if (section == 1) keep=1
    }
    keep { print }
    /^---------- End Simulation Statistics/ && keep { exit }
  ' "$src" >"$dst"
  grep -q '^---------- Begin Simulation Statistics ----------' "$dst" || {
    echo "ERROR: failed to extract first ROI from $src" >&2
    exit 4
  }
}

echo "[2/5] Run frozen G5 with all-commit research tracing (19 ROI)"
for w in "${WORKLOADS[@]}"; do
  out="$OUT_ROOT/$w"
  mkdir -p "$out"
  echo "  $w / G5 all-commit temporal trace"

  set +e
  "$GEM5" --outdir="$out"     --debug-flags=TageResearchAll     --debug-file=tage_commit.log.gz     "$CFG"     --binary "$EMBENCH_BUILD/src/$w/$w"     --bp-type tage5-iso45k     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $w G5 temporal trace rc=$rc" >&2
    tail -n 180 "$out.stdout" >&2 || true
    tail -n 180 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: benchmark verification failed for $w" >&2
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
  [[ -f "$out/tage_commit.log.gz" ]] || {
    echo "ERROR: missing all-commit research log for $w" >&2
    exit 6
  }
done

echo "[3/5] Reconcile all events and evaluate first-half -> second-half persistence"
python3 - "$OUT_ROOT" <<'PY'
import collections
import csv
import gzip
import math
import pathlib
import re
import sys

root=pathlib.Path(sys.argv[1])
workloads=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
KS=[0,8,16,32,64]

tick_rx=re.compile(r"^\s*(\d+):")
event_rx=re.compile(
    r"TAGE_RESEARCH_COMMIT pc=(0x[0-9a-fA-F]+) conf=(\d+) provider=(\d+) "
    r"bank=(\d+) strength=(\d+) hitBank=(-?\d+) altBank=(-?\d+) "
    r"pred=(\d+) taken=(\d+) correct=(\d+) altTaken=(\d+) longestPred=(\d+)"
)

def parse_stats(path):
    s={}; v={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        try:
            x=float(p[1])
        except ValueError:
            continue
        s[p[0]]=x
        if "::" in p[0]:
            b,i=p[0].rsplit("::",1)
            if i.isdigit():
                v.setdefault(b,{})[int(i)]=x
    return s,v

def one(s,suf):
    h=[x for k,x in s.items() if k.endswith(suf)]
    if len(h)!=1:
        raise RuntimeError(f"{suf}: {h}")
    return h[0]

def vector(v,suf):
    h=[x for k,x in v.items() if k.endswith(suf)]
    if len(h)!=1:
        raise RuntimeError(f"{suf}: {h}")
    return h[0]

def pct(n,d):
    return 100.0*n/d if d else 0.0

def top_set(train_events,k):
    if k == 0:
        return set()
    strong_wrong=collections.Counter(
        e["pc"] for e in train_events
        if e["conf"] == 2 and not e["correct"]
    )
    # Deterministic tie break: larger strong-wrong count first, then lower PC.
    ranked=sorted(strong_wrong.items(), key=lambda kv:(-kv[1],kv[0]))
    return {pc for pc,_ in ranked[:k]}

def evaluate(test_events, hard_set):
    total=len(test_events)
    errors=sum(not e["correct"] for e in test_events)
    strong_errors=sum((e["conf"]==2 and not e["correct"]) for e in test_events)

    triggered=0
    triggered_errors=0
    triggered_strong=0
    hard_strong_access=0
    hard_strong_wrong=0

    for e in test_events:
        low=e["conf"] in (0,1)
        hard=(e["conf"]==2 and e["pc"] in hard_set)
        fire=low or hard
        if fire:
            triggered += 1
            if not e["correct"]:
                triggered_errors += 1
            if e["conf"]==2 and not e["correct"]:
                triggered_strong += 1
        if hard:
            hard_strong_access += 1
            if not e["correct"]:
                hard_strong_wrong += 1

    baseline_error_rate=errors/total if total else 0.0
    trigger_error_rate=triggered_errors/triggered if triggered else 0.0
    enrichment=(trigger_error_rate/baseline_error_rate
                if baseline_error_rate else 0.0)

    return {
      "total":total,
      "errors":errors,
      "strong_errors":strong_errors,
      "triggered":triggered,
      "triggered_errors":triggered_errors,
      "triggered_strong":triggered_strong,
      "hard_strong_access":hard_strong_access,
      "hard_strong_wrong":hard_strong_wrong,
      "activation_pct":pct(triggered,total),
      "error_coverage_pct":pct(triggered_errors,errors),
      "strong_error_coverage_pct":pct(triggered_strong,strong_errors),
      "trigger_error_rate_pct":pct(triggered_errors,triggered),
      "enrichment":enrichment,
    }

all_rows=[]
agg={k:collections.Counter() for k in KS}

print()
print("=== BPU-5B G5 temporal holdout: train first half, test second half ===")
print("K=0 is weak+medium confidence only.")
print()

for w in workloads:
    s,v=parse_stats(root/w/"roi.stats")
    final_tick=int(one(s,"finalTick"))
    sim_ticks=int(one(s,"simTicks"))
    roi_start=final_tick-sim_ticks

    stat_total=int(one(s,"committedConditionalPredictions"))
    stat_wrong=int(one(s,"committedConditionalWrong"))
    stat_conf={i:int(x) for i,x in vector(v,"providerConfidence").items()}
    stat_conf_wrong={
        i:int(x) for i,x in vector(v,"providerConfidenceWrong").items()
    }

    events=[]
    pre_roi=0
    post_roi=0
    with gzip.open(root/w/"tage_commit.log.gz","rt",errors="replace") as f:
        for line in f:
            m=event_rx.search(line)
            if not m:
                continue
            tm=tick_rx.match(line)
            if not tm:
                raise SystemExit(
                    f"ERROR {w}: commit event missing leading tick: {line[:200]}"
                )
            tick=int(tm.group(1))
            if tick < roi_start:
                pre_roi += 1
                continue
            if tick > final_tick:
                post_roi += 1
                continue

            pred=int(m.group(8))
            taken=int(m.group(9))
            correct=int(m.group(10))
            if correct != int(pred == taken):
                raise SystemExit(f"ERROR {w}: incorrect trace correctness bit")

            events.append({
              "tick":tick,
              "pc":int(m.group(1),16),
              "conf":int(m.group(2)),
              "provider":int(m.group(3)),
              "bank":int(m.group(4)),
              "strength":int(m.group(5)),
              "correct":bool(correct),
            })

    if len(events) != stat_total:
        raise SystemExit(
            f"ERROR {w}: ROI commit trace {len(events)} != stats {stat_total}; "
            f"preROI={pre_roi} postROI={post_roi}"
        )

    conf=collections.Counter(e["conf"] for e in events)
    conf_wrong=collections.Counter(
        e["conf"] for e in events if not e["correct"]
    )
    if sum(not e["correct"] for e in events) != stat_wrong:
        raise SystemExit(f"ERROR {w}: total wrong mismatch")
    for i in range(3):
        if conf[i] != stat_conf.get(i,0):
            raise SystemExit(
                f"ERROR {w}: conf{i} accesses {conf[i]} != "
                f"{stat_conf.get(i,0)}"
            )
        if conf_wrong[i] != stat_conf_wrong.get(i,0):
            raise SystemExit(
                f"ERROR {w}: conf{i} wrong {conf_wrong[i]} != "
                f"{stat_conf_wrong.get(i,0)}"
            )

    split=len(events)//2
    train=events[:split]
    test=events[split:]

    print(f"--- {w} --- train={len(train)} test={len(test)}")
    print(
        f"{'K':>4s} {'persist%':>9s} {'activate%':>10s} "
        f"{'errCover%':>10s} {'strongCov%':>10s} "
        f"{'trigErr%':>9s} {'enrich':>8s}"
    )

    for k in KS:
        hs=top_set(train,k)
        r=evaluate(test,hs)

        # Temporal persistence: fraction of learned PCs that produce at least
        # one strong-confidence error in the held-out second half.
        test_strong_wrong_pcs={
            e["pc"] for e in test
            if e["conf"]==2 and not e["correct"]
        }
        persist=pct(len(hs & test_strong_wrong_pcs),len(hs)) if hs else 0.0

        print(
            f"{k:4d} {persist:9.3f} {r['activation_pct']:10.3f} "
            f"{r['error_coverage_pct']:10.3f} "
            f"{r['strong_error_coverage_pct']:10.3f} "
            f"{r['trigger_error_rate_pct']:9.3f} {r['enrichment']:8.3f}"
        )

        row={
          "workload":w,
          "k":k,
          "trainEvents":len(train),
          "testEvents":len(test),
          "learnedSetSize":len(hs),
          "learnedPcPersistencePct":persist,
          **r,
        }
        all_rows.append(row)

        a=agg[k]
        for field in (
            "total","errors","strong_errors","triggered",
            "triggered_errors","triggered_strong",
            "hard_strong_access","hard_strong_wrong"):
            a[field]+=r[field]
        a["learned"]+=len(hs)
        a["persistent"]+=len(hs & test_strong_wrong_pcs)

print()
print("=== aggregate held-out second-half results ===")
print(
    f"{'K':>4s} {'persist%':>9s} {'activate%':>10s} "
    f"{'errCover%':>10s} {'strongCov%':>10s} "
    f"{'trigErr%':>9s} {'enrich':>8s}"
)

agg_rows=[]
for k in KS:
    a=agg[k]
    activation=pct(a["triggered"],a["total"])
    coverage=pct(a["triggered_errors"],a["errors"])
    strong_cov=pct(a["triggered_strong"],a["strong_errors"])
    trig_err=pct(a["triggered_errors"],a["triggered"])
    base_rate=(a["errors"]/a["total"]) if a["total"] else 0.0
    trig_rate=(a["triggered_errors"]/a["triggered"]) if a["triggered"] else 0.0
    enrich=(trig_rate/base_rate) if base_rate else 0.0
    persist=pct(a["persistent"],a["learned"]) if a["learned"] else 0.0

    print(
        f"{k:4d} {persist:9.3f} {activation:10.3f} "
        f"{coverage:10.3f} {strong_cov:10.3f} "
        f"{trig_err:9.3f} {enrich:8.3f}"
    )

    agg_rows.append({
      "k":k,
      "learnedPcPersistencePct":persist,
      "activationPct":activation,
      "errorCoveragePct":coverage,
      "strongErrorCoveragePct":strong_cov,
      "triggerErrorRatePct":trig_err,
      "enrichment":enrich,
      "testEvents":a["total"],
      "testErrors":a["errors"],
      "testStrongErrors":a["strong_errors"],
      "triggeredEvents":a["triggered"],
      "triggeredErrors":a["triggered_errors"],
    })

with (root/"temporal_holdout_by_workload.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(all_rows[0].keys()))
    wr.writeheader()
    wr.writerows(all_rows)

with (root/"temporal_holdout_aggregate.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(agg_rows[0].keys()))
    wr.writeheader()
    wr.writerows(agg_rows)

print()
print("BPU_B5B_ALL_EVENT_RECONCILIATION=PASS")
print("BPU_B5B_TEMPORAL_HOLDOUT=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-5B_G5_temporal_holdout"
  echo "profile=G5-45K"
  echo "profile_bits=45736"
  echo "trace=all_committed_conditionals"
  echo "training=first_half_per_workload"
  echo "test=second_half_per_workload"
  echo "ranking=strong_wrong_count_desc_then_pc_asc"
  echo "K=0,8,16,32,64"
  echo "trigger=weak_or_medium_OR_strong_pc_in_learned_set"
  echo "condition=cond1,btb2,indirect1,btb4096_direct_proxy"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "By workload: $OUT_ROOT/temporal_holdout_by_workload.csv"
echo "Aggregate: $OUT_ROOT/temporal_holdout_aggregate.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B5B_PROVENANCE=PASS"
