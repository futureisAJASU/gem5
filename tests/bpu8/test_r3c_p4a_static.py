#!/usr/bin/env python3
"""P4A R3C static SE adapter regression (does not invoke gem5)."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p4a_static as p4a


class P4AConfigContractTests(unittest.TestCase):
    def test_adapter_changes_only_three_io_interfaces(self):
        original=p4a.ORIGINAL_CONFIG.read_text()
        adapter=p4a.R3C_CONFIG.read_text()
        self.assertTrue(p4a.adapter_contract(original,adapter))
        compile(original,str(p4a.ORIGINAL_CONFIG),"exec")
        compile(adapter,str(p4a.R3C_CONFIG),"exec")

    def test_r3_original_not_requiring_stdin(self):
        self.assertNotIn("--program-stdin-file",p4a.ORIGINAL_CONFIG.read_text())
        self.assertIn("--program-stdin-file",p4a.R3C_CONFIG.read_text())

    def test_no_extra_non_io_config_mutation_allowed(self):
        original=p4a.ORIGINAL_CONFIG.read_text()
        changed=p4a.R3C_CONFIG.read_text().replace("1.4GHz","2.0GHz")
        with self.assertRaisesRegex(ValueError,"beyond explicit IO"):
            p4a.adapter_contract(original,changed)

    def test_p4a_expected_case_set_exactly_11(self):
        self.assertEqual(len(p4a.p2.ORDER),11)
        self.assertEqual(set(p4a.p3a.CASES)|set(p4a.p3b.CASES),set(p4a.p2.ORDER))

    def test_adpcm_stdin_case_contract_is_fixed(self):
        case=p4a.p3b.TASKS["adpcm_encode"]
        self.assertEqual(case["stdin"],"data/small.pcm")
        self.assertEqual(case["inputs"],["data/small.pcm"])

    def test_rijndael_encrypt_only_not_roundtrip_in_timing(self):
        self.assertEqual(p4a.p3a.KEY,
            "1234567890abcdeffedcba09876543211234567890abcdeffedcba0987654321")
        self.assertIn("rijndael_encrypt",p4a.p3a.CASES)
        self.assertNotIn("rijndael_encrypt",p4a.p3b.CASES)

    def test_patricia_nonzero_exit_is_explicitly_documented(self):
        self.assertIn("patricia",p4a.p3a.CASES)

if __name__=="__main__":
    unittest.main()
