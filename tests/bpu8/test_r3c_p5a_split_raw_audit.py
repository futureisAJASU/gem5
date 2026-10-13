#!/usr/bin/env python3
"""P5A split RAW evidence fail-closed contract tests; no gem5 execution."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p5a_split_raw_audit as p5

class P5ASplitTests(unittest.TestCase):
    def test_recheck_one_reads_json_str_binary_path_through_real_hasher(self):
        """Real p2.sha(Path) of staged ELF, full recheck return, no gem5 run."""
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            case="basicmath"
            elf=root/"binary.rv64.elf"
            elf.write_bytes(b"ELF dummy bytes")
            case_root=root/case
            work=case_root/"work"
            sim=case_root/"sim"
            work.mkdir(parents=True)
            sim.mkdir()
            (work/"program.stdout").write_bytes(b"verified program output")
            (work/"program.stderr").write_bytes(b"")
            (work/"input.dat").write_bytes(b"unaltered input")
            (case_root/"gem5.stdout").write_text(
                "SIMULATION_EXIT_CAUSE=exiting\nSIMULATION_EXIT_CODE=0\n")
            (case_root/"gem5.stderr").write_text("gem5 stderr")
            (sim/"roi.stats").write_text("ORIGINAL FIRST ROI\n")
            (sim/"stats.txt").write_text("RAW original stats\n")
            (sim/"config.ini").write_text("original config")
            (case_root/"command.json").write_text(json.dumps({
                "argv":["fixed","cmd"],"cwd":str(work),"expected_exit":0}))
            golden=root/"reference.stdout"
            golden.write_bytes(b"verified program output")
            referr=root/"reference.stderr"
            referr.write_bytes(b"")
            row={
                "simTicks":1000, "simInsts":100,
                "storageBits":45736,
                "committedConditionalPredictions":27,
                "committedConditionalWrong":3,
                "mpki":"30.000000000",
                "r3CauseJson":"{}",
                "historyRestoreChecks":4,
                "historyStateRestores":4,
            }
            plan={"cases":{case:{
                "binary":str(elf),
                "binary_sha256":p5.p2.sha(elf),
                "expected_process_exit_code":0,
                "argv":[],
                "input_files":[{
                    "name":"input.dat","size":len(b"unaltered input"),
                    "sha256":p5.p2.sha(work/"input.dat")}],
                "reference":{},
                "program_output_file_relative":None
            }}}
            snapshot={
                "pass":True,
                "status":"G5_SE_FUNCTIONAL_ROI_PASS_NO_COMPARISON",
                "gem5_runner_rc":0,
                "timeout":False,
                "simulated_exit_code":0,
                "raw":{f:p5.p2.sha(sim/f) for f in
                       ("stats.txt","roi.stats","config.ini")},
                "roi_inspect_sha256":hashlib.sha256(
                    json.dumps(row,sort_keys=True).encode()).hexdigest(),
                "gem5_stdout_sha256":p5.p2.sha(case_root/"gem5.stdout"),
                "gem5_stderr_sha256":p5.p2.sha(case_root/"gem5.stderr"),
            }
            with (patch.object(p5.p4b,"build_command",return_value=["fixed","cmd"]),
                  patch.object(p5.p4b,"reference_paths",return_value={
                      "stdout":golden,"stderr":referr}),
                  patch.object(p5.p4b,"expected_output_file",return_value=None),
                  patch.object(p5.p4b,"compare_program",return_value={
                      "passed":True}),
                  patch.object(p5.r3,"load_matrix",return_value={
                      "profiles":{"g5_native":{}}}),
                  patch.object(p5.r3,"validate_r3_ini",return_value=True),
                  patch.object(p5.r3,"parse_first_roi",return_value=(
                      {"dummy":"1"},"ORIGINAL FIRST ROI\n")),
                  patch.object(p5.r3,"inspect_row",return_value=row)):
                result=p5.recheck_one(
                    case,root,plan,{},root/"gem5.opt",
                    root/"reference_a",root/"reference_b",snapshot)
            self.assertTrue(result["passed"])
            self.assertEqual(result["simTicks"],1000)
            self.assertEqual(result["elf_sha256"],p5.p2.sha(elf))
            self.assertEqual(result["roi_sha256"],p5.p2.sha(sim/"roi.stats"))
            self.assertEqual(result["runner_evidence"],
                             "verified_runner_manifest_and_original_RAW")

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

    def test_explicit_negative_console_witness_detected(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"log"
            file.write_text("R3C_P4B_G5_ONLY qsort: FAIL\n"
                            "R3C_P4B_G5_ONLY patricia: PASS\n")
            self.assertEqual(p5.console_failures(file),["qsort"])

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

    def test_surviving_original_full11_is_primary_evidence(self):
        full=list(p5.FIRST+p5.LAST)
        manifest={"verdict":"G5_ONLY_FEASIBILITY_PASS_NO_CORPUS_LOCK",
                  "attempted_cases":full,
                  "cases":{name:{"pass":True} for name in full}}
        self.assertEqual(p5.classify_original_run(full,manifest,False),
                         "FULL11_COMPLETE_ORIGINAL")
        self.assertEqual(p5.classify_original_run(full,manifest,True),
                         "FULL11_COMPLETE_ORIGINAL")

    def test_full11_requires_real_completed_manifest(self):
        full=list(p5.FIRST+p5.LAST)
        with self.assertRaisesRegex(ValueError,"manifest absent"):
            p5.classify_original_run(full,None,False)
        with self.assertRaisesRegex(ValueError,"manifest absent"):
            p5.classify_original_run(full,None,True)
        with self.assertRaisesRegex(ValueError,"not PASS"):
            p5.classify_original_run(full,{
                "verdict":"INCOMPLETE_OR_G5_FEASIBILITY_FAIL",
                "attempted_cases":full,
                "cases":{x:{} for x in full}},False)

    def test_first8_preserves_split_mode(self):
        self.assertEqual(
            p5.classify_original_run(list(p5.FIRST),None,False),
            "FIRST8_COMPLETE_CONSOLE")

    def test_eleventh_original_pass_is_not_missing_witness(self):
        observed=list(p5.FIRST+p5.LAST)
        self.assertNotEqual(observed,list(p5.FIRST))
        with self.assertRaisesRegex(ValueError,"manifest absent"):
            p5.classify_original_run(observed,None,True)

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
