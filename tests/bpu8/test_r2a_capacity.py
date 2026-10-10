#!/usr/bin/env python3
"""BPU-8 R2A: frozen seven-bank capacity paths, fail-closed synthetic gates."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/bpu_b8_r2a_capacity_full19.py"
spec = importlib.util.spec_from_file_location("bpu8_r2a_runner", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

EXPECTED = {
    "r2a_dn43": 43816, "r2a_ref45": 45736,
    "r2a_sh49": 49064, "r2a_lg49": 49576,
    "r2a_both52": 52904, "r2a_mid60": 60072,
    "r2a_long60": 60584, "tg7_50": 50088,
    "tg5_45": 45736, "stock": 65192, "g7": 65192,
}

def config_ini(profile, matrix):
    p = matrix["profiles"][profile]
    if profile == "stock":
        entries, base = [512]*7, 8192
        tags, hist = [9,9,10,10,11,11,12], [5,9,15,25,44,76,130]
    elif profile == "g7":
        entries, base = [512,512,512,1024,512,512,512], 2048
        tags, hist = [9,9,10,10,11,11,12], [5,9,15,25,44,76,130]
    else:
        entries, base, tags, hist = (p["entries"],p["base_entries"],
                                     p["tag_bits"],p["histories"])
    options = {
      "nHistoryTables":len(entries),
      "maxHist":hist[-1],"minHist":hist[0],
      "logTagTableSizes":" ".join(map(str,[base.bit_length()-1]+
                                          [v.bit_length()-1 for v in entries])),
      "tagTableTagWidths":" ".join(map(str,[0]+tags)),
      "explicitHistLengths":"" if profile == "stock" else " ".join(map(str,hist)),
      "tagTableCounterBits":3,"tagTableUBits":2,
      "logRatioBiModalHystEntries":2,"maxNumAlloc":1,
      "pathHistBits":16,"fixedIndexHashLogSize":0,
      "speculativeHistUpdate":"true","perceptronEnabled":"false",
      "instShiftAmt":1,
    }
    return ("[board.processor.cores.core.branchPred.conditionalBranchPred.tage]\n" +
            "".join(f"{k}={v}\n" for k,v in options.items()))

class CapacityMatrixTests(unittest.TestCase):
    def test_exact_matrix_and_reference(self):
        matrix = m.load_matrix()
        self.assertEqual(len(matrix["profiles"]), 11)
        self.assertEqual(len(matrix["workloads"]), 19)
        self.assertEqual(len(matrix["paired_comparisons"]), 8)
        self.assertEqual({p: v["total_bits"] for p, v
                          in matrix["profiles"].items()}, EXPECTED)
        self.assertEqual(matrix["profiles"]["r2a_ref45"]["bp_type"],
                         "tage-geo-tg7-45")
        self.assertEqual(matrix["profiles"]["tg7_50"]["bp_type"],
                         "tage-geo-tg7-50")
        self.assertEqual(matrix["profiles"]["tg5_45"]["bp_type"],
                         "tage5-iso45k")

    def test_matrix_mutation_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"matrix.json"
            matrix = m.load_matrix()
            def test_bad(mutator, regex):
                x = json.loads(json.dumps(matrix))
                mutator(x)
                p.write_text(json.dumps(x))
                with self.assertRaisesRegex(ValueError, regex):
                    m.load_matrix(p)
            test_bad(lambda x: x["profiles"]["r2a_lg49"].update(
                     total_bits=50088), "geometry drift")
            test_bad(lambda x: x["profiles"]["r2a_ref45"]["entries"].__setitem__(
                     6, 512), "reference TG7-45|geometry drift")
            test_bad(lambda x: x["profiles"]["tg7_50"].update(
                     total_bits=45736), "frozen R1 control")
            test_bad(lambda x: x["method"].update(hash_log_size=10),
                     "identity or index mode")
            test_bad(lambda x: x["paired_comparisons"].pop(),
                     "pairwise")
            test_bad(lambda x: x["workloads"].append("huffbench"), "workload/frontend")

    def test_real_config_geometry_assertions(self):
        matrix=m.load_matrix()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"config.ini"
            for name in EXPECTED:
                f.write_text(config_ini(name, matrix))
                self.assertTrue(m.validate_gem5_config(f, name,matrix["profiles"]))
            f.write_text(config_ini("r2a_dn43",matrix).replace(
                       "logTagTableSizes=11 8 9 9 9 9 9 7",
                       "logTagTableSizes=11 8 9 9 9 9 9 8"))
            with self.assertRaisesRegex(ValueError,"logTagTableSizes"):
                m.validate_gem5_config(f,"r2a_dn43",matrix["profiles"])
            f.write_text(config_ini("r2a_lg49",matrix).replace(
                       "fixedIndexHashLogSize=0","fixedIndexHashLogSize=10"))
            with self.assertRaisesRegex(ValueError,"fixedIndexHashLogSize"):
                m.validate_gem5_config(f,"r2a_lg49",matrix["profiles"])
            f.write_text(config_ini("r2a_lg49",matrix).replace(
                       "maxNumAlloc=1","maxNumAlloc=2"))
            with self.assertRaisesRegex(ValueError,"maxNumAlloc"):
                m.validate_gem5_config(f,"r2a_lg49",matrix["profiles"])

    def test_first_roi_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"stats.txt"
            f.write_text("---------- Begin Simulation Statistics ----------\n"
                         "system.cpu.simTicks 1000\n"
                         "---------- End Simulation Statistics   ----------\n"
                         "---------- Begin Simulation Statistics ----------\n"
                         "system.cpu.simTicks 2000\n"
                         "---------- End Simulation Statistics   ----------\n")
            d,text=m.parse_first_roi(f)
            self.assertEqual(m.unique_int(d,"simTicks"),1000)
            self.assertNotIn("2000",text)
            f.write_text("---------- Begin Simulation Statistics ----------\n"
                         "system.cpu.simTicks 1000\n")
            with self.assertRaisesRegex(ValueError,"incomplete"):
                m.parse_first_roi(f)

if __name__=="__main__":
    unittest.main()
