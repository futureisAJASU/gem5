#!/usr/bin/env python3
"""Directed, simulator-free P3A evaluator regressions."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p3a_functional as p3a


def sample(rc=1, stdout_size=100, sha="a"*64, stderr_size=0, stderr_sha="b"*64):
    return {
        "returncode":rc,
        "stdout_size":stdout_size,
        "stdout_sha256":sha,
        "stderr_size":stderr_size,
        "stderr_sha256":stderr_sha,
    }


class P3ACorrectnessGateTests(unittest.TestCase):
    def test_patricia_upstream_exit_one_and_matched_output_allowed(self):
        self.assertTrue(p3a.patricia_ok(sample(),sample()))

    def test_patricia_exit_zero_not_silent_pass(self):
        self.assertFalse(p3a.patricia_ok(sample(rc=0),sample(rc=0)))

    def test_patricia_mismatched_output_rejected(self):
        self.assertFalse(p3a.patricia_ok(sample(),sample(sha="c"*64)))

    def test_patricia_empty_output_rejected(self):
        self.assertFalse(p3a.patricia_ok(sample(stdout_size=0),sample(stdout_size=0)))

    def test_patricia_stderr_rejected(self):
        self.assertFalse(p3a.patricia_ok(sample(stderr_size=1),sample(stderr_size=1)))

    def test_file_record_includes_sha_and_detects_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"input"
            self.assertFalse(p3a.file_record(f)["exists"])
            f.write_bytes(b"abc")
            rec=p3a.file_record(f)
            self.assertTrue(rec["exists"])
            self.assertEqual(rec["size"],3)
            self.assertEqual(rec["sha256"],"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__=="__main__":
    unittest.main()
