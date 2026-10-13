#!/usr/bin/env python3
"""R3C P6B: scan explicitly named HISTORICAL evidence for candidate fingerprints.

This is an inventory, NOT a declaration of unseen input independence.
Required evidence roots must be explicitly supplied. No gem5 jobs, no
results inspection or automatic r3c_corpus_lock.json creation.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
import tarfile

import bpu_b8_r3c_p2_build as p2

SHA_RE=re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])")
TEXT_SUFFIXES={".json",".csv",".tsv",".txt",".md",".yaml",".yml",".log"}
MAX_BYTES=8*1024*1024
MAX_ENTRIES=30000
MAX_HITS=2500
EXPECTED_P6A="11_CASE_CUSTODY_CHECKED_HISTORICAL_INDEPENDENCE_NOT_VERIFIED_NOT_LOCKED"

def require(ok,why):
    if not ok:
        raise ValueError(why)

def source_fingerprints(snap:dict):
    require(snap.get("kind")=="R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT"
            and snap.get("verdict")==EXPECTED_P6A
            and snap.get("historical_unseen_workload_independence")=="UNVERIFIED"
            and snap.get("r3c_corpus_lock")=="NOT_CREATED"
            and len(snap.get("cases",[]))==11,
            "P6A custody source not a supported prelock")
    by_hash={}
    for case in snap["cases"]:
        for kind,h in [("RV64_ELF",case["rv64_elf_sha256"])] + [
                ("INPUT:"+i["name"],i["sha256"])
                for i in case["input_files"]]:
            require(isinstance(h,str) and bool(re.fullmatch(r"[a-f0-9]{64}",h)),
                    case["case"]+": malformed digest")
            by_hash.setdefault(h,[]).append({"case":case["case"],"kind":kind})
    require(len({c["case"] for c in snap["cases"]})==11,
            "duplicate case identity")
    return by_hash

def exposed_text(pathname:str, raw:bytes, fingerprints:dict):
    """Returns exact candidate SHA occurrence; excludes name-only guesses."""
    if len(raw)>MAX_BYTES:
        return None,"OVERSIZE"
    try:
        txt=raw.decode("utf-8")
    except UnicodeDecodeError:
        return None,"NON_UTF8"
    hits=[]
    for value in sorted({i.lower() for i in SHA_RE.findall(txt)}):
        if value in fingerprints:
            hits.append({"sha256":value,"candidate_fingerprints":fingerprints[value]})
    return hits,None

def stream_historical(paths, fingerprints):
    indexed=[];matches=[];issues=[];counter=Counter()
    for ref in paths:
        ref=ref.expanduser().resolve()
        require(ref.exists(), "declared historical source missing: "+str(ref))
        if ref.is_file():
            targets=[ref]
        else:
            targets=sorted(p for p in ref.rglob("*") if p.is_file()
                           and ".git" not in p.parts
                           and "__pycache__" not in p.parts
                           and p.suffix.lower() in TEXT_SUFFIXES.union({".gz",".tar"}))
        for f in targets:
            counter["listed"]+=1
            require(counter["listed"]<=MAX_ENTRIES,
                    "too many files; split evidence roots, do NOT claim completion")
            if tarfile.is_tarfile(f):
                counter["archives"]+=1
                try:
                    with tarfile.open(f,"r:*") as archive:
                        for info in archive:
                            if not info.isfile():
                                continue
                            if not (Path(info.name).suffix.lower() in TEXT_SUFFIXES):
                                continue
                            counter["archive_members_listed"]+=1
                            require(counter["archive_members_listed"]<=MAX_ENTRIES,
                                    "too many archive members; split evidence roots")
                            if info.size>MAX_BYTES:
                                issues.append({"source":str(f)+"!"+info.name,
                                               "reason":"OVERSIZE"})
                                continue
                            file=archive.extractfile(info)
                            require(file is not None,"cannot read archive member")
                            match,problem=exposed_text(info.name,file.read(MAX_BYTES+1),fingerprints)
                            label=str(f)+"!"+info.name
                            if problem:
                                issues.append({"source":label,"reason":problem})
                            else:
                                counter["scanned_text"]+=1
                                if match:
                                    matches.append({"source":label,"exact_candidate_SHA_occurrences":match})
                except (tarfile.TarError, EOFError) as error:
                    raise ValueError("historical archive cannot be read: "+str(f)+": "+str(error)) from error
            elif f.suffix.lower() in TEXT_SUFFIXES:
                try:
                    if f.stat().st_size>MAX_BYTES:
                        issues.append({"source":str(f),"reason":"OVERSIZE"})
                        continue
                    match,problem=exposed_text(str(f),f.read_bytes(),fingerprints)
                    if problem:
                        issues.append({"source":str(f),"reason":problem})
                    else:
                        counter["scanned_text"]+=1
                        if match:
                            matches.append({"source":str(f),"exact_candidate_SHA_occurrences":match})
                except OSError as error:
                    raise ValueError("could not read historical evidence: "+str(f)) from error
            else:
                issues.append({"source":str(f),"reason":"UNSUPPORTED_FILE_FORMAT"})
            if len(issues)+len(matches)>MAX_HITS:
                raise ValueError("too many outcomes; reduce scan root, preserve original inventory")
        indexed.append({"root":str(ref),"type":"dir" if ref.is_dir() else "file",
                        "requested_explicitly":True})
    require(counter["scanned_text"]>0,
            "no readable historical sources; cannot assess prior exposure")
    return indexed,matches,issues,dict(counter)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--p6a",type=Path,required=True)
    p.add_argument("--prior-evidence",type=Path,action="append",required=True,
                   help="Explicit pre-R3C historical directory or .tar.gz; repeat per source")
    p.add_argument("--out",type=Path,required=True)
    opts=p.parse_args()
    snapfile=opts.p6a.expanduser().resolve()
    dest=opts.out.expanduser().resolve()
    require(not dest.exists(),"output file exists; preserve previous proof")
    require(snapfile.is_file(),"P6A JSON missing")
    snap=json.loads(snapfile.read_text())
    fingerprints=source_fingerprints(snap)
    roots=[p.expanduser().resolve() for p in opts.prior_evidence]
    # Do not use P6A/P5A/R3C as "historical": they necessarily contain
    # the candidate hashes but were created during qualification.
    require(all("r3c" not in str(p).lower() for p in roots),
            "candidate R3C evidence mistakenly passed as independent historical data")
    indexed,collision,issues,count=stream_historical(roots,fingerprints)
    record={
        "kind":"R3C_P6B_EXPLICIT_PRIOR_EVIDENCE_FINGERPRINT_DISCOVERY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "verdict":"PRIOR_EVIDENCE_DISCOVERY_REQUIRES_COMPLETENESS_REVIEW_NO_CORPUS_LOCK",
        "p6a_sha256":p2.sha(snapfile),
        "prior_sources":indexed,
        "counts":count,
        "prior_exact_candidate_SHA_occurrences":collision,
        "skipped_or_unreadable_members":issues,
        "coverage":"EXPLICIT_SOURCES_ONLY_NOT_ALL_PAST_EXPERIMENTS",
        "all_prior_experiment_logs_discovered":"NOT_PROVEN",
        "independence_of_11_cases":"NOT_DETERMINED",
        "source_and_license_signoff":"NOT_COMPLETED",
        "corpus_lock":"NOT_AUTHORIZED",
        "holdout_jobs":0,
        "next":"Reconcile all exact-SHA hits and enumerate missing historical campaigns. "
               "Use original prior run commands/source/input identity as the decisive "
               "evidence, not a name-only mismatch or absence of SHA hits.",
    }
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x") as f:
        json.dump(record,f,ensure_ascii=False,sort_keys=True,indent=2)
        f.write("\n")
    print("R3C_P6B_SNAPSHOT="+str(dest))
    print("R3C_P6B_SHA256="+p2.sha(dest))
    print("R3C_P6B_PRIOR_SOURCES="+str(len(indexed)))
    print("R3C_P6B_MATCHING_SOURCES="+str(len(collision)))
    print("R3C_P6B_SKIPPED_OR_UNREADABLE="+str(len(issues)))
    print("R3C_P6B_VERDICT="+record["verdict"])
    print("NO CLAIM: exhaustive prior evidence, untouched independence, "
          "corpus lock, or 66-run holdout")

if __name__=="__main__":
    try: main()
    except (KeyError,ValueError,OSError,tarfile.TarError) as exc:
        print("R3C_P6B_FAIL_CLOSED: "+str(exc),file=sys.stderr)
        sys.exit(1)
