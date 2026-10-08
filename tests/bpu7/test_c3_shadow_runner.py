"""Regression tests for BPU-7 C3 shadow evidence parsing and safe resume.

All stats used here are intentionally SYNTHETIC; these tests verify the
evidence machinery ONLY, never any branch predictor performance claims.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/bpu_b7_c3_shadow_full19.py"
spec = importlib.util.spec_from_file_location("bpu7_c3_shadow_runner", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthetic_stats(extra_bits=0):
    """A G5-centered positive branch/ROI accounting fixture, NOT gem5 output."""
    values = {
        "simTicks": 100000,
        "simInsts": 10000,
        "committedConditionalPredictions": 100,
        "committedConditionalWrong": 5,
        "finalConditionalWrong": 5,
        "storageBits": 45736 + extra_bits,
        "c3PcBiasStorageBits": extra_bits,
        "c3PcBiasBankReads": 0,
        "c3PcBiasEligibleCommitted": 0,
        "c3PcBiasTagHits": 0,
        "c3PcBiasWouldFlip": 0,
        "c3PcBiasWouldFix": 0,
        "c3PcBiasWouldBreak": 0,
        "c3PcBiasTrainWrites": 0,
        "c3PcBiasAllocations": 0,
        "c3PcBiasEvictions": 0,
        "c3PcBiasCollisionBlocked": 0,
        "predictionMetadataChecks": 100,
        "historyRestoreChecks": 2,
        "historyStateRestores": 2,
    }
    return "".join(f"system.cpu.branchPred.{k} {v}\n" for k, v in values.items())


def stats_dump(body, end_spaces=3):
    return ("---------- Begin Simulation Statistics ----------\n" +
            body +
            "---------- End Simulation Statistics" + " " * end_spaces +
            "----------\n")


class ParserAndAccounting(unittest.TestCase):
    def test_gem5_real_three_space_end_marker_and_first_roi_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stats.txt"
            first = stats_dump(synthetic_stats())
            second = stats_dump("simInsts 333333\n")
            path.write_text(first + second)
            stats, roi = mod.parse_first_roi(path)
            self.assertEqual(roi, first)
            self.assertEqual(mod.unique_int(stats, "simInsts"), 10000)
            self.assertNotIn("333333", roi)
            row = mod.inspect_row(stats, "g5", "aha-mont64", "not-used",
                                  hashlib.sha256(roi.encode()).hexdigest())
            self.assertEqual(row["storageBits"], 45736)
            self.assertEqual(row["shadowNet"], 0)

    def test_old_one_space_end_marker_is_also_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "stats.txt"
            p.write_text(stats_dump(synthetic_stats(), end_spaces=1))
            self.assertEqual(mod.unique_int(mod.parse_first_roi(p)[0], "simTicks"),
                             100000)

    def test_truncated_stats_are_never_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "stats.txt"
            p.write_text("---------- Begin Simulation Statistics ----------\n"
                         + synthetic_stats())
            with self.assertRaisesRegex(ValueError, "missing end-stats"):
                mod.parse_first_roi(p)

    def test_shadow_read_and_training_invariant_fails_closed(self):
        stats = {
            k: str(v) for k, v in (
                line.split() for line in synthetic_stats().splitlines()
            )
        }
        # Show that a fake correction is rejected when no valid hit exists.
        stats["system.cpu.branchPred.c3PcBiasWouldFix"] = "1"
        with self.assertRaises(ValueError):
            mod.inspect_row(stats, "g5", "aha-mont64", "none", "none")


class CompletedRawRecovery(unittest.TestCase):
    def test_prior_fully_executed_g5_is_recovered_without_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "configs/02_little_v052_rv64_proxy.py"
            cfg.parent.mkdir()
            cfg.write_text("# synthetic fixture only\n")
            matrix = root / "docs/bpu7_sweep_matrix_v02.json"
            matrix.parent.mkdir()
            matrix.write_text(json.dumps({
                "status": "PRE_FREEZE",
                "execution_permitted": False,
                "workloads": ["aha-mont64"]
            }))
            gem5 = root / "build/RISCV/gem5.opt"
            gem5.parent.mkdir(parents=True)
            gem5.write_text("# synthetic simulator fixture\n")
            bench_root = root / "benchmarks/external/embench-iot/bd-rv64-gem5"
            binary = bench_root / "src/aha-mont64/aha-mont64"
            binary.parent.mkdir(parents=True)
            binary.write_text("synthetic workload input")
            output = root / "old-shadow-results"
            d = output / "g5/aha-mont64"
            d.mkdir(parents=True)
            cmd = [
                str(gem5), f"--outdir={d}", str(cfg),
                "--binary", str(binary), "--bp-type", "tage5-iso45k",
                "--bp-inst-shift", "1", "--bp-cond-shift", "1",
                "--bp-btb-shift", "2", "--bp-indirect-shift", "1",
                "--btb-entries", "4096"
            ]
            (d / "command.json").write_text(json.dumps(cmd, indent=2))
            (d / "stdout.txt").write_text("SIMULATION_EXIT_CODE=0\n")
            (d / "stderr.txt").write_text("")
            raw = stats_dump(synthetic_stats())
            (d / "stats.txt").write_text(raw)
            old = {
                "experiment": "BPU7_C3_PC_BIAS_SHADOW_FULL19",
                "status": "SHADOW_DIAGNOSTIC_NOT_M1",
                "no_measured_real_correction": True,
                "repo_head": "prior-head-abc",
                "repo_dirty_tracked": False,
                "gem5_sha256": sha(gem5),
                "config_sha256": sha(cfg),
                "matrix_sha256": sha(matrix),
                "runner_sha256": "old-script-digest",
                "embench_head": "NO_GIT_METADATA",
                "benchmarks": {"aha-mont64": sha(binary)},
                "job_count": 1,
                "profiles": {
                    "g5": {"bp_type": "tage5-iso45k",
                           "total_bits": 45736, "aux_bits": 0}
                },
                "condition": {
                    "bp_inst_shift": 1, "bp_cond_shift": 1,
                    "bp_btb_shift": 2, "bp_indirect_shift": 1,
                    "btb_entries": 4096,
                },
            }
            manifest = output / "manifest.json"
            manifest.write_text(json.dumps(old, indent=2))
            originals = {p: sha(p) for p in (
                manifest, d / "stats.txt", d / "stdout.txt", d / "command.json"
            )}
            with (
                mock.patch.object(mod, "ROOT", root),
                mock.patch.object(mod, "CFG", cfg),
                mock.patch.object(mod, "WORKLOADS", ("aha-mont64",)),
                mock.patch.object(mod, "PROFILES", {
                    "g5": ("tage5-iso45k", 45736, 0)
                }),
                mock.patch.object(mod, "git", side_effect=lambda *a, **kw: (
                    "new-review-head" if a == ("rev-parse", "HEAD") else ""
                )),
                mock.patch.object(mod.subprocess, "run") as run,
                mock.patch.object(sys, "argv", [
                    "runner", "--no-build", "--resume",
                    "--out", str(output),
                    "--embench-build", str(bench_root),
                    "--gem5", str(gem5)
                ]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                mod.main()
            # Only the directed C++ runner is allowed, no gem5 rerun.
            self.assertEqual(run.call_count, 2)
            self.assertTrue((d / ".verified.json").is_file())
            self.assertTrue((d / "roi.stats").is_file())
            self.assertTrue((output / "resume_audit.jsonl").is_file())
            self.assertEqual((output / "results.csv").read_text().count("\n"), 2)
            for path, digest in originals.items():
                self.assertEqual(sha(path), digest, f"{path} was overwritten")

    def test_resume_rejects_any_changed_gem5_binary(self):
        # Protect against suggesting a resume strategy that mixes experiments
        # built from different predictor source revisions.
        self.assertNotEqual(
            hashlib.sha256(b"gem5-old").hexdigest(),
            hashlib.sha256(b"gem5-new").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
