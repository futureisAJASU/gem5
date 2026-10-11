#!/usr/bin/env python3
"""R3 synthetic source and counter-conservation regression; not gem5 measurement."""
import configparser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "scripts/bpu_b8_r3_g5_lock_full19.py"
spec = importlib.util.spec_from_file_location("bpu8_r3", P)
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
M = r3.load_matrix()


def synthetic_ini(p):
    z = M["profiles"][p]
    e, t, h = z["entries"], z["tag_bits"], z["histories"]
    section = "system.cpu.branchPred.conditionalBranchPred.tage"
    pairs = {
        "nHistoryTables": len(e), "maxHist": 130, "minHist": 5,
        "logTagTableSizes": " ".join(str(x.bit_length()-1) for x in [2048]+e),
        "tagTableTagWidths": " ".join(map(str, [0]+t)),
        "explicitHistLengths": " ".join(map(str, h)),
        "tagTableCounterBits": 3, "tagTableUBits": 2,
        "logRatioBiModalHystEntries": 2, "maxNumAlloc": 1,
        "pathHistBits": 16,
        "fixedIndexHashLogSize": z["fixed_index_hash_log_size"],
        "speculativeHistUpdate": "true", "perceptronEnabled": "false",
        "r3TageDiagnosticsEnabled": "true", "instShiftAmt": 1,
    }
    return "["+section+"]\n"+"\n".join(f"{k}={v}" for k,v in pairs.items())+"\n"


def synthetic_stats(p):
    counts = len(M["profiles"][p]["entries"])+1
    z = {k: 0 for k in r3.BASE_FIELDS}
    z.update(simTicks=1000,simInsts=1000,committedConditionalPredictions=10,
             committedConditionalWrong=3,finalConditionalWrong=3,
             predictionMetadataChecks=10,historyRestoreChecks=2,
             historyStateRestores=2,storageBits=45736,taggedStorageBits=43008,
             bimodalStorageBits=2560,historyStorageBits=146,otherStorageBits=22)
    z.update(r3PseudoNewAlloc=2,r3AlternateDisagreements=4,
             r3AlternateWouldFix=1,r3AllocAttempts=2,r3Allocations=2,
             r3ForcedUsefulClears=1)
    banks = {
        "r3HitBank": [4,6]+[0]*(counts-2),
        "r3HitBankWrong": [1,2]+[0]*(counts-2),
        "r3SelectedBankWrong": [1,2]+[0]*(counts-2),
        "r3AltBank": [0,2]+[0]*(counts-2),
        "r3AllocByBank": [0,2]+[0]*(counts-2),
    }
    for key,values in banks.items():
        for i,v in enumerate(values):
            z[f"{key}::{i}"] = v
    return {"system.cpu.branchPred.conditionalBranchPred.tage."+k:str(v)
            for k,v in z.items()}


class R3GateTests(unittest.TestCase):
    def test_114_full_12_smoke_preregistered(self):
        self.assertEqual(len(M["profiles"]),6)
        self.assertEqual(len(M["workloads"]),19)
        self.assertEqual(len(M["smoke_workloads"]),2)
        self.assertEqual(M["expected_full19_jobs"],114)
        self.assertEqual(M["expected_smoke_jobs"],12)
        self.assertEqual(set(p["total_bits"] for p in M["profiles"].values()),{45736})
        for name,p in M["profiles"].items():
            self.assertTrue(p["r3_diagnostics"])
            self.assertEqual(p["fixed_index_hash_log_size"],
                             11 if name.endswith("h11") else 0)

    def test_pre_result_contract_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)/"prereg.json"
            cases = (
                (lambda m:m["profiles"]["tg7_h11"].update(total_bits=45737),
                 "exact geometry"),
                (lambda m:m["profiles"]["tg6_native"].update(
                    fixed_index_hash_log_size=11), "exact geometry"),
                (lambda m:m["comparisons"]["same_hash"].pop(),
                 "comparisons"),
                (lambda m:m["workloads"].pop(), "identity"),
                (lambda m:m["profiles"]["g5_native"].update(r3_diagnostics=False),
                 "exact geometry"),
            )
            for edit,message in cases:
                m=json.loads(json.dumps(M))
                edit(m)
                tmp.write_text(json.dumps(m))
                with self.assertRaisesRegex(ValueError,message):
                    r3.load_matrix(tmp)

    def test_real_config_shape_and_hash_must_match(self):
        with tempfile.TemporaryDirectory() as td:
            ini=Path(td)/"config.ini"
            for p in M["profiles"]:
                raw=synthetic_ini(p)
                ini.write_text(raw)
                self.assertTrue(r3.validate_r3_ini(ini,p,M["profiles"]))
                ini.write_text(raw.replace("r3TageDiagnosticsEnabled=true",
                                           "r3TageDiagnosticsEnabled=false"))
                with self.assertRaisesRegex(ValueError,"r3TageDiagnosticsEnabled"):
                    r3.validate_r3_ini(ini,p,M["profiles"])
                ini.write_text(raw.replace(
                    f"fixedIndexHashLogSize={M['profiles'][p]['fixed_index_hash_log_size']}",
                    "fixedIndexHashLogSize=8"))
                with self.assertRaisesRegex(ValueError,"fixedIndexHashLogSize"):
                    r3.validate_r3_ini(ini,p,M["profiles"])

    def test_cause_counter_conservation_and_fail_closed(self):
        for p,z in M["profiles"].items():
            raw=synthetic_stats(p)
            ok=r3.inspect_row(raw,p,"huffbench",z,"0"*64)
            self.assertEqual(ok["committedConditionalPredictions"],10)
            self.assertEqual(json.loads(ok["r3CauseJson"])["r3HitBank"],[4,6]+
                             [0]*(len(z["entries"])-1))
            for key in ("r3HitBankWrong::1","r3AllocByBank::1"):
                changed=dict(raw)
                full="system.cpu.branchPred.conditionalBranchPred.tage."+key
                changed[full]="3"
                with self.assertRaisesRegex(ValueError,"conservation"):
                    r3.inspect_row(changed,p,"huffbench",z,"0"*64)
            changed=dict(raw)
            changed["system.cpu.branchPred.conditionalBranchPred.tage.r3AllocAttempts"]="1"
            with self.assertRaisesRegex(ValueError,"conservation"):
                r3.inspect_row(changed,p,"huffbench",z,"0"*64)

    def test_first_roi_exact_slice(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"stats.txt"
            f.write_text("---------- Begin Simulation Statistics ----------\n"
                         "system.cpu.simTicks 100\n"
                         "---------- End Simulation Statistics ----------\n"
                         "---------- Begin Simulation Statistics ----------\n"
                         "system.cpu.simTicks 200\n"
                         "---------- End Simulation Statistics ----------\n")
            stats,raw=r3.parse_first_roi(f)
            self.assertEqual(r3.unique_int(stats,"simTicks"),100)
            self.assertNotIn("200",raw)


if __name__=="__main__":
    unittest.main()
