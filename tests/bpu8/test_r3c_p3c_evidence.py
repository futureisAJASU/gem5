#!/usr/bin/env python3
"""P3C evidence snapshot integrity gates, synthetic regression. No gem5 simulation."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p3c_evidence as p3c
import bpu_b8_r3c_p2_build as p2


class P3CEvidenceTests(unittest.TestCase):
    def test_exact_fixed_case_partition(self):
        self.assertEqual(len(p3c.EXPECTED), 11)
        self.assertEqual(set(p3c.P3A_CASES).intersection(p3c.P3B_CASES), set())
        self.assertEqual(set(p3c.P3A_CASES).union(p3c.P3B_CASES),
                         set(p3c.EXPECTED))
        self.assertEqual(len(p3c.P3B_CASES),9)

    def test_observation_hash_is_rechecked_against_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"case.stdout").write_bytes(b"known data")
            (root/"case.stderr").write_bytes(b"")
            row={"id":"case", "returncode":0,
                 "stdout_sha256":p2.sha(root/"case.stdout"),
                 "stderr_sha256":p2.sha(root/"case.stderr"),
                 "stdout_size":10, "stderr_size":0}
            self.assertEqual(
                p3c.inspect_observation(row,root)["stdout_size"],10)
            (root/"case.stdout").write_bytes(b"other data")
            with self.assertRaisesRegex(ValueError, "observation SHA mismatch"):
                p3c.inspect_observation(row,root)

    def test_missing_observation_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "missing observation"):
                p3c.inspect_observation({"id":"case"},Path(td))

    def test_path_escape_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "escapes"):
                p3c.absolute_within(Path("/etc/hosts"),Path(td))

    def test_invalid_observation_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"invalid run id"):
                p3c.inspect_observation({"id":"../attack"}, Path(td))


if __name__=="__main__":
    unittest.main()
