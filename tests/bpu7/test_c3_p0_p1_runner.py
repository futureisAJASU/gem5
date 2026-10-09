"""Synthetic harness-only checks. NO synthetic values are reported as ROI data."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/bpu_b7_c3_p0_p1_full19.py"
spec = importlib.util.spec_from_file_location("bpu7_c3_p0_p1_full19", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def fixture(profile):
    total, extra = runner.PROFILES[profile][1:]
    is_p0 = profile.startswith("p0_")
    is_p1 = profile.startswith("p1_")
    data = {
        "simTicks": 100000, "simInsts": 10000,
        "committedConditionalPredictions": 100,
        "committedConditionalWrong": 5 if profile != "g7" else 4,
        "finalConditionalWrong": 5 if profile != "g7" else 4,
        "storageBits": total,
        "c3PcBiasStorageBits": extra if is_p0 else 0,
        "c3PcChooserStorageBits": extra if is_p1 else 0,
        "predictionMetadataChecks": 100,
        "historyRestoreChecks": 2, "historyStateRestores": 2,
        "c3PcBiasBankReads": 100 if is_p0 else 0,
        "c3PcBiasEligibleCommitted": 80 if is_p0 else 0,
        "c3PcBiasTagHits": 70 if is_p0 else 0,
        "c3PcBiasWouldFlip": 4 if is_p0 else 0,
        "c3PcBiasWouldFix": 3 if is_p0 else 0,
        "c3PcBiasWouldBreak": 1 if is_p0 else 0,
        "c3PcBiasTrainWrites": 78 if is_p0 else 0,
        "c3PcBiasAllocations": 4 if is_p0 else 0,
        "c3PcBiasEvictions": 2 if is_p0 else 0,
        "c3PcBiasCollisionBlocked": 2 if is_p0 else 0,
        "c3PcChooserReads": 100 if is_p1 else 0,
        "c3PcChooserEligibleCommitted": 80 if is_p1 else 0,
        "c3PcChooserTagHits": 65 if is_p1 else 0,
        "c3PcChooserDisagreements": 20 if is_p1 else 0,
        "c3PcChooserWouldOverride": 3 if is_p1 else 0,
        "c3PcChooserWouldFix": 2 if is_p1 else 0,
        "c3PcChooserWouldBreak": 1 if is_p1 else 0,
        "c3PcChooserRowWrites": 80 if is_p1 else 0,
        "c3PcChooserDirectionUpdates": 70 if is_p1 else 0,
        "c3PcChooserChooserUpdates": 6 if is_p1 else 0,
        "c3PcChooserAllocations": 8 if is_p1 else 0,
        "c3PcChooserEvictions": 3 if is_p1 else 0,
        "c3PcChooserCollisionBlocked": 2 if is_p1 else 0,
        "c3PcChooserStalePredictions": 1 if is_p1 else 0,
    }
    return {"system.cpu.branchPred.tage." + k: str(v) for k, v in data.items()}


class Full19Harness(unittest.TestCase):
    def test_complete_enumeration_is_152(self):
        self.assertEqual(len(runner.WORKLOADS), 19)
        self.assertEqual(len(runner.PROFILES), 8)
        self.assertEqual(len(runner.WORKLOADS) * len(runner.PROFILES), 152)
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--list"],
            capture_output=True, text=True, check=True
        )
        self.assertIn("SHADOW_ONLY_ROI_PLAN=152; M1_CORRECTION=NOT_IMPLEMENTED",
                      p.stdout)
        self.assertEqual(len(p.stdout.splitlines()), 153)

    def test_real_gem5_triple_space_marker_and_first_roi(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stats.txt"
            body = "\n".join(f"{key} {value}" for key, value in fixture("p1_e128").items())
            head = "---------- Begin Simulation Statistics ----------\n"
            tail = "---------- End Simulation Statistics   ----------\n"
            path.write_text(head + body + "\n" + tail +
                            head + "simInsts 99999\n" + tail)
            stats, roi = runner.parse_first_roi(path)
            self.assertEqual(runner.unique_int(stats, "simInsts"), 10000)
            self.assertEqual(roi, head + body + "\n" + tail)

    def test_missing_end_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stats.txt"
            path.write_text("---------- Begin Simulation Statistics ----------\n" +
                            "simTicks 1000\n")
            with self.assertRaisesRegex(ValueError, "missing end"):
                runner.parse_first_roi(path)

    def test_eight_profiles_state_and_accounting(self):
        for profile in runner.PROFILES:
            with self.subTest(profile=profile):
                row = runner.inspect_row(fixture(profile), profile,
                                         "aha-mont64", "fixture-digest", "roi-hash")
                self.assertEqual(row["storageBits"], runner.PROFILES[profile][1])
                if profile.startswith("p0_"):
                    self.assertEqual(row["shadowNet"], 2)
                elif profile.startswith("p1_"):
                    self.assertEqual(row["shadowNet"], 1)
                else:
                    self.assertEqual(row["shadowNet"], 0)

    def test_shadow_errors_fail_closed(self):
        cases = (
            ("p0_e128", "c3PcBiasWouldBreak", "8", "fix/break"),
            ("p0_e128", "c3PcBiasCollisionBlocked", "10", "training"),
            ("p1_e128", "c3PcChooserRowWrites", "79", "training"),
            ("p1_e128", "c3PcChooserChooserUpdates", "25", "chooser"),
            ("p1_e128", "c3PcChooserStorageBits", "2048", "bits"),
            ("g5", "c3PcChooserReads", "1", "auxiliary"),
        )
        for profile, key, value, message in cases:
            with self.subTest(profile=profile, key=key):
                stat = fixture(profile)
                stat["system.cpu.branchPred.tage." + key] = value
                with self.assertRaisesRegex(ValueError, message):
                    runner.inspect_row(stat, profile, "aha-mont64", "-", "-")

    def test_exact_stats_suffix_rejects_ambiguous_members(self):
        d = {"some.storageBits": "100", "other.storageBits": "200"}
        with self.assertRaisesRegex(ValueError, "one stat storageBits"):
            runner.unique_int(d, "storageBits")


if __name__ == "__main__":
    unittest.main()
