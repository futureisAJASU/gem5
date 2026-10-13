#!/usr/bin/env python3
"""P5B deterministic G5 historical replay contract; no simulator execution."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p5b_g5_historical_replay as p5b
import bpu_b8_r3_g5_lock_full19 as r3

class HistoricalG5Tests(unittest.TestCase):
    def test_simulator_identity_separated_by_sha(self):
        self.assertEqual(len(p5b.CURRENT_SHA),64)
        self.assertEqual(len(p5b.HISTORICAL_SHA),64)
        self.assertNotEqual(p5b.CURRENT_SHA,p5b.HISTORICAL_SHA)

    def test_original_control_only(self):
        self.assertEqual(p5b.CONTROL,"g5_native")
        matrix=r3.load_matrix()
        self.assertEqual(len(matrix["workloads"]),19)
        self.assertEqual(matrix["profiles"]["g5_native"]["total_bits"],45736)

    def test_mandatory_deterministic_counters(self):
        for key in ("simTicks","simInsts","committedConditionalWrong",
                    "committedConditionalPredictions","storageBits",
                    "r3CauseJson","historyRestoreChecks",
                    "historyStateRestores"):
            self.assertIn(key,p5b.FIELDS)

    def test_never_compare_g5_tg7_in_replay(self):
        src=(ROOT/"scripts/bpu_b8_r3c_p5b_g5_historical_replay.py").read_text()
        self.assertIn('"compared_profiles":[]',src)
        self.assertIn('"holdout_jobs":0',src)
        self.assertNotIn('for profile in registry["profiles"]',src)

if __name__=="__main__":
    unittest.main()
