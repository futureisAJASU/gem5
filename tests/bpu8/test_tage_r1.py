#!/usr/bin/env python3
"""BPU-8 synthetic fail-closed parser, exact-state matrix and ROI gates."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
path = ROOT/"scripts/bpu_b8_tage_isobit_full19.py"
spec = importlib.util.spec_from_file_location("bpu8_runner",path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MatrixTests(unittest.TestCase):
    def test_registry_and_storage(self):
        data=m.load_matrix()
        self.assertEqual(len(data["profiles"]),10)
        self.assertEqual(len(data["workloads"]),19)
        for k,p in data["profiles"].items():
            self.assertEqual(p["total_bits"],
                             65192 if k in ("stock","g7") else
                             45736 if k.endswith("_45") else 50088)
        self.assertEqual(sum(int(k.endswith("_45")) for k in data["profiles"]),4)

    def test_geometry_mutations_fail_closed(self):
        d=m.load_matrix()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"matrix.json"
            def verify():
                f.write_text(json.dumps(d))
                return m.load_matrix(f)
            verify()
            d["profiles"]["tg6_50"]["tag_bits"][0] += 1
            with self.assertRaisesRegex(ValueError,"bits"):
                verify()
            d=m.load_matrix()
            d["profiles"]["tg4_50"]["entries"][0]=300
            with self.assertRaisesRegex(ValueError,"geometry"):
                verify()
            d=m.load_matrix()
            d["profiles"]["tg5_45"]["histories"][1]=17
            with self.assertRaisesRegex(ValueError,"G5 canonical"):
                verify()
            d=m.load_matrix()
            d["profiles"]["stock"]["total_bits"]=45736
            with self.assertRaisesRegex(ValueError,"anchor"):
                verify()
            d=m.load_matrix()
            d["workloads"].append("huffbench")
            with self.assertRaisesRegex(ValueError,"corpus"):
                verify()

    def test_first_roi_marker_and_errors(self):
        valid=("---------- Begin Simulation Statistics ----------\n"
               "system.cpu.x.foo 12 # sample\n"
               "---------- End Simulation Statistics   ----------\n"
               "---------- Begin Simulation Statistics ----------\n"
               "system.cpu.x.foo 99\n"
               "---------- End Simulation Statistics   ----------\n")
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"stats.txt"
            p.write_text(valid)
            stats, raw=m.parse_first_roi(p)
            self.assertEqual(m.unique_int(stats,"foo"),12)
            self.assertNotIn("99",raw)
            with self.assertRaisesRegex(ValueError,"exactly one"):
                m.unique_int(stats,"missing")
            p.write_text(valid.replace("system.cpu.x.foo 12 # sample",
                                     "system.cpu.x.foo 12\nsystem.cpu.x.foo 12"))
            with self.assertRaisesRegex(ValueError,"duplicate"):
                m.parse_first_roi(p)
            p.write_text(valid.replace("---------- End Simulation Statistics   ----------\n",""))
            with self.assertRaisesRegex(ValueError,"overlapping|incomplete"):
                m.parse_first_roi(p)

    @staticmethod
    def stats(bits=45736, wrong=4):
        return {"cpu."+k:str(v) for k,v in dict(
            simTicks=20000,simInsts=2000,committedConditionalPredictions=100,
            committedConditionalWrong=wrong,finalConditionalWrong=wrong,
            predictionMetadataChecks=100,historyRestoreChecks=2,
            historyStateRestores=2,storageBits=bits,
            taggedStorageBits=bits-2728,bimodalStorageBits=2560,
            historyStorageBits=146,otherStorageBits=22
        ).items()}

    def test_row_accounting_fail_closed(self):
        x=self.stats()
        good=m.inspect_row(x,"tg5_45","huffbench",45736,"hash")
        self.assertEqual(good["committedConditionalWrong"],4)
        self.assertEqual(good["mpki"],"2.000000000")
        x=self.stats();x["cpu.predictionMetadataChecks"]="99"
        with self.assertRaisesRegex(ValueError,"metadata"):
            m.inspect_row(x,"tg5_45","huffbench",45736,"hash")
        x=self.stats();x["cpu.finalConditionalWrong"]="5"
        with self.assertRaisesRegex(ValueError,"corrected"):
            m.inspect_row(x,"tg5_45","huffbench",45736,"hash")
        x=self.stats();x["cpu.storageBits"]="50088"
        with self.assertRaisesRegex(ValueError,"storageBits"):
            m.inspect_row(x,"tg5_45","huffbench",45736,"hash")
        x=self.stats();x["cpu.otherStorageBits"]="21"
        with self.assertRaisesRegex(ValueError,"storage sum"):
            m.inspect_row(x,"tg5_45","huffbench",45736,"hash")
        x=self.stats();x["cpu.simInsts"]="0"
        with self.assertRaisesRegex(ValueError,"empty"):
            m.inspect_row(x,"tg5_45","huffbench",45736,"hash")


if __name__=="__main__":
    unittest.main()
