#!/usr/bin/env python3
"""Independent BPU-7 registry and negative-mutation tests (no simulation)."""
import copy
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "bpu_b7_sweep_preflight", ROOT / "scripts" / "bpu_b7_sweep_preflight.py"
)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)
MATRIX = ROOT / "docs" / "bpu7_sweep_matrix_v02.json"
CAMPAIGN = ROOT / "docs" / "BPU_B7_SWEEP_CAMPAIGN_V03_2026-10-08.md"
FAMILIES = {"C1": 3, "C2": 3, "C3": 6, "C4": 3, "C5": 3, "C7": 3}
WORKLOADS = {
    "aha-mont64", "crc32", "cubic", "edn", "huffbench",
    "matmult-int", "minver", "nbody", "nettle-aes", "nettle-sha256",
    "nsichneu", "picojpeg", "qrduino", "sglib-combined",
    "slre", "st", "statemate", "ud", "wikisort",
}


class Bpu7CandidateRegistryTests(unittest.TestCase):
    def setUp(self):
        self.matrix = json.loads(MATRIX.read_text(encoding="utf-8"))

    def test_all_six_serious_candidates_present_exactly(self):
        profiles, workloads = preflight.validate(self.matrix)
        self.assertEqual(Counter(p["family"] for p in profiles), FAMILIES)
        self.assertEqual(len(profiles) * len(workloads), 399)
        self.assertEqual(set(workloads), WORKLOADS)

    def test_new_imli_c7_has_three_capacity_levels(self):
        c7 = [p for p in self.matrix["profiles"] if p["family"] == "C7"]
        self.assertEqual({p["id"] for p in c7},
                         {"C7_E256", "C7_E512", "C7_E1024"})
        self.assertEqual([p["aux_bits_expected"] for p in c7],
                         [1289, 2569, 5129])

    def test_tagged_c3_has_three_points_in_each_mode(self):
        c3 = [p for p in self.matrix["profiles"] if p["family"] == "C3"]
        self.assertEqual(Counter(p["mode"] for p in c3),
                         {"PC_BIAS": 3, "HIST_TAG": 3})

    def test_gate_detects_c3_mode_imbalance(self):
        mutated = copy.deepcopy(self.matrix)
        c3 = [p for p in mutated["profiles"] if p["family"] == "C3"]
        c3[0]["mode"] = "HIST_TAG"
        with self.assertRaises(AssertionError):
            preflight.validate(mutated)

    def test_gate_detects_missing_new_c7(self):
        mutated = copy.deepcopy(self.matrix)
        mutated["profiles"] = [
            p for p in mutated["profiles"] if p["id"] != "C7_E1024"
        ]
        with self.assertRaises(AssertionError):
            preflight.validate(mutated)

    def test_gate_detects_profile_identity_swap(self):
        mutated = copy.deepcopy(self.matrix)
        first = next(p for p in mutated["profiles"] if p["id"] == "C7_E256")
        first["id"] = "C7_E128"
        with self.assertRaises(AssertionError):
            preflight.validate(mutated)

    def test_gate_detects_storage_forgery(self):
        mutated = copy.deepcopy(self.matrix)
        first = next(p for p in mutated["profiles"] if p["id"] == "C7_E512")
        first["aux_bits_expected"] += 1
        with self.assertRaises(AssertionError):
            preflight.validate(mutated)

    def test_gate_detects_unapproved_run(self):
        mutated = copy.deepcopy(self.matrix)
        mutated["execution_permitted"] = True
        with self.assertRaises(AssertionError):
            preflight.validate(mutated)

    def test_c6_and_a0_are_explicitly_deferred_not_lost(self):
        c = CAMPAIGN.read_text(encoding="utf-8")
        self.assertIn("C6", c)
        self.assertIn("A0 TAGE Access-Reduction Track", c)
        self.assertIn("not included in the 21", c)
        self.assertNotIn("C8", {p["family"] for p in self.matrix["profiles"]})


if __name__ == "__main__":
    unittest.main()
