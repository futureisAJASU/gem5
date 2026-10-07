#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JOBS="${JOBS:-$(nproc)}"
OUT_ROOT="${OUT_ROOT:-bpu_b5a_g5_strong_error_localization}"
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

echo "[2/5] Run frozen G5 with research-only wrong-event tracing (19 ROI)"
for w in "${WORKLOADS[@]}"; do
  out="$OUT_ROOT/$w"
  mkdir -p "$out"
  echo "  $w / G5 strong-error localization"

  set +e
  "$GEM5" --outdir="$out"     --debug-flags=TageResearch     --debug-file=tage_research.log     "$CFG"     --binary "$EMBENCH_BUILD/src/$w/$w"     --bp-type tage5-iso45k     --bp-inst-shift 1     --bp-cond-shift 1     --bp-btb-shift 2     --bp-indirect-shift 1     --btb-entries 4096     >"$out.stdout" 2>"$out.stderr"
  rc=$?
  set -e

  if (( rc != 0 )); then
    echo "ERROR: $w G5 localization rc=$rc" >&2
    tail -n 160 "$out.stdout" >&2 || true
    tail -n 160 "$out.stderr" >&2 || true
    exit "$rc"
  fi

  grep -q 'SIMULATION_EXIT_CODE=0' "$out.stdout" || {
    echo "ERROR: benchmark verification failed for $w" >&2
    exit 5
  }

  extract_first_roi "$out/stats.txt" "$out/roi.stats"
  [[ -f "$out/tage_research.log" ]] || {
    echo "ERROR: missing research log for $w" >&2
    exit 6
  }
done

echo "[3/5] Reconcile logs with stats and measure exact static-PC concentration"
python3 - "$OUT_ROOT" <<'PY'
import collections
import csv
import pathlib
import re
import sys

root=pathlib.Path(sys.argv[1])
workloads=[
  "aha-mont64","crc32","cubic","edn","huffbench","matmult-int","minver",
  "nbody","nettle-aes","nettle-sha256","nsichneu","picojpeg","qrduino",
  "sglib-combined","slre","st","statemate","ud","wikisort"
]
tick_rx=re.compile(r"^\\s*(\\d+):")
rx=re.compile(
    r"TAGE_RESEARCH_WRONG pc=(0x[0-9a-fA-F]+) conf=(\d+) provider=(\d+) "
    r"bank=(\d+) strength=(\d+) hitBank=(-?\d+) altBank=(-?\d+) "
    r"pred=(\d+) taken=(\d+) altTaken=(\d+) longestPred=(\d+)"
)

def parse_stats(path):
    s={}; v={}
    for line in path.read_text().splitlines():
        p=line.split()
        if len(p)<2: continue
        try: x=float(p[1])
        except ValueError: continue
        s[p[0]]=x
        if "::" in p[0]:
            b,i=p[0].rsplit("::",1)
            if i.isdigit():
                v.setdefault(b,{})[int(i)]=x
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

def coverage(counter, ks):
    vals=sorted(counter.values(), reverse=True)
    total=sum(vals)
    out={}
    for k in ks:
        out[k]=pct(sum(vals[:k]),total)
    return total,len(vals),out

def n_for(counter, fraction):
    vals=sorted(counter.values(), reverse=True)
    target=sum(vals)*fraction
    cur=0
    for i,x in enumerate(vals,1):
        cur+=x
        if cur>=target:
            return i
    return 0

all_strong=collections.Counter()
all_wrong=collections.Counter()
joint_provider=collections.Counter()
joint_bank=collections.Counter()
rows=[]
ks=[1,4,8,16,32,64]

print()
print("=== BPU-5A G5 exact strong-error static-PC localization ===")
print(
    f"{'workload':18s} {'wrong':>8s} {'strong':>8s} {'uniqS':>7s} "
    f"{'top1%':>7s} {'top4%':>7s} {'top8%':>7s} {'top16%':>8s} "
    f"{'N50':>6s} {'N75':>6s} {'N90':>6s}"
)

