#!/usr/bin/env python3
"""P6D licenses are reviewed but NEVER auto-approved; source SHAs immutable."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p6d_final_prelock_license_review as p6d

class P6DSourceLicenseTests(unittest.TestCase):
    def test_mibench_license_present_with_actual_p1_sha(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/"network"/"dijkstra"
            d.mkdir(parents=True)
            (d/"dijkstra.c").write_text("int main(void){return 0;}\n")
            (d/"LICENSE").write_text("GPL'ed.\n")
            original={"candidate_sources":{
                "dijkstra":{"source_subdir":"network/dijkstra",
                            "files":[{
                               "path":p,"sha256":p6d.p2.sha(d/p),
                               "size":(d/p).stat().st_size}
                               for p in ("dijkstra.c","LICENSE")]}}}
            report=p6d.candidate_license_records("dijkstra",Path(td),original)
            self.assertTrue(report["license_material_present"])
            self.assertEqual(len(report["license_files"]),1)
            self.assertEqual(report["license_files"][0]["sha256"],
                             p6d.p2.sha(d/"LICENSE"))
            self.assertEqual(report["license_classification"],
                             "REQUIRES_HUMAN_REVIEW")

    def test_source_modification_blocks_review(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/"network"/"dijkstra"
            d.mkdir(parents=True)
            f=d/"LICENSE"
            f.write_text("Original terms")
            obj={"candidate_sources":{
                "dijkstra":{"source_subdir":"network/dijkstra",
                            "files":[{"path":"LICENSE",
                                      "sha256":p6d.p2.sha(f),"size":f.stat().st_size}]}}}
            f.write_text("Altered! note")
            with self.assertRaisesRegex(ValueError,"P1 source file mutated"):
                p6d.candidate_license_records("dijkstra",Path(td),obj)

    def test_prelock_signoff_is_never_automatic(self):
        src=(ROOT/"scripts/bpu_b8_r3c_p6d_final_prelock_license_review.py").read_text()
        self.assertIn('"manual_license_review":"REQUIRED"',src)
        self.assertIn('"r3c_corpus_lock":"NOT_CREATED"',src)
        self.assertIn('"authorized_six_profile_holdout_runs":0',src)
        self.assertIn("NOT_CLAIMED_INTERNAL_10_ITERATION_ROI",src)

if __name__=="__main__":
    unittest.main()
