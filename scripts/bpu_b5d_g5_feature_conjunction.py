#!/usr/bin/env python3
import collections,csv,gzip,math,pathlib,re,sys
SRC=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "bpu_b5b_g5_temporal_holdout")
OUT=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else SRC/"bpu_b5d_feature_conjunction")
OUT.mkdir(parents=True,exist_ok=True)
W=["aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver","nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino","sglib-combined","slre","st","statemate","ud","wikisort"]
KS=(8,16,32,64)
MODES=("wm_only","hard_pc","hard_alt","hard_lowstrong","hard_alt_or_lowstrong","alt_no_pc","lowstrong_no_pc")
trx=re.compile(r"^\s*(\d+):")
erx=re.compile(r"TAGE_RESEARCH_COMMIT pc=(0x[0-9a-fA-F]+) conf=(\d+) provider=(\d+) bank=(\d+) strength=(\d+) hitBank=(-?\d+) altBank=(-?\d+) pred=(\d+) taken=(\d+) correct=(\d+) altTaken=(\d+) longestPred=(\d+)")
def stats(path):
 s={};v={}
 for line in path.read_text().splitlines():
  p=line.split()
  if len(p)<2: continue
  try:x=float(p[1])
  except: continue
  s[p[0]]=x
  if "::" in p[0]:
   b,i=p[0].rsplit("::",1)
   if i.isdigit():v.setdefault(b,{})[int(i)]=x
 return s,v
def one(s,suf):
 h=[v for k,v in s.items() if k.endswith(suf)]
 if len(h)!=1: raise RuntimeError((suf,h))
 return h[0]
def vec(v,suf):
 h=[x for k,x in v.items() if k.endswith(suf)]
 if len(h)!=1: raise RuntimeError((suf,h))
 return h[0]
def pct(n,d): return 100*n/d if d else 0.0
def wilson(w,a,z=1.96):
 if not a:return 0
 p=w/a; z2=z*z
 return (p+z2/(2*a)-z*math.sqrt(p*(1-p)/a+z2/(4*a*a)))/(1+z2/a)
def load(w):
 s,v=stats(SRC/w/"roi.stats"); start=int(one(s,"finalTick")-one(s,"simTicks")); end=int(one(s,"finalTick"))
 ev=[]
 with gzip.open(SRC/w/"tage_commit.log.gz","rt",errors="replace") as f:
  for line in f:
   m=erx.search(line)
   if not m: continue
   tm=trx.match(line)
   if not tm: raise SystemExit(f"{w}: missing tick")
   t=int(tm.group(1))
   if t<start or t>end: continue
   pred,taken,correct=int(m.group(8)),int(m.group(9)),int(m.group(10))
   if correct!=int(pred==taken): raise SystemExit(f"{w}: correctness mismatch")
   ev.append(dict(pc=int(m.group(1),16),conf=int(m.group(2)),provider=int(m.group(3)),bank=int(m.group(4)),strength=int(m.group(5)),pred=pred,alt=int(m.group(11)),correct=bool(correct)))
 if len(ev)!=int(one(s,"committedConditionalPredictions")): raise SystemExit(f"{w}: trace count")
 if sum(not e["correct"] for e in ev)!=int(one(s,"committedConditionalWrong")): raise SystemExit(f"{w}: wrong count")
 c=collections.Counter(e["conf"] for e in ev); cw=collections.Counter(e["conf"] for e in ev if not e["correct"])
 for i in range(3):
  if c[i]!=int(vec(v,"providerConfidence").get(i,0)): raise SystemExit(f"{w}: conf{i}")
  if cw[i]!=int(vec(v,"providerConfidenceWrong").get(i,0)): raise SystemExit(f"{w}: confw{i}")
 return ev
def learn(train,k):
 d={}
 for e in train:
  if e["conf"]!=2: continue
  a,w=d.get(e["pc"],(0,0)); a+=1; w+=int(not e["correct"]); d[e["pc"]]=(a,w)
 r=[]
 for pc,(a,w) in d.items():
  if w:r.append((wilson(w,a),w,a,pc))
 r.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3]))
 return {pc for *_,pc in r[:k]}
def test(ev,hs,mode):
 n=len(ev); err=sum(not e["correct"] for e in ev); serr=sum(e["conf"]==2 and not e["correct"] for e in ev); trig=te=tse=0
 for e in ev:
  wm=e["conf"]<2; strong=e["conf"]==2; hard=strong and e["pc"] in hs; alt=strong and e["pred"]!=e["alt"]; low=strong and e["strength"]==5
  fire={"wm_only":wm,"hard_pc":wm or hard,"hard_alt":wm or(hard and alt),"hard_lowstrong":wm or(hard and low),"hard_alt_or_lowstrong":wm or(hard and (alt or low)),"alt_no_pc":wm or alt,"lowstrong_no_pc":wm or low}[mode]
  if fire:
   trig+=1
   if not e["correct"]:
    te+=1; tse+=int(strong)
 br=err/n if n else 0; tr=te/trig if trig else 0
 return dict(total=n,errors=err,strong_errors=serr,triggered=trig,triggered_errors=te,triggered_strong=tse,activation=pct(trig,n),coverage=pct(te,err),strongcov=pct(tse,serr),trigerr=pct(te,trig),enrich=(tr/br if br else 0))
rows=[]; agg={(m,k):collections.Counter() for m in MODES for k in KS}
for w in W:
 ev=load(w); cut=len(ev)//2; tr,te=ev[:cut],ev[cut:]
 for k in KS:
  hs=learn(tr,k)
  for m in MODES:
   r=test(te,hs,m); rows.append({"workload":w,"mode":m,"k":k,**r})
   a=agg[(m,k)]
   for q in ("total","errors","strong_errors","triggered","triggered_errors","triggered_strong"):a[q]+=r[q]
print("=== BPU-5D aggregate held-out results ===")
print(f"{'mode':>22} {'K':>4} {'activate%':>10} {'errCover%':>10} {'strongCov%':>10} {'trigErr%':>9} {'enrich':>8}")
out=[]
for m in MODES:
 for k in KS:
  a=agg[(m,k)]; act=pct(a["triggered"],a["total"]); cov=pct(a["triggered_errors"],a["errors"]); sc=pct(a["triggered_strong"],a["strong_errors"]); tr=pct(a["triggered_errors"],a["triggered"]); br=a["errors"]/a["total"] if a["total"] else 0; rr=a["triggered_errors"]/a["triggered"] if a["triggered"] else 0; en=rr/br if br else 0
  print(f"{m:>22} {k:4d} {act:10.3f} {cov:10.3f} {sc:10.3f} {tr:9.3f} {en:8.3f}")
  out.append(dict(mode=m,k=k,activationPct=act,errorCoveragePct=cov,strongErrorCoveragePct=sc,triggerErrorRatePct=tr,enrichment=en))
with (OUT/"aggregate.csv").open("w",newline="") as f:
 wr=csv.DictWriter(f,fieldnames=out[0].keys()); wr.writeheader(); wr.writerows(out)
with (OUT/"by_workload.csv").open("w",newline="") as f:
 wr=csv.DictWriter(f,fieldnames=rows[0].keys()); wr.writeheader(); wr.writerows(rows)
print("BPU_B5D_TRACE_RECONCILIATION=PASS")
print("BPU_B5D_FEATURE_CONJUNCTION_AUDIT=PASS")
