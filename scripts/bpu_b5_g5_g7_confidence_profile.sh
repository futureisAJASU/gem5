#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SRC="${SRC:-bpu_b4c_full19_geometry}"
OUT="${OUT:-$SRC/g5_g7_confidence_profile.csv}"

python3 - "$SRC" "$OUT" <<'PY'
import csv, pathlib, sys

src=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2])
workloads=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
profiles=["g5","g7"]

def parse(path):
    s={}; v={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try: x=float(p[1])
        except ValueError: continue
        s[p[0]]=x
        if "::" in p[0]:
            b,i=p[0].rsplit("::",1)
            if i.isdigit(): v.setdefault(b,{})[int(i)]=x
    return s,v

def one(s,suf):
    h=[x for k,x in s.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError(f"{suf}: {h}")
    return h[0]

def vector(v,suf):
    h=[x for k,x in v.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError(f"{suf}: {h}")
    return h[0]

def pct(n,d): return 100.0*n/d if d else 0.0

rows=[]

for p in profiles:
    print()
    print(f"=== {p.upper()} full-19 confidence/error profile ===")
    print(f"{'workload':18s} {'W acc%':>8s} {'W err%':>8s} {'M acc%':>8s} {'M err%':>8s} {'W+M acc%':>10s} {'W+M err%':>10s} {'strong err%':>11s}")
    agg_total=agg_wrong=0
    agg_conf=[0,0,0]; agg_bad=[0,0,0]

    for w in workloads:
        s,v=parse(src/p/w/"roi.stats")
        total=int(one(s,"committedConditionalPredictions"))
        wrong=int(one(s,"committedConditionalWrong"))
        conf=vector(v,"providerConfidence")
        bad=vector(v,"providerConfidenceWrong")
        a=[int(conf.get(i,0)) for i in range(3)]
        e=[int(bad.get(i,0)) for i in range(3)]
        if sum(a)!=total: raise SystemExit(f"ERROR {p}/{w}: confidence access sum")
        if sum(e)!=wrong: raise SystemExit(f"ERROR {p}/{w}: confidence error sum")
        ar=[pct(x,total) for x in a]
        er=[pct(x,wrong) for x in e]
        wm_a=ar[0]+ar[1]; wm_e=er[0]+er[1]

        print(f"{w:18s} {ar[0]:8.3f} {er[0]:8.3f} {ar[1]:8.3f} {er[1]:8.3f} {wm_a:10.3f} {wm_e:10.3f} {er[2]:11.3f}")

        kinds={
          "bimodal": int(one(s,"bimodalProviderCorrect"))+int(one(s,"bimodalProviderWrong")),
          "longest": int(one(s,"longestMatchProviderCorrect"))+int(one(s,"longestMatchProviderWrong")),
          "bimodal_alt": int(one(s,"bimodalAltMatchProviderCorrect"))+int(one(s,"bimodalAltMatchProviderWrong")),
          "tage_alt": int(one(s,"altMatchProviderCorrect"))+int(one(s,"altMatchProviderWrong")),
        }
        badk={
          "bimodal": int(one(s,"bimodalProviderWrong")),
          "longest": int(one(s,"longestMatchProviderWrong")),
          "bimodal_alt": int(one(s,"bimodalAltMatchProviderWrong")),
          "tage_alt": int(one(s,"altMatchProviderWrong")),
        }

        rows.append({
          "profile":p,"workload":w,
          "committedConditional":total,"tageWrong":wrong,
          "weakAccessPct":ar[0],"weakErrorSharePct":er[0],
          "mediumAccessPct":ar[1],"mediumErrorSharePct":er[1],
          "strongAccessPct":ar[2],"strongErrorSharePct":er[2],
          "weakMediumAccessPct":wm_a,"weakMediumErrorSharePct":wm_e,
          "bimodalProviderPct":pct(kinds["bimodal"],total),
          "longestProviderPct":pct(kinds["longest"],total),
          "bimodalAltProviderPct":pct(kinds["bimodal_alt"],total),
          "tageAltProviderPct":pct(kinds["tage_alt"],total),
          "longestErrorSharePct":pct(badk["longest"],wrong),
        })

        agg_total+=total; agg_wrong+=wrong
        for i in range(3):
            agg_conf[i]+=a[i]; agg_bad[i]+=e[i]

    print()
    print(
      f"{p.upper()} aggregate: "
      f"W access {pct(agg_conf[0],agg_total):.3f}% / errors {pct(agg_bad[0],agg_wrong):.3f}%; "
      f"M access {pct(agg_conf[1],agg_total):.3f}% / errors {pct(agg_bad[1],agg_wrong):.3f}%; "
      f"W+M access {pct(agg_conf[0]+agg_conf[1],agg_total):.3f}% / errors {pct(agg_bad[0]+agg_bad[1],agg_wrong):.3f}%; "
      f"strong errors {pct(agg_bad[2],agg_wrong):.3f}%"
    )

with out.open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
    wr.writeheader(); wr.writerows(rows)

print()
print(f"CSV: {out}")
print("BPU_B5_G5_G7_CONFIDENCE_PROFILE=PASS")
PY
