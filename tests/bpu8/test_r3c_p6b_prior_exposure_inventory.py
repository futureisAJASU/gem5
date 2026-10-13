#!/usr/bin/env python3
"""P6B does not assert no prior exposure, even if exact SHA hits are empty."""
from pathlib import Path
import io
import json
import sys
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p6b_prior_exposure_inventory as p6b

A="a"*64
B="b"*64

def fixture():
    return {
        "kind":"R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT",
        "verdict":p6b.EXPECTED_P6A,
        "historical_unseen_workload_independence":"UNVERIFIED",
        "r3c_corpus_lock":"NOT_CREATED",
        "cases":[{
            "case":"benchmark_"+str(n),
            "rv64_elf_sha256":A if n==0 else format(n+1,"064x"),
            "input_files":[{"name":"input.dat","sha256":B}]
            if n==0 else []
        } for n in range(11)]
    }

class PriorInventoryTests(unittest.TestCase):
    def test_p6a_unverified_identity_mandatory(self):
        sig=p6b.source_fingerprints(fixture())
        self.assertEqual(sig[A],[{"case":"benchmark_0","kind":"RV64_ELF"}])
        self.assertEqual(sig[B],[{"case":"benchmark_0","kind":"INPUT:input.dat"}])
        changed=fixture()
        changed["historical_unseen_workload_independence"]="VERIFIED"
        with self.assertRaisesRegex(ValueError,"P6A custody"):
            p6b.source_fingerprints(changed)

    def test_scan_detects_exact_elf_and_input_sha_in_archive(self):
        sig=p6b.source_fingerprints(fixture())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            archive=root/"historical_R1_evidence.tar.gz"
            with tarfile.open(archive,"w:gz") as tar:
                content=json.dumps({
                    "source_digest":A,"argv":["-input"],
                    "program_file_sha256":B}).encode()
                info=tarfile.TarInfo("prior/manifest.json")
                info.size=len(content)
                tar.addfile(info,io.BytesIO(content))
            roots,matches,issues,counts=p6b.stream_historical([archive],sig)
            self.assertEqual(len(roots),1)
            self.assertEqual(len(matches),1)
            self.assertEqual({v["sha256"] for v in matches[0][
                "exact_candidate_SHA_occurrences"]},{A,B})
            self.assertEqual(issues,[])
            self.assertEqual(counts["scanned_text"],1)

    def test_partial_sha_not_collision(self):
        sig=p6b.source_fingerprints(fixture())
        x,problem=p6b.exposed_text("prior",(
            "sha="+A[:63]+"\n"+"text not a full hash").encode(),sig)
        self.assertIsNone(problem)
        self.assertEqual(x,[])

    def test_missing_explicit_prior_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"declared historical source missing"):
                p6b.stream_historical([Path(td)/"missing.tar.gz"],p6b.source_fingerprints(fixture()))

    def test_archive_binary_members_not_mistakenly_audited(self):
        sig=p6b.source_fingerprints(fixture())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/"hist.json"
            p.write_text(json.dumps({"description":"Embench Full19",
                                     "sha":"c"*64}))
            data=p6b.stream_historical([root],sig)
            self.assertEqual(len(data[1]),0)
            self.assertEqual(data[3]["scanned_text"],1)
            # No-match is a DISCOVERY observation, never an independence proof.

if __name__=="__main__":
    unittest.main()
