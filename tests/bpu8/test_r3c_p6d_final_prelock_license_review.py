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

    def test_complete_dossier_integration_never_implicitly_freezes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            mibench=root/"mibench"
            coremark=root/"coremark"
            mibench.mkdir();coremark.mkdir()
            (coremark/"LICENSE.md").write_text("P6D fixed fixture terms")
            case_files={}
            for name in p6d.EXPECTED_CASES[:-1]:
                target=mibench/name
                target.mkdir()
                (target/"LICENSE").write_text(name+" license")
                case_files[name]={
                    "source_subdir":name,
                    "files":[{
                        "path":"LICENSE",
                        "size":(target/"LICENSE").stat().st_size,
                        "sha256":p6d.p2.sha(target/"LICENSE")
                    }]
                }
            p1={
                "kind":"BPU8_R3C_P1_SOURCE_CUSTODY_NO_COMPILE_NO_RUN",
                "verdict":"SOURCE_TREE_PRESENT_NOT_CORPUS_LOCK",
                "missing_source_paths":[],
                "candidate_sources":case_files,
                "coremark_sources":{"LICENSE.md":{
                    "sha256":p6d.p2.sha(coremark/"LICENSE.md")}},
                "mibench":{"path":str(mibench),"git_head":"m1",
                           "git_remote_origin":"https://github.com/embecosm/mibench"},
                "coremark":{"path":str(coremark),"git_head":"c1",
                            "git_remote_origin":"https://github.com/eembc/coremark"},
            }
            p6a={
                "kind":"R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT",
                "verdict":p6d.P6A_VERDICT,
                "r3c_corpus_lock":"NOT_CREATED",
                "cases":[{
                    "case":name,"rv64_elf_sha256":"a"*64,
                    "argv":[],"input_files":[],
                    "expected_process_exit_code":0,
                    "correctness_gate":"RV64_QEMU_REFERENCE",
                    "original_g5_roi_sha256":"b"*64,
                } for name in p6d.EXPECTED_CASES],
            }
            p6b={
                "verdict":p6d.P6B_VERDICT,
                "p6a_sha256":"p6a hash",
                "corpus_lock":"NOT_AUTHORIZED",
                "prior_sources":[{} for _ in range(5)],
                "prior_exact_candidate_SHA_occurrences":[],
            }
            p6c={
                "verdict":p6d.P6C_VERDICT,
                "p6a_sha256":"p6a hash",
                "p6b_sha256":"p6b hash",
                "corpus_lock":"NOT_CREATED",
                "qualifying_untouched_holdout":"NOT_PROVEN",
                "historic_source_file_count":84,
                "historical_registries_recovered":[{} for _ in range(5)],
                "reference_file_count":0,
            }
            def mapped_source(header):
                return (mibench if header["path"]==str(mibench)
                        else coremark)
            with patch.object(p6d,"worktree",side_effect=mapped_source):
                row=p6d.dossier(
                    p1,p6a,p6b,p6c,
                    "p1 hash","p6a hash","p6b hash","p6c hash")
            self.assertEqual(len(row["source_and_licensing_records"]),11)
            self.assertEqual(sum(x["license_material_present"]
                                 for x in row["source_and_licensing_records"]),11)
            self.assertEqual(row["authorized_six_profile_holdout_runs"],0)
            self.assertEqual(row["r3c_corpus_lock"],"NOT_CREATED")

    def test_prelock_signoff_is_never_automatic(self):
        src=(ROOT/"scripts/bpu_b8_r3c_p6d_final_prelock_license_review.py").read_text()
        self.assertIn('"manual_license_review":"REQUIRED"',src)
        self.assertIn('"r3c_corpus_lock":"NOT_CREATED"',src)
        self.assertIn('"authorized_six_profile_holdout_runs":0',src)
        self.assertIn("NOT_CLAIMED_INTERNAL_10_ITERATION_ROI",src)

if __name__=="__main__":
    unittest.main()
