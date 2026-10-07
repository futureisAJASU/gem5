#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SRC="${SRC:-bpu_b5b_g5_temporal_holdout}"
OUT_DIR="${OUT_DIR:-$SRC/bpu_b5c_trigger_efficiency}"
mkdir -p "$OUT_DIR"

python3 - "$SRC" "$OUT_DIR" <<'PY'
import collections
import csv
import gzip
import math
import pathlib
import re
import sys

src=pathlib.Path(sys.argv[1])
out=pathlib.Path(sys.argv[2])

workloads=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
POLICIES=("count","rate","wilson")
KS=(8,16,32,64)

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

def wilson_lower(w,a,z=1.96):
    if a <= 0:
        return 0.0
    p=w/a
    z2=z*z
    den=1.0+z2/a
    centre=p+z2/(2*a)
    margin=z*math.sqrt((p*(1-p)/a)+(z2/(4*a*a)))
    return (centre-margin)/den

def build_stats(train):
    by_pc={}
    for e in train:
        if e["conf"] != 2:
            continue
        pc=e["pc"]
        rec=by_pc.setdefault(pc,[0,0])
        rec[0]+=1
        if not e["correct"]:
            rec[1]+=1
    return by_pc

def rank_set(by_pc, policy, k):
    rows=[]
    for pc,(a,w) in by_pc.items():
        if w <= 0:
            continue
        if policy=="count":
            score=float(w)
        elif policy=="rate":
            score=w/a
        elif policy=="wilson":
            score=wilson_lower(w,a)
        else:
            raise ValueError(policy)
        rows.append((score,w,a,pc))
    # deterministic: score desc, wrong count desc, accesses desc, lower PC.
    rows.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3]))
    return {pc for _,_,_,pc in rows[:k]}

def evaluate(test, hard_set):
    total=len(test)
    errors=sum(not e["correct"] for e in test)
    strong_errors=sum(e["conf"]==2 and not e["correct"] for e in test)
    trig=trig_err=trig_strong_err=0
    for e in test:
        fire=(e["conf"] in (0,1)) or (e["conf"]==2 and e["pc"] in hard_set)
        if fire:
            trig+=1
            if not e["correct"]:
                trig_err+=1
                if e["conf"]==2:
                    trig_strong_err+=1
    base_rate=(errors/total) if total else 0.0
    trig_rate=(trig_err/trig) if trig else 0.0
    return {
      "total":total,
      "errors":errors,
      "strong_errors":strong_errors,
      "triggered":trig,
      "triggered_errors":trig_err,
      "triggered_strong_errors":trig_strong_err,
      "activation_pct":pct(trig,total),
      "error_coverage_pct":pct(trig_err,errors),
      "strong_error_coverage_pct":pct(trig_strong_err,strong_errors),
      "trigger_error_rate_pct":pct(trig_err,trig),
      "enrichment":(trig_rate/base_rate) if base_rate else 0.0,
    }

def load_events(w):
    s,v=parse_stats(src/w/"roi.stats")
    final_tick=int(one(s,"finalTick"))
    sim_ticks=int(one(s,"simTicks"))
    roi_start=final_tick-sim_ticks

    stat_total=int(one(s,"committedConditionalPredictions"))
    stat_wrong=int(one(s,"committedConditionalWrong"))
    stat_conf={i:int(x) for i,x in vector(v,"providerConfidence").items()}
    stat_conf_wrong={i:int(x) for i,x in vector(v,"providerConfidenceWrong").items()}

    events=[]
    with gzip.open(src/w/"tage_commit.log.gz","rt",errors="replace") as f:
        for line in f:
            m=event_rx.search(line)
            if not m:
                continue
            tm=tick_rx.match(line)
            if not tm:
                raise SystemExit(f"ERROR {w}: missing tick")
            tick=int(tm.group(1))
            if tick < roi_start or tick > final_tick:
                continue
            pred=int(m.group(8))
            taken=int(m.group(9))
            correct=int(m.group(10))
            if correct != int(pred==taken):
                raise SystemExit(f"ERROR {w}: correctness mismatch")
            events.append({
              "pc":int(m.group(1),16),
              "conf":int(m.group(2)),
              "provider":int(m.group(3)),
              "bank":int(m.group(4)),
              "strength":int(m.group(5)),
              "correct":bool(correct),
            })

    if len(events)!=stat_total:
        raise SystemExit(f"ERROR {w}: trace count {len(events)} != {stat_total}")
    if sum(not e["correct"] for e in events)!=stat_wrong:
        raise SystemExit(f"ERROR {w}: wrong count mismatch")
    c=collections.Counter(e["conf"] for e in events)
    cw=collections.Counter(e["conf"] for e in events if not e["correct"])
    for i in range(3):
        if c[i]!=stat_conf.get(i,0):
            raise SystemExit(f"ERROR {w}: conf{i} access mismatch")
        if cw[i]!=stat_conf_wrong.get(i,0):
            raise SystemExit(f"ERROR {w}: conf{i} wrong mismatch")
    return events

