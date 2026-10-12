#!/usr/bin/env python3
"""G5-only R3C SE feasibility synthetic tests (zero simulator work)."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p4b_g5_se_feasibility as gate
import bpu_b8_r3c_p2_build as p2


class G5OnlySETests(unittest.TestCase):
    def test_only_g5_control_is_runnable(self):
        self.assertEqual(gate.EXPECTED_CONTROL,"g5_native")
        self.assertEqual(tuple(gate.ORDER),tuple(p2.ORDER))

    def test_command_has_fixed_geometry_and_explicit_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            case=dict(binary=str(root/"x.elf"), argv=["-e","some input.dat"],
                      stdin_file_relative="data/small.pcm")
            c=gate.build_command(root/"gem5.opt",root/"adapter.py",
                                 case,root/"sim",root/"work",
                                 {"bp_type":"tage-r3-native-tg5-45"})
            self.assertIn("--bp-type",c)
            self.assertEqual(c[c.index("--bp-type")+1],"tage-r3-native-tg5-45")
            self.assertIn("--program-arg=-e",c)
            self.assertIn("--program-arg=some input.dat",c)
            self.assertEqual(len([x for x in c if x.startswith("--program-stdin-file=")]),1)
            self.assertEqual(len([x for x in c if x.startswith("--program-stdout-file=")]),1)
            self.assertEqual(len([x for x in c if x.startswith("--program-stderr-file=")]),1)
            self.assertFalse(any("tg7" in x or "tg6" in x or "h11" in x for x in c))

    def test_extract_se_exit_requires_single_status(self):
        self.assertEqual(gate.extract_sim_exit(
            "SIMULATION_EXIT_CAUSE=exiting because last active thread context exited\n"
            "SIMULATION_EXIT_CODE=1\n"),1)
        with self.assertRaisesRegex(ValueError,"missing/duplicate"):
            gate.extract_sim_exit("SIMULATION_EXIT_CODE=1\nSIMULATION_EXIT_CODE=0\n")
        with self.assertRaisesRegex(ValueError,"missing/duplicate"):
            gate.extract_sim_exit("SIMULATION_EXIT_CAUSE=foo\n")

    def test_exact_output_comparison(self):
        self.assertTrue(gate.compare_program(
            "qsort",b"sorted\n",b"",b"sorted\n",b"",None,None)["passed"])
        self.assertFalse(gate.compare_program(
            "qsort",b"not sorted\n",b"",b"sorted\n",b"",None,None)["passed"])

    def test_file_outputs_must_match_qemu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ref=root/"ref"
            out=root/"out"
            ref.write_bytes(b"ciphertext1")
            out.write_bytes(b"ciphertext1")
            self.assertTrue(gate.compare_program(
                "rijndael_encrypt",b"",b"",b"",b"",ref,out)["passed"])
            out.write_bytes(b"ciphertext2")
            self.assertFalse(gate.compare_program(
                "rijndael_encrypt",b"",b"",b"",b"",ref,out)["passed"])

    def test_missing_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a=root/"ref"
            a.write_bytes(b"ref")
            self.assertFalse(gate.compare_program(
                "susan_edges",b"",b"",b"",b"",a,root/"not_exists")["passed"])

    def test_qemu_reference_hash_must_match_audited_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            file=root/"patricia.rv64.stdout"
            err=root/"patricia.rv64.stderr"
            file.write_bytes(b"Found.\n")
            err.write_bytes(b"")
            ref={"observations":[{
                "id":"patricia.rv64",
                "stdout_sha256":p2.sha(file),"stdout_size":file.stat().st_size,
                "stderr_sha256":p2.sha(err),"stderr_size":0}]}
            self.assertEqual(gate.reference_paths("patricia",root,root,ref)["stdout"],file)
            file.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError,"reference changed"):
                gate.reference_paths("patricia",root,root,ref)

if __name__=="__main__":
    unittest.main()
