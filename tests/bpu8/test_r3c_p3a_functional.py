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


class P2BChainedSHAIntegrityTests(unittest.TestCase):
    """Synthetic P2B sidecar fixtures; do not modify source checkouts."""

    def make_journal(self, temp: Path):
        pristine = temp / "external_mibench"
        sidecar = temp / "p2b"
        stage_root = sidecar / "overlay_source" / "mibench"
        originals = {
            "network/patricia/patricia_test.c": b"unused_rpc",
            "security/rijndael/aes.h": b"unsigned_long",
            "security/rijndael/aesxam.c":
                b"orig1|orig2|orig3|orig4|orig5",
        }
        for rel, data in originals.items():
            src, staged = pristine / rel, stage_root / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            staged.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(data)
            staged.write_bytes(data)
        transitions = [
            (b"unused_rpc", b"removed_rpc"),
            (b"unsigned_long", b"uint32_t"),
            (b"orig1", b"new1"),
            (b"orig2", b"new2"),
            (b"orig3", b"new3"),
            (b"orig4", b"new4"),
            (b"orig5", b"new5"),
        ]
        patches = []
        for rel, (old, new) in zip(
                p3a.EXPECTED_PATCH_PATHS, transitions, strict=True):
            target = stage_root / rel
            before = target.read_bytes()
            after = before.replace(old, new, 1)
            import hashlib
            patches.append({
                "file": str(target),
                "source_sha256": hashlib.sha256(before).hexdigest(),
                "patched_sha256": hashlib.sha256(after).hexdigest(),
                "old": old.decode(),
                "new": new.decode(),
            })
            target.write_bytes(after)
        return patches, sidecar, pristine, stage_root

    def test_all_seven_chained_sha_transitions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            self.assertIsNone(p3a.validate_patch_journal(records, root, original))
            self.assertEqual(
                (original/"security/rijndael/aesxam.c").read_bytes(),
                b"orig1|orig2|orig3|orig4|orig5")

    def test_corrupt_intermediate_predecessor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            records[3]["source_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "predecessor SHA mismatch"):
                p3a.validate_patch_journal(records, root, original)

    def test_corrupt_intermediate_successor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            records[2]["patched_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "successor SHA mismatch"):
                p3a.validate_patch_journal(records, root, original)

    def test_tampered_final_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            f = stage / "security/rijndael/aesxam.c"
            f.write_bytes(f.read_bytes() + b" extra")
            with self.assertRaisesRegex(ValueError, "final staged source mismatch"):
                p3a.validate_patch_journal(records, root, original)

    def test_wrong_file_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            records[0]["file"] = str(stage / "security/rijndael/aes.h")
            with self.assertRaisesRegex(ValueError, "path mismatch"):
                p3a.validate_patch_journal(records, root, original)

    def test_unexpected_extra_patch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, root, original, stage = self.make_journal(Path(tmp))
            records.append(dict(records[-1]))
            with self.assertRaisesRegex(ValueError, "seven explicit"):
                p3a.validate_patch_journal(records, root, original)


if __name__=="__main__":
    unittest.main()
