#!/usr/bin/env python3
"""BPU-8 R2C preregistered fixedHash11 source-only gates; not gem5 sim."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
f=ROOT/"scripts/bpu_b8_r2c_fixed_hash_full19.py"
spec=importlib.util.spec_from_file_location("bpu8_r2c",f)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
M=m.load_matrix()

class R2CHash11ContractTests(unittest.TestCase):
    def test_152_jobs_and_immutable_geometry(self):
        self.assertEqual(len(M["profiles"]),8)
        self.assertEqual(len(M["workloads"]),19)
        self.assertEqual(len(M["comparisons"]["native_vs_fixed"]),7)
        self.assertEqual(len(M["comparisons"]["fixed_equal_bits"]),2)
        self.assertEqual(8*19,152)
        self.assertEqual(8*2,16)
        self.assertEqual(M["profiles"]["tg5_45_h11"]["total_bits"],45736)
        self.assertEqual(M["profiles"]["tg7_50_h11"]["total_bits"],50088)
        self.assertEqual(M["profiles"]["r2a_both52_h11"]["total_bits"],52904)
        self.assertEqual(M["profiles"]["r2b_6b_53_h11"]["total_bits"],52904)
        self.assertEqual(M["profiles"]["r2a_mid60_h11"]["total_bits"],60072)
        self.assertEqual(M["profiles"]["r2b_6b_60_h11"]["total_bits"],60072)
        self.assertEqual(M["profiles"]["g7_h11"]["total_bits"],65192)
        self.assertEqual(M["profiles"]["tg5_45"]["bp_type"],"tage5-iso45k")
        self.assertEqual(m.PINNED_GEM5_SHA,M["method"]["exact_physical_gem5_sha256"])

    def test_mutated_pre_result_contract_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"m.json"
            def check(edit,label):
                changed=json.loads(json.dumps(M))
                edit(changed)
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError,label):
                    m.load_matrix(path)
            check(lambda z:z["profiles"]["r2a_mid60_h11"].update(
                  total_bits=60073),"geometry drift")
            check(lambda z:z["profiles"]["r2b_6b_53_h11"].update(
                  fixed_index_hash_log_size=10),"geometry drift")
            check(lambda z:z["profiles"]["g7_h11"].update(
                  bp_type="tage7-iso65k"),"geometry drift")
            check(lambda z:z["method"].update(hash_log=10),"fixed-hash")
            check(lambda z:z["comparisons"]["fixed_equal_bits"].pop(),
                  "pair registry")
            check(lambda z:z["workloads"].pop(),"workloads/frontend")

    def test_instantiated_hash_changes_only_no_storage_changes(self):
        from test_r2b_frontier import config_for
        with tempfile.TemporaryDirectory() as tmp:
            ini=Path(tmp)/"config.ini"
            for name in M["profiles"]:
                underlying=name[:-4] if name.endswith("_h11") else name
                body=config_for(underlying)
                if name.endswith("_h11"):
                    body=body.replace("fixedIndexHashLogSize=0",
                                      "fixedIndexHashLogSize=11")
                ini.write_text(body)
                self.assertTrue(m.validate_gem5_config(ini,name,M["profiles"]))
            ini.write_text(config_for("r2a_mid60"))
            with self.assertRaisesRegex(ValueError,"fixedIndexHashLogSize"):
                m.validate_gem5_config(ini,"r2a_mid60_h11",M["profiles"])
            ini.write_text(config_for("r2b_6b_60").replace(
                "fixedIndexHashLogSize=0","fixedIndexHashLogSize=10"))
            with self.assertRaisesRegex(ValueError,"fixedIndexHashLogSize"):
                m.validate_gem5_config(ini,"r2b_6b_60_h11",M["profiles"])

    def test_native_reference_mandatory_and_first_roi_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing=Path(tmp)/"missing-r2b-raw"
            with self.assertRaisesRegex(ValueError,"RAW manifest/results.csv absent"):
                m.verify_native_controls(missing,M,Path(tmp)/"no-gem5",
                                         {},("huffbench",))
            stat=Path(tmp)/"stats.txt"
            stat.write_text("---------- Begin Simulation Statistics ----------\n"
                            "cpu.simTicks 201\n"
                            "---------- End Simulation Statistics   ----------\n"
                            "---------- Begin Simulation Statistics ----------\n"
                            "cpu.simTicks 202\n"
                            "---------- End Simulation Statistics   ----------\n")
            stats,txt=m.parse_first_roi(stat)
            self.assertEqual(m.unique_int(stats,"simTicks"),201)
            self.assertNotIn("202",txt)

if __name__=="__main__":
    unittest.main()