all_rows=[]
agg={(p,k):collections.Counter() for p in POLICIES for k in KS}

print("=== BPU-5C no-rerun trigger-efficiency audit ===")
print("Train=first half, test=second half. Trigger=W+M OR strong learned-PC.")
print()

for w in workloads:
    events=load_events(w)
    split=len(events)//2
    train=events[:split]
    test=events[split:]
    by_pc=build_stats(train)

    print(f"--- {w} ---")
    print(f"{'policy':>8s} {'K':>4s} {'activate%':>10s} {'errCover%':>10s} {'strongCov%':>10s} {'trigErr%':>9s} {'enrich':>8s}")
    for p in POLICIES:
        for k in KS:
            hs=rank_set(by_pc,p,k)
            r=evaluate(test,hs)
            print(
                f"{p:>8s} {k:4d} {r['activation_pct']:10.3f} "
                f"{r['error_coverage_pct']:10.3f} "
                f"{r['strong_error_coverage_pct']:10.3f} "
                f"{r['trigger_error_rate_pct']:9.3f} {r['enrichment']:8.3f}"
            )
            row={"workload":w,"policy":p,"k":k,"learnedSetSize":len(hs),**r}
            all_rows.append(row)
            a=agg[(p,k)]
            for field in ("total","errors","strong_errors","triggered","triggered_errors","triggered_strong_errors"):
                a[field]+=r[field]

print()
print("=== aggregate held-out results ===")
print(f"{'policy':>8s} {'K':>4s} {'activate%':>10s} {'errCover%':>10s} {'strongCov%':>10s} {'trigErr%':>9s} {'enrich':>8s}")
agg_rows=[]
for p in POLICIES:
    for k in KS:
        a=agg[(p,k)]
        activation=pct(a["triggered"],a["total"])
        coverage=pct(a["triggered_errors"],a["errors"])
        strong_cov=pct(a["triggered_strong_errors"],a["strong_errors"])
        trig_err=pct(a["triggered_errors"],a["triggered"])
        base_rate=(a["errors"]/a["total"]) if a["total"] else 0.0
        trig_rate=(a["triggered_errors"]/a["triggered"]) if a["triggered"] else 0.0
        enrich=(trig_rate/base_rate) if base_rate else 0.0
        print(f"{p:>8s} {k:4d} {activation:10.3f} {coverage:10.3f} {strong_cov:10.3f} {trig_err:9.3f} {enrich:8.3f}")
        agg_rows.append({
          "policy":p,"k":k,
          "activationPct":activation,
          "errorCoveragePct":coverage,
          "strongErrorCoveragePct":strong_cov,
          "triggerErrorRatePct":trig_err,
          "enrichment":enrich,
          "testEvents":a["total"],
          "testErrors":a["errors"],
          "testStrongErrors":a["strong_errors"],
        })

with (out/"by_workload.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(all_rows[0].keys()))
    wr.writeheader(); wr.writerows(all_rows)

with (out/"aggregate.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(agg_rows[0].keys()))
    wr.writeheader(); wr.writerows(agg_rows)

print()
print("BPU_B5C_TRACE_RECONCILIATION=PASS")
print("BPU_B5C_TRIGGER_EFFICIENCY_AUDIT=PASS")
PY

echo "By workload: $OUT_DIR/by_workload.csv"
echo "Aggregate: $OUT_DIR/aggregate.csv"
