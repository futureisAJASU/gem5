#!/usr/bin/env python3
"""Synthetic UNIT tests only: never confuse generated rows with gem5 results.

Run: python3 -m unittest discover -s tests/bpu7 -p 'test_*.py' -v
"""
import csv
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "bpu_b7_round1_result_gate", ROOT / "scripts" / "bpu_b7_round1_result_gate.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

FIELDNAMES = [
    "profile", "workload", "cycles", "insts", "committed", "base_wrong",
    "final_wrong", "fixes", "breaks", "overrides", "total_bits", "bp_reads",
    "bp_writes", "m1_verified", "test_gate_pass", "run_sha",
    "artifact_sha256", "artifact_path",
]
PROFILES = ["C1_E64"]
W = ["aha-mont64"]
BITS = {"R0": 45736, "R1": 65192, "C1_E64": 48168}


class Round1ResultGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / "result.csv"
        data = [
            ("R0", 1000, 45736, 2, 2, 0, 0, 0, 0),
            ("R1", 990, 65192, 1, 1, 0, 0, 0, 0),
            ("C1_E64", 995, 48168, 2, 1, 1, 0, 1, 1),
        ]
        self.rows = []
        for name, cycle, bits, base, final, fixes, breaks, overrides, m1 in data:
            artifact = f"{name}/aha-mont64/roi.stats"
            p = self.root / artifact
            p.parent.mkdir(parents=True)
            p.write_text("synthetic unit-only evidence " + name, encoding="utf-8")
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            self.rows.append(dict(
                profile=name, workload="aha-mont64", cycles=cycle, insts=100,
                committed=10, base_wrong=base, final_wrong=final, fixes=fixes,
                breaks=breaks, overrides=overrides, total_bits=bits,
                bp_reads=30, bp_writes=3, m1_verified=m1, test_gate_pass="PASS",
                run_sha="a" * 40, artifact_sha256=digest, artifact_path=artifact
            ))
        self._write()

    def _write(self):
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(self.rows)

    def _read(self):
        return gate.read_results(self.csv, PROFILES, W, BITS)

    def test_valid_synthetic_three_rows(self):
        rows = self._read()
        self.assertEqual(len(rows), 3)
        result = gate.aggregate(rows, ["R0", "R1", "C1_E64"], W)
        c1 = next(r for r in result if r["profile"] == "C1_E64")
        self.assertAlmostEqual(c1["g5_geomean_pct"], -0.5)
        self.assertEqual(c1["net_fixes"], 1)

    def test_missing_profile_blocked(self):
        self.rows.pop()
        self._write()
        with self.assertRaisesRegex(ValueError, "INCOMPLETE"):
            self._read()

    def test_wrong_accounting_blocked(self):
        self.rows[-1]["breaks"] = 1
        self._write()
        with self.assertRaisesRegex(ValueError, "overrides"):
            self._read()

    def test_missing_m1_blocked(self):
        self.rows[-1]["m1_verified"] = 0
        self._write()
        with self.assertRaisesRegex(ValueError, "M1 latency"):
            self._read()

    def test_invalid_storage_blocked(self):
        self.rows[-1]["total_bits"] += 1
        self._write()
        with self.assertRaisesRegex(ValueError, "storage mismatch"):
            self._read()

    def test_missing_roi_file_blocked(self):
        (self.root / self.rows[-1]["artifact_path"]).unlink()
        with self.assertRaisesRegex(ValueError, "artifact missing"):
            self._read()

    def test_tampered_roi_file_blocked(self):
        (self.root / self.rows[-1]["artifact_path"]).write_text("tampered")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self._read()

    def test_mixed_source_commits_blocked(self):
        self.rows[-1]["run_sha"] = "b" * 40
        self._write()
        with self.assertRaisesRegex(ValueError, "commit mismatch"):
            self._read()

    def test_duplicate_artifact_blocked(self):
        self.rows[-1]["artifact_path"] = self.rows[0]["artifact_path"]
        self.rows[-1]["artifact_sha256"] = self.rows[0]["artifact_sha256"]
        self._write()
        with self.assertRaisesRegex(ValueError, "reused"):
            self._read()


if __name__ == "__main__":
    unittest.main()
