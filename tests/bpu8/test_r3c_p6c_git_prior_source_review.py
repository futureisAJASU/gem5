#!/usr/bin/env python3
"""Bounded pre-R3C Git historical source inventory; no simulator runs."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p6c_git_prior_source_review as p6c

class PriorSourceAuditTests(unittest.TestCase):
    def fixture(self):
        a={
          "verdict":p6c.P6A_VERDICT,
          "r3c_corpus_lock":"NOT_CREATED",
          "historical_unseen_workload_independence":"UNVERIFIED",
        }
        b={
          "verdict":p6c.P6B_VERDICT,
          "corpus_lock":"NOT_AUTHORIZED",
          "independence_of_11_cases":"NOT_DETERMINED",
          "prior_sources":[{"root":"/history/R1"}],
        }
        paths={p:json.dumps({"workloads":["crc32","qrduino"],
                             "experiment":"BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01"})
               for p in p6c.ANCIENT_REGISTRIES}
        for i in range(12):
            paths[f"scripts/bpu_test_{i}.sh"]='EMBENCH_DIR="embench-iot"\n'
        old={"experiment":"BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01",
             "workloads":["crc32","qrduino"]+[f"embench_{x}" for x in range(17)]}
        return a,b,paths,old

    def test_unchanged_historical_registries_are_not_holdout(self):
        a,b,paths,old=self.fixture()
        x=p6c.stage(a,b,paths,old)
        self.assertEqual(x["historic_bpu_scripts_reviewed"],12)
        self.assertEqual(len(x["historical_registries_recovered"]),5)
        self.assertEqual(x["historic_source_file_count"],17)

    def test_history_source_mentions_do_not_silently_disappear(self):
        hits=p6c.corpus_refs('RUN "basicmath" --branch-predictor mibench;')
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]["candidate_names"],["basicmath"])
        self.assertEqual(hits[0]["source_roots"],["mibench"])
        self.assertEqual(p6c.corpus_refs("basicmathematics unchanged"),[])

    def test_historical_registry_contamination_fails(self):
        a,b,paths,old=self.fixture()
        old["workloads"][0]="basicmath"
        with self.assertRaisesRegex(ValueError,"R3 exact workload name"):
            p6c.stage(a,b,paths,old)

    def test_missing_registry_must_not_pass(self):
        a,b,paths,old=self.fixture()
        del paths[p6c.ANCIENT_REGISTRIES[2]]
        with self.assertRaisesRegex(ValueError,"required five"):
            p6c.stage(a,b,paths,old)

    def test_not_six_profile_result_and_no_corpus_lock(self):
        text=(ROOT/"scripts/bpu_b8_r3c_p6c_git_prior_source_review.py").read_text()
        self.assertIn('"qualifying_untouched_holdout":"NOT_PROVEN"',text)
        self.assertIn('"corpus_lock":"NOT_CREATED"',text)
        self.assertIn('"authorized_six_profile_jobs":0',text)

if __name__=="__main__":
    unittest.main()