for w in workloads:
    s,v=parse_stats(root/w/"roi.stats")
    stat_wrong=int(one(s,"committedConditionalWrong"))
    stat_conf={i:int(x) for i,x in vector(v,"providerConfidenceWrong").items()}
    sim_ticks=int(one(s,"simTicks"))
    final_tick=int(one(s,"finalTick"))
    roi_start_tick=final_tick-sim_ticks
    if roi_start_tick < 0:
        raise SystemExit(
            f"ERROR {w}: invalid ROI tick window start={roi_start_tick} "
            f"final={final_tick} simTicks={sim_ticks}"
        )

    wrong=collections.Counter()
    strong=collections.Counter()
    conf_counts=collections.Counter()
    provider=collections.Counter()
    bank=collections.Counter()

    matched=0
    pre_roi_wrong=0
    post_roi_wrong=0
    for line in (root/w/"tage_research.log").read_text(errors="replace").splitlines():
        m=rx.search(line)
        if not m:
            continue
        tm=tick_rx.match(line)
        if not tm:
            raise SystemExit(
                f"ERROR {w}: research event missing leading gem5 tick: {line}"
            )
        tick=int(tm.group(1))
        if tick < roi_start_tick:
            pre_roi_wrong += 1
            continue
        if tick > final_tick:
            post_roi_wrong += 1
            continue

        pc=int(m.group(1),16)
        conf=int(m.group(2))
        prov=int(m.group(3))
        b=int(m.group(4))
        key=(w,pc)
        matched+=1
        wrong[key]+=1
        conf_counts[conf]+=1
        if conf==2:
            strong[key]+=1
            provider[prov]+=1
            bank[b]+=1
            all_strong[key]+=1
            joint_provider[prov]+=1
            joint_bank[(w,b)]+=1
        all_wrong[key]+=1

    if matched != stat_wrong:
        raise SystemExit(
            f"ERROR {w}: ROI-window logged wrong {matched} != "
            f"stats committed wrong {stat_wrong}; "
            f"window=[{roi_start_tick},{final_tick}] "
            f"preROI={pre_roi_wrong} postROI={post_roi_wrong}"
        )
    for i in range(3):
        if conf_counts[i] != stat_conf.get(i,0):
            raise SystemExit(
                f"ERROR {w}: logged conf{i} wrong {conf_counts[i]} "
                f"!= stats {stat_conf.get(i,0)}"
            )

    total,uniq,cov=coverage(strong,ks)
    print(
        f"{w:18s} {matched:8d} {total:8d} {uniq:7d} "
        f"{cov[1]:7.2f} {cov[4]:7.2f} {cov[8]:7.2f} {cov[16]:8.2f} "
        f"{n_for(strong,.50):6d} {n_for(strong,.75):6d} {n_for(strong,.90):6d}"
    )

    rows.append({
      "workload":w,
      "roiStartTick":roi_start_tick,
      "roiEndTick":final_tick,
      "preRoiWrongEventsIgnored":pre_roi_wrong,
      "postRoiWrongEventsIgnored":post_roi_wrong,
      "wrong":matched,
      "strongWrong":total,
      "uniqueStrongWrongPCs":uniq,
      "top1StrongCoveragePct":cov[1],
      "top4StrongCoveragePct":cov[4],
      "top8StrongCoveragePct":cov[8],
      "top16StrongCoveragePct":cov[16],
      "top32StrongCoveragePct":cov[32],
      "top64StrongCoveragePct":cov[64],
      "pcsFor50PctStrong":n_for(strong,.50),
      "pcsFor75PctStrong":n_for(strong,.75),
      "pcsFor90PctStrong":n_for(strong,.90),
    })

total,uniq,cov=coverage(all_strong,ks)
print()
print("=== aggregate across workload+PC identities ===")
print(f"strong wrong events     = {total}")
print(f"unique strong-wrong PCs = {uniq}")
for k in ks:
    print(f"top {k:2d} static branch identities cover {cov[k]:.3f}% of strong errors")
print(f"PCs required for 50% strong errors = {n_for(all_strong,.50)}")
print(f"PCs required for 75% strong errors = {n_for(all_strong,.75)}")
print(f"PCs required for 90% strong errors = {n_for(all_strong,.90)}")

print()
print("=== strong-error provider distribution ===")
for p,n in sorted(joint_provider.items()):
    print(f"provider {p}: {n} ({pct(n,total):.3f}%)")

print()
print("=== top 32 workload+PC strong-error identities ===")
for (w,pc),n in all_strong.most_common(32):
    print(f"{w:18s} pc=0x{pc:x} strongWrong={n:8d} share={pct(n,total):7.3f}%")

with (root/"strong_pc_concentration.csv").open("w",newline="") as f:
    wr=csv.DictWriter(f,fieldnames=list(rows[0].keys()))
    wr.writeheader(); wr.writerows(rows)

with (root/"strong_pc_top.csv").open("w",newline="") as f:
    wr=csv.writer(f)
    wr.writerow(["rank","workload","pc","strongWrong","aggregateStrongSharePct"])
    for rank,((w,pc),n) in enumerate(all_strong.most_common(),1):
        wr.writerow([rank,w,f"0x{pc:x}",n,f"{pct(n,total):.9f}"])

print()
print("BPU_B5A_WRONG_EVENT_RECONCILIATION=PASS")
print("BPU_B5A_CONFIDENCE_RECONCILIATION=PASS")
print("BPU_B5A_STRONG_PC_LOCALIZATION=PASS")
PY

echo "[4/5] Emit provenance"
{
  echo "gem5_head=$(git rev-parse HEAD)"
  echo "embench_head=$(git -C "$EMBENCH_DIR" rev-parse HEAD)"
  echo "experiment=BPU-5A_G5_strong_error_static_PC_localization"
  echo "profile=G5-45K"
  echo "profile_bits=45736"
  echo "debug_flag=TageResearch"
  echo "logged_events=wrong_committed_conditionals_only"
  echo "condition=cond1,btb2,indirect1,btb4096_direct_proxy"
  echo "workloads=aha-mont64,crc32,cubic,edn,huffbench,matmult-int,minver,nbody,nettle-aes,nettle-sha256,nsichneu,picojpeg,qrduino,sglib-combined,slre,st,statemate,ud,wikisort"
} >"$OUT_ROOT/manifest.txt"

echo "[5/5] Done"
echo "Concentration: $OUT_ROOT/strong_pc_concentration.csv"
echo "Ranked PCs: $OUT_ROOT/strong_pc_top.csv"
echo "Manifest: $OUT_ROOT/manifest.txt"
echo "BPU_B5A_PROVENANCE=PASS"
