#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SRC="${SRC:-bpu_b2_micro_tage_instrumentation}"
BASE="${BASE:-bpu_b1_canonical_index_closure}"
OUT="${OUT:-$SRC/confidence_profile.csv}"

python3 - "$SRC" "$BASE" "$OUT" <<'PY'
import csv
import math
import pathlib
import sys

src=pathlib.Path(sys.argv[1])
base=pathlib.Path(sys.argv[2])
out_csv=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]
classes=["weak","medium","strong"]

def parse(path):
    scalars={}
    vectors={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2:
            continue
        key,raw=p[0],p[1]
        try:
            val=float(raw)
        except ValueError:
            continue
        scalars[key]=val
        if "::" in key:
            b,i=key.rsplit("::",1)
            if i.isdigit():
                vectors.setdefault(b,{})[int(i)]=val
    return scalars,vectors

def ss(s,suffix):
    hits=[v for k,v in s.items() if k.endswith(suffix)]
    if len(hits)!=1:
        raise RuntimeError(f"scalar suffix {suffix}: {len(hits)} hits")
    return hits[0]

def vs(v,suffix):
    hits=[x for k,x in v.items() if k.endswith(suffix)]
    if len(hits)!=1:
        raise RuntimeError(f"vector suffix {suffix}: {len(hits)} hits")
    return hits[0]

def pct(n,d):
    return 100.0*n/d if d else 0.0

rows=[]
cycle_ratios=[]

print("=== BPU-2 confidence/provider profile ===")
print(
    f"{'workload':18s} "
    f"{'W access%':>9s} {'W err%':>8s} {'W enrich':>8s} "
    f"{'M access%':>9s} {'M err%':>8s} {'M enrich':>8s} "
    f"{'W+M access%':>11s} {'W+M err%':>10s} {'W+M enrich':>10s}"
)

for w in workloads:
    s,v=parse(src/w/"roi.stats")
    total=int(ss(s,"committedConditionalPredictions"))
    wrong=int(ss(s,"committedConditionalWrong"))
    conf=vs(v,"providerConfidence")
    bad=vs(v,"providerConfidenceWrong")

    access=[int(conf.get(i,0)) for i in range(3)]
    errors=[int(bad.get(i,0)) for i in range(3)]
    ar=[pct(x,total) for x in access]
    er=[pct(x,wrong) for x in errors]
    enrich=[(er[i]/ar[i] if ar[i] else 0.0) for i in range(3)]

    wm_a=ar[0]+ar[1]
    wm_e=er[0]+er[1]
    wm_enrich=wm_e/wm_a if wm_a else 0.0

    kinds={
        "bimodal": int(ss(s,"bimodalProviderCorrect")) + int(ss(s,"bimodalProviderWrong")),
        "longest": int(ss(s,"longestMatchProviderCorrect")) + int(ss(s,"longestMatchProviderWrong")),
        "bimodal_alt": int(ss(s,"bimodalAltMatchProviderCorrect")) + int(ss(s,"bimodalAltMatchProviderWrong")),
        "tage_alt": int(ss(s,"altMatchProviderCorrect")) + int(ss(s,"altMatchProviderWrong")),
    }
    kind_bad={
        "bimodal": int(ss(s,"bimodalProviderWrong")),
        "longest": int(ss(s,"longestMatchProviderWrong")),
        "bimodal_alt": int(ss(s,"bimodalAltMatchProviderWrong")),
        "tage_alt": int(ss(s,"altMatchProviderWrong")),
    }
    if sum(kinds.values()) != total:
        raise SystemExit(f"ERROR {w}: provider-kind sum {sum(kinds.values())} != {total}")
    if sum(kind_bad.values()) != wrong:
        raise SystemExit(f"ERROR {w}: provider-kind wrong sum {sum(kind_bad.values())} != {wrong}")

    simticks=ss(s,"simTicks")
    cycles=round(simticks*1.4e9/1e12)
    base_cycles=""
    delta=""
    bpath=base/w/"btb2"/"roi.stats"
    if bpath.exists():
        bs,_=parse(bpath)
        bt=ss(bs,"simTicks")
        base_cycles=round(bt*1.4e9/1e12)
        delta=(cycles/base_cycles-1.0)*100.0
        cycle_ratios.append(cycles/base_cycles)

    print(
        f"{w:18s} "
        f"{ar[0]:9.3f} {er[0]:8.3f} {enrich[0]:8.2f} "
        f"{ar[1]:9.3f} {er[1]:8.3f} {enrich[1]:8.2f} "
        f"{wm_a:11.3f} {wm_e:10.3f} {wm_enrich:10.2f}"
    )

    rows.append({
        "workload":w,
        "micro_cycles":cycles,
        "tournament_cycles":base_cycles,
        "micro_vs_tournament_pct":f"{delta:.6f}" if delta!="" else "",
        "committed_conditional":total,
        "tage_wrong":wrong,
        "weak_access_pct":f"{ar[0]:.9f}",
        "weak_error_share_pct":f"{er[0]:.9f}",
        "weak_enrichment":f"{enrich[0]:.9f}",
        "medium_access_pct":f"{ar[1]:.9f}",
        "medium_error_share_pct":f"{er[1]:.9f}",
        "medium_enrichment":f"{enrich[1]:.9f}",
        "strong_access_pct":f"{ar[2]:.9f}",
        "strong_error_share_pct":f"{er[2]:.9f}",
        "strong_enrichment":f"{enrich[2]:.9f}",
        "weak_medium_access_pct":f"{wm_a:.9f}",
        "weak_medium_error_share_pct":f"{wm_e:.9f}",
        "weak_medium_enrichment":f"{wm_enrich:.9f}",
        "bimodal_provider_pct":f"{pct(kinds['bimodal'],total):.9f}",
        "longest_provider_pct":f"{pct(kinds['longest'],total):.9f}",
        "bimodal_alt_provider_pct":f"{pct(kinds['bimodal_alt'],total):.9f}",
        "tage_alt_provider_pct":f"{pct(kinds['tage_alt'],total):.9f}",
        "bimodal_error_share_pct":f"{pct(kind_bad['bimodal'],wrong):.9f}",
        "longest_error_share_pct":f"{pct(kind_bad['longest'],wrong):.9f}",
        "bimodal_alt_error_share_pct":f"{pct(kind_bad['bimodal_alt'],wrong):.9f}",
        "tage_alt_error_share_pct":f"{pct(kind_bad['tage_alt'],wrong):.9f}",
    })

print()
print("=== provider-kind profile ===")
print(
    f"{'workload':18s} {'bimodal%':>9s} {'longest%':>9s} "
    f"{'bimAlt%':>9s} {'tageAlt%':>9s} {'longest err%':>13s}"
)
for r in rows:
    print(
        f"{r['workload']:18s} "
        f"{float(r['bimodal_provider_pct']):9.3f} "
        f"{float(r['longest_provider_pct']):9.3f} "
        f"{float(r['bimodal_alt_provider_pct']):9.3f} "
        f"{float(r['tage_alt_provider_pct']):9.3f} "
        f"{float(r['longest_error_share_pct']):13.3f}"
    )

if cycle_ratios:
    gm=math.exp(sum(math.log(x) for x in cycle_ratios)/len(cycle_ratios))
    print()
    print(
        f"micro-TAGE/Tournament canonical six-workload cycle geomean: "
        f"{gm:.9f} ({(gm-1)*100:+.5f}%)"
    )

with out_csv.open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
    wr.writeheader()
    wr.writerows(rows)

print()
print(f"CSV: {out_csv}")
print("BPU_B2_CONFIDENCE_PROFILE=PASS")
PY
