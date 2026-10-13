#!/usr/bin/env python3
"""P5A split RAW evidence fail-closed contract tests; no gem5 execution."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p5a_split_raw_audit as p5

class P5ASplitTests(unittest.TestCase):
    def test_partition_matches_prereg(self):
        self.assertEqual(len(p5.FIRST),8)
        self.assertEqual(len(p5.LAST),3)
        self.assertEqual(p5.FIRST+p5.LAST,tuple(p5.p2.ORDER))
        self.assertFalse(set(p5.FIRST)&set(p5.LAST))

    def test_exact_original_console_order(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"log"
            path.write_text("".join("R3C_P4B_G5_ONLY "+name+": PASS\n" for name in p5.FIRST))
            self.assertEqual(p5.console_passes(path),list(p5.FIRST))

    def test_fail_marker_not_counted(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"log"
            path.write_text("R3C_P4B_G5_ONLY qsort: FAIL\n"
                            "R3C_P4B_G5_ONLY patricia: PASS\n")
            self.assertEqual(p5.console_passes(path),["patricia"])

    def test_missing_console_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"missing original console"):
                p5.console_passes(Path(td)/"not-there")

    def test_new_simulator_identity_is_pinned(self):
        self.assertEqual(len(p5.EXPECTED_GEM5),64)
        self.assertEqual(p5.EXPECTED_GEM5,
                         "12681de7975d5082b64dee6e085585dbbd1d078fa7be7f477f4553ab98344a1a")

    def test_absent_first_manifest_is_explicitly_supported(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(p5.manifest(Path(td)/"missing.json"))

    def test_complete_first_console_is_full_evidence(self):
        self.assertTrue(p5.validate_interrupted_console(list(p5.FIRST),False))
        self.assertTrue(p5.validate_interrupted_console(list(p5.FIRST),True))

    def test_truncated_console_default_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"first interrupted console incomplete"):
            p5.validate_interrupted_console(list(p5.FIRST[:7]),False)

    def test_truncated_console_requires_explicit_downgrade(self):
        self.assertFalse(p5.validate_interrupted_console(list(p5.FIRST[:7]),True))
        self.assertFalse(p5.validate_interrupted_console([],True))

    def test_fabricated_extra_case_fails_even_with_downgrade(self):
        with self.assertRaisesRegex(ValueError,"unexpected, duplicated"):
            p5.validate_interrupted_console(list(p5.FIRST[:7])+["unknown"],True)
        with self.assertRaisesRegex(ValueError,"unexpected, duplicated"):
            p5.validate_interrupted_console(["qsort","basicmath"],True)
        with self.assertRaisesRegex(ValueError,"unexpected, duplicated"):
            p5.validate_interrupted_console(["qsort","qsort"],True)

if __name__=="__main__":
    unittest.main()
