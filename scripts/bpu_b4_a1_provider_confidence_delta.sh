#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

A1="${A1:-bpu_b4a1_tagged_entries_sweep}"
EXT="${EXT:-bpu_b4a1_extension_2048}"
OUT="${OUT:-$EXT/provider_confidence_delta_1024_2048.csv}"

python3 - "$A1" "$EXT" "$OUT" <<'PY'
import csv, pathlib, sys

a1=pathlib.Path(sys.argv[1]); ext=pathlib.Path(sys.argv[2]); out=pathlib.Path(sys.argv[3])
workloads=["statemate","crc32","nsichneu","slre","sglib-combined","qrduino"]

def parse(path):
    scalars={}; vectors={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try: v=float(p[1])
        except ValueError: continue
        scalars[p[0]]=v
        if "::" in p[0]:
            b,i=p[0].rsplit("::",1)
            if i.isdigit(): vectors.setdefault(b,{})[int(i)]=v
    return scalars,vectors

def scalar(s,suf):
    h=[v for k,v in s.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError(f"{suf}: {h}")
    return h[0]

def vector(v,suf):
    h=[x for k,x in v.items() if k.endswith(suf)]
    if len(h)!=1: raise RuntimeError(f"{suf}: {[k for k in v if k.endswith(suf)]}")
    return h[0]

def pct(n,d): return 100.0*n/d if d else 0.0

rows=[]
print("=== BPU-4 A1 no-rerun provider/confidence delta: e1024 -> e2048 ===")
print(f"{'workload':18s} {'B0 dpp':>8s} {'B1 dpp':>8s} {'B2 dpp':>8s} {'B3 dpp':>8s} {'W dpp':>8s} {'M dpp':>8s} {'S dpp':>8s} {'err%':>9s}")

for w in workloads:
    s1,v1=parse(a1/w/"e1024"/"roi.stats")
    s2,v2=parse(ext/w/"e2048"/"roi.stats")

    t1=scalar(s1,"committedConditionalPredictions"); t2=scalar(s2,"committedConditionalPredictions")
    e1=scalar(s1,"committedConditionalWrong"); e2=scalar(s2,"committedConditionalWrong")
    b1=vector(v1,"selectedProviderBank"); b2=vector(v2,"selectedProviderBank")
    c1=vector(v1,"providerConfidence"); c2=vector(v2,"providerConfidence")

    bp1=[pct(b1.get(i,0),t1) for i in range(4)]
    bp2=[pct(b2.get(i,0),t2) for i in range(4)]
    cp1=[pct(c1.get(i,0),t1) for i in range(3)]
    cp2=[pct(c2.get(i,0),t2) for i in range(3)]

    kinds={}
    for tag,s in (("1024",s1),("2048",s2)):
        total=t1 if tag=="1024" else t2
        wrong=e1 if tag=="1024" else e2
        d={
          "bimodal": scalar(s,"bimodalProviderCorrect")+scalar(s,"bimodalProviderWrong"),
          "longest": scalar(s,"longestMatchProviderCorrect")+scalar(s,"longestMatchProviderWrong"),
          "bimAlt": scalar(s,"bimodalAltMatchProviderCorrect")+scalar(s,"bimodalAltMatchProviderWrong"),
          "tageAlt": scalar(s,"altMatchProviderCorrect")+scalar(s,"altMatchProviderWrong"),
          "longestWrong": scalar(s,"longestMatchProviderWrong"),
        }
        kinds[tag]={
          "longestPct":pct(d["longest"],total),
          "bimodalPct":pct(d["bimodal"],total),
          "longestErrShare":pct(d["longestWrong"],wrong),
        }

    err_red=(1-e2/e1)*100 if e1 else 0.0
    print(f"{w:18s} {bp2[0]-bp1[0]:8.3f} {bp2[1]-bp1[1]:8.3f} {bp2[2]-bp1[2]:8.3f} {bp2[3]-bp1[3]:8.3f} {cp2[0]-cp1[0]:8.3f} {cp2[1]-cp1[1]:8.3f} {cp2[2]-cp1[2]:8.3f} {err_red:9.3f}")

    rows.append({
      "workload":w,
      "wrong1024":int(e1),"wrong2048":int(e2),"errorReductionPct":err_red,
      **{f"B{i}_pct_1024":bp1[i] for i in range(4)},
      **{f"B{i}_pct_2048":bp2[i] for i in range(4)},
      **{f"B{i}_delta_pp":bp2[i]-bp1[i] for i in range(4)},
      "weak_pct_1024":cp1[0],"weak_pct_2048":cp2[0],"weak_delta_pp":cp2[0]-cp1[0],
      "medium_pct_1024":cp1[1],"medium_pct_2048":cp2[1],"medium_delta_pp":cp2[1]-cp1[1],
      "strong_pct_1024":cp1[2],"strong_pct_2048":cp2[2],"strong_delta_pp":cp2[2]-cp1[2],
      "longest_provider_pct_1024":kinds["1024"]["longestPct"],
      "longest_provider_pct_2048":kinds["2048"]["longestPct"],
      "bimodal_provider_pct_1024":kinds["1024"]["bimodalPct"],
      "bimodal_provider_pct_2048":kinds["2048"]["bimodalPct"],
      "longest_error_share_pct_1024":kinds["1024"]["longestErrShare"],
      "longest_error_share_pct_2048":kinds["2048"]["longestErrShare"],
    })

print()
print("=== provider-kind details ===")
print(f"{'workload':18s} {'long1024%':>10s} {'long2048%':>10s} {'base1024%':>10s} {'base2048%':>10s} {'longErr1%':>10s} {'longErr2%':>10s}")
for r in rows:
    print(f"{r['workload']:18s} {r['longest_provider_pct_1024']:10.3f} {r['longest_provider_pct_2048']:10.3f} {r['bimodal_provider_pct_1024']:10.3f} {r['bimodal_provider_pct_2048']:10.3f} {r['longest_error_share_pct_1024']:10.3f} {r['longest_error_share_pct_2048']:10.3f}")

with out.open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
    wr.writeheader(); wr.writerows(rows)

print()
print(f"CSV: {out}")
print("BPU_B4_A1_PROVIDER_CONFIDENCE_DELTA=PASS")
PY
