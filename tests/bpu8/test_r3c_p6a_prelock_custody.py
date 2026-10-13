#!/usr/bin/env python3
"""P6A prelock provenance test: isolated fixture, no simulated performance."""
from pathlib import Path
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p6a_prelock_custody as p6
import bpu_b8_r3c_p5a_split_raw_audit as p5

class P6ACustodyTests(unittest.TestCase):
    def test_no_implicit_holdout_or_lock(self):
        src=(ROOT/"scripts/bpu_b8_r3c_p6a_prelock_custody.py").read_text()
        self.assertIn("NOT_CORPUS_LOCK",src)
        self.assertIn('"historical_unseen_workload_independence":"UNVERIFIED"',src)
        self.assertIn('"comparison_performance_started":False',src)
        self.assertIn('"source_and_inputs_immutable_commit":"NOT_CREATED"',src)
        self.assertEqual(p6.EXPECTED_6,(
            "g5_native","g5_h11","tg6_native",
            "tg6_h11","tg7_native","tg7_h11"))

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"missing JSON source"):
                p6.load(Path(td)/"absent.json")

    def test_fixture_all_11_source_inputs_and_repeat3_require_correct_sha(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            first=d/"original";last=d/"repeat"
            first.mkdir();last.mkdir()
            sim=d/"gem5.opt"
            sim.write_text("fake simulator for fixture")
            original_manifest=first/"g5_functional_manifest.json"
            original_manifest.write_text('{"test":"source evidence"}\n')
            cases={}
            p5case=[]
            for name in p6.p2.ORDER:
                elf=d/(name+".elf")
                elf.write_bytes((name+" ELF payload").encode())
                source=d/(name+".input")
                source.write_bytes((name+" input").encode())
                work=first/name/"work";stat=first/name/"sim"
                work.mkdir(parents=True);stat.mkdir()
                (work/"input.bin").write_bytes(source.read_bytes())
                (work/"program.stdout").write_text(name+" stdout")
                (work/"program.stderr").write_text("")
                (first/name/"gem5.stdout").write_text(name+" gem5")
                (first/name/"gem5.stderr").write_text("")
                for raw in ("stats.txt","roi.stats","config.ini"):
                    (stat/raw).write_text(name+" "+raw+" raw")
                row=dict(
                    binary=str(elf),binary_sha256=p6.p2.sha(elf),
                    input_files=[dict(name="input.bin",source_path=str(source),
                                      sha256=p6.p2.sha(source),size=source.stat().st_size)],
                    source_kind="ORIGINAL_P1_PINNED",argv=[],
                    stdin_file_relative=None,program_output_file_relative=None,
                    expected_process_exit_code=0,
                    correctness_gate="EXACT_PREQUALIFIED_QEMU_RV64_STDOUT")
                cases[name]=row
                p5case.append(dict(
                    workload=name,passed=True,
                    elf_sha256=p6.p2.sha(elf),
                    roi_sha256=p6.p2.sha(stat/"roi.stats"),
                    raw_sha256={raw:p6.p2.sha(stat/raw) for raw in
                                ("stats.txt","roi.stats","config.ini")},
                    gem5_stdout_sha256=p6.p2.sha(first/name/"gem5.stdout"),
                    gem5_stderr_sha256=p6.p2.sha(first/name/"gem5.stderr"),
                    app_stdout_sha256=p6.p2.sha(work/"program.stdout"),
                    app_stderr_sha256=p6.p2.sha(work/"program.stderr"),
                    output_file_sha256=None,
                    source_root=str((first/name).resolve()),storageBits=45736))
            reps=[]
            for name in p5.LAST:
                orig=first/name/"sim"/"roi.stats"
                duplicate=last/name/"sim"
                duplicate.mkdir(parents=True)
                (duplicate/"roi.stats").write_bytes(orig.read_bytes())
                proof={
                    "all_simulated_roi_bytes_identical_excluding_explicit_host_fields":True,
                    "host_only_fields_whitelist":sorted(p5.HOST_ONLY_FIRST_ROI_FIELDS),
                    "raw_roi_sha_identical":True,
                    "host_only_drift":False,"changed_host_fields":{}
                }
                reps.append(dict(case=name,pass_=True,
                     original_roi_sha256=p6.p2.sha(orig),
                     repeat_roi_sha256=p6.p2.sha(duplicate/"roi.stats"),
                     roi_semantic_verification=proof))
                reps[-1]["pass"]=reps[-1].pop("pass_")
            p4a=dict(cases=cases,
                     future_six_comparators=list(p6.EXPECTED_6))
            p5ledger=dict(kind="BPU8_R3C_P5A_SPLIT_G5_ONLY_RAW_RECOVERY",
                          verdict=p6.EXPECTED_P5A,
                          original_run_mode="FULL11_COMPLETE_ORIGINAL",
                          original_full11_final_manifest_verified=True,
                          original_final_manifest_sha256=p6.p2.sha(original_manifest),
                          first_console_witness_complete=True,
                          corpus_locked=False,six_profile_holdout_executions=0,
                          gem5_sha256=p5.EXPECTED_GEM5,
                          cases=p5case,three_repeat_cases=reps)
            hist=dict(kind="BPU8_R3C_P5B_NEW_GEM5_G5_ONLY_HISTORICAL_REPLAY",
                      verdict=p6.EXPECTED_P5B,new_gem5_sha256=p5.EXPECTED_GEM5,
                      old_r3_gem5_sha256=p6.p5b.HISTORICAL_SHA,
                      profile="g5_native",compared_profiles=[],holdout_jobs=0,
                      cases={str(i):{"pass":True} for i in range(19)})
            profiles={x:{"total_bits":45736} for x in p6.EXPECTED_6}
            # Simulator SHA is already independently checked in the P5A
            # record; this fixture mocks ONLY its immutable linked digest.
            original_sha=p6.p2.sha
            def fake_sha(path):
                return (p5.EXPECTED_GEM5 if Path(path)==sim
                        else original_sha(Path(path)))
            with (patch.object(p6.r3,"load_matrix",
                               return_value={"profiles":profiles}),
                  patch.object(p6.p2,"sha",side_effect=fake_sha),
                  patch.object(p6.p5a,"verify_repeat_roi_semantics",
                               return_value=reps[0]["roi_semantic_verification"])):
                expected=p6.validate_ledger(p4a,p5ledger,hist,sim,first,last)
                self.assertEqual(len(expected),11)
                self.assertEqual(expected[-1]["case"],"coremark_performance")
                (first/"qsort"/"work"/"program.stdout").write_text("ALTERED")
                with self.assertRaisesRegex(ValueError,"output SHA drift"):
                    p6.validate_ledger(p4a,p5ledger,hist,sim,first,last)

if __name__=="__main__":
    unittest.main()
