#!/usr/bin/env python3
"""Pre-result fail-closed checks for R2B exact-iso logical-state frontier."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
path = ROOT / "scripts/bpu_b8_r2b_geometry_full19.py"
spec = importlib.util.spec_from_file_location("r2b", path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
M = runner.load_matrix()

def config_for(profile):
    p = M["profiles"][profile]
    if profile == "stock":
        base, entries = 8192, [512] * 7
        tags, histories = [9,9,10,10,11,11,12], [5,9,15,25,44,76,130]
    elif profile == "g7":
        base, entries = 2048, [512,512,512,1024,512,512,512]
        tags, histories = [9,9,10,10,11,11,12], [5,9,15,25,44,76,130]
    else:
        base, entries = p["base_entries"], p["entries"]
        tags, histories = p["tag_bits"], p["histories"]
    fields = {
        "nHistoryTables": len(entries),
        "maxHist": histories[-1], "minHist": histories[0],
        "logTagTableSizes": " ".join(map(str, [base.bit_length()-1]+
                            [e.bit_length()-1 for e in entries])),
        "tagTableTagWidths": " ".join(map(str, [0]+tags)),
        "explicitHistLengths": ("" if profile=="stock" else
                               " ".join(map(str,histories))),
        "tagTableCounterBits":3, "tagTableUBits":2,
        "logRatioBiModalHystEntries":2,"maxNumAlloc":1,
        "pathHistBits":16,"fixedIndexHashLogSize":0,
        "speculativeHistUpdate":"true","perceptronEnabled":"false",
        "instShiftAmt":1,
    }
    return ("[board.processor.cores.core.branchPred.conditionalBranchPred.tage]\n" +
            "".join(f"{k}={v}\n" for k,v in fields.items()))

class ExactIsoR2BTests(unittest.TestCase):
    def test_registered_304_full19_and_32_smoke(self):
        self.assertEqual(M["experiment"],"BPU8_R2B_GEOMETRY_FRONTIER_V01")
        self.assertEqual(len(M["profiles"]),16)
        self.assertEqual(len(M["workloads"]),19)
        self.assertEqual(16*19,304)
        self.assertEqual(16*2,32)
        self.assertEqual(len(M["paired_comparisons"]),14)
        for name,g in M["tiers"].items():
            self.assertIn(g["bits"],(50088,52904,60072))
            for q in [g["reference"]]+g["comparators"]:
                self.assertEqual(g["bits"],M["profiles"][q]["total_bits"])
        # The frozen original stock and G7 65K are never mistaken for
        # equality-normalized alternatives.
        self.assertEqual(M["profiles"]["stock"]["total_bits"],65192)
        self.assertEqual(M["profiles"]["g7"]["total_bits"],65192)

    def test_strict_matrix_mutations_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"matrix.json"
            def corrupt_and_check(edit, pattern):
                val=json.loads(json.dumps(M))
                edit(val)
                path.write_text(json.dumps(val))
                with self.assertRaisesRegex(ValueError,pattern):
                    runner.load_matrix(path)
            corrupt_and_check(lambda m:m["profiles"]["r2b_5b_60"].update(
                              total_bits=60073),"geometry changed")
            corrupt_and_check(lambda m:m["profiles"]["r2b_6a_53"].
                              get("entries").__setitem__(1,512),"geometry changed")
            corrupt_and_check(lambda m:m["profiles"]["tg7_50"].update(
                              total_bits=60072),"control drift")
            corrupt_and_check(lambda m:m["tiers"]["B53_52904"].update(
                              bits=53000),"budget tier changed")
            corrupt_and_check(lambda m:m["paired_comparisons"].pop(),
                              "paired iso-bit")
            corrupt_and_check(lambda m:m["workloads"].append("huffbench"),
                              "Full19 workload")

    def test_instantiated_geometry_and_error_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=pathlib.Path(tmp)/"config.ini"
            for p in M["profiles"]:
                cfg.write_text(config_for(p))
                self.assertTrue(runner.validate_gem5_config(cfg,p,M["profiles"]))
            cfg.write_text(config_for("r2b_5b_60").replace(
                "maxNumAlloc=1","maxNumAlloc=2"))
            with self.assertRaisesRegex(ValueError,"maxNumAlloc"):
                runner.validate_gem5_config(cfg,"r2b_5b_60",M["profiles"])
            cfg.write_text(config_for("r2b_6a_53").replace(
                "fixedIndexHashLogSize=0","fixedIndexHashLogSize=10"))
            with self.assertRaisesRegex(ValueError,"fixedIndexHashLogSize"):
                runner.validate_gem5_config(cfg,"r2b_6a_53",M["profiles"])
            cfg.write_text(config_for("r2b_5a_60").replace(
                "logTagTableSizes=11 9 10 10 9 10",
                "logTagTableSizes=11 9 10 10 9 9"))
            with self.assertRaisesRegex(ValueError,"logTagTableSizes"):
                runner.validate_gem5_config(cfg,"r2b_5a_60",M["profiles"])

    def test_first_roi_and_required_binary_sha_pin(self):
        self.assertEqual(runner.PINNED_GEM5_SHA,
                         "96717e980f10f22c8899ede11ecd4b88a762d53f79f8c1c918e5b0a9f202dced")
        with tempfile.TemporaryDirectory() as tmp:
            f=pathlib.Path(tmp)/"stats.txt"
            f.write_text("---------- Begin Simulation Statistics ----------\n"
                         "cpu.simTicks 143\n"
                         "---------- End Simulation Statistics   ----------\n"
                         "---------- Begin Simulation Statistics ----------\n"
                         "cpu.simTicks 144\n"
                         "---------- End Simulation Statistics   ----------\n")
            stats,text=runner.parse_first_roi(f)
            self.assertEqual(runner.unique_int(stats,"simTicks"),143)
            self.assertNotIn("144",text)
            f.write_text("---------- Begin Simulation Statistics ----------\n"
                         "cpu.simTicks 143\n")
            with self.assertRaisesRegex(ValueError,"incomplete"):
                runner.parse_first_roi(f)

if __name__=="__main__":
    unittest.main()
