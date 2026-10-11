"""P3 synthetic accounting tests. Not measurement evidence."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "p3", ROOT / "scripts/bpu_b7_c3_p3_g1_full19.py")
p3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p3)
prior_spec = importlib.util.spec_from_file_location(
    "oldtests", ROOT / "tests/bpu7/test_c3_p0_p1_runner.py")
old = importlib.util.module_from_spec(prior_spec)
prior_spec.loader.exec_module(old)

def fixture(p3_enabled):
    d = old.fixture("p1_e128")
    prefix = "system.cpu.branchPred.tage."
    # Directly counted G0 class totals, not P2's whole-execution sampling.
    proposed = {"Weak": (1,1,0), "Medium": (1,1,0),
                "Strong5": (1,0,1)}
    totals = {"Eligible":(35,30,15)}
    for i, cat in enumerate(("Weak","Medium","Strong5")):
        req, fix, br = proposed[cat]
        veto = req if (p3_enabled and cat=="Strong5") else 0
        acc = req - veto
        values = {
            "Eligible": totals["Eligible"][i],
            "Proposed":req,"Accepted":acc,"Vetoed":veto,
            "RawFix":fix,"RawBreak":br,
            "AcceptedFix":fix if not veto else 0,
            "AcceptedBreak":br if not veto else 0,
            "VetoFix":fix if veto else 0,
            "VetoBreak":br if veto else 0,
        }
        for k,v in values.items():
            d[prefix+"c3G1"+cat+k]=str(v)
    d.update({
       prefix+"c3G1AcceptedOverrides":str(2 if p3_enabled else 3),
       prefix+"c3G1AcceptedFix":"2",
       prefix+"c3G1AcceptedBreak":str(0 if p3_enabled else 1),
       prefix+"c3G1VetoedOverrides":str(1 if p3_enabled else 0),
       prefix+"c3G1VetoedFix":"0",
       prefix+"c3G1VetoedBreak":str(1 if p3_enabled else 0),
    })
    return d

class G1P3Contract(unittest.TestCase):
    def test_eight_exact_profiles(self):
        self.assertEqual(len(p3.WORKLOADS),19)
        self.assertEqual(len(p3.PROFILES),8)
        for n,b in ((64,46824),(128,47912),(256,50088)):
            self.assertEqual(p3.PROFILES[f"p1_e{n}"][1],b)
            self.assertEqual(p3.PROFILES[f"p3_e{n}"][1],b)
        self.assertEqual(p3.PROFILES["g5"][1],45736)
        self.assertEqual(p3.PROFILES["g7"][1],65192)
    def test_full19_and_smoke_listing(self):
        script=ROOT/"scripts/bpu_b7_c3_p3_g1_full19.py"
        for args, jobs in ((["--list"],152),(["--smoke","--list"],16)):
            p=subprocess.run([sys.executable,str(script),*args],capture_output=True,
                             text=True,check=True)
            self.assertEqual(len(p.stdout.splitlines()),jobs+1)
            self.assertIn(f"SHADOW_ONLY_ROI_PLAN={jobs}",p.stdout)
    def test_p1_vs_p3_conservation(self):
        for mode in (False, True):
            profile="p3_e128" if mode else "p1_e128"
            row=p3.inspect_row(fixture(mode),profile,"huffbench","dummy","dummy")
            self.assertEqual(row["shadowNet"],1)
            self.assertEqual(row["acceptedShadowNet"],2 if mode else 1)
            self.assertEqual(row["c3G1VetoedOverrides"],1 if mode else 0)
    def test_veto_must_only_hit_strong5(self):
        stat=fixture(True)
        stat["system.cpu.branchPred.tage.c3G1WeakVetoed"]="1"
        with self.assertRaisesRegex(ValueError, "class Weak|conservation"):
            p3.inspect_row(stat,"p3_e128","huffbench","-","-")
    def test_raw_fix_break_conservation(self):
        stat=fixture(True)
        stat["system.cpu.branchPred.tage.c3G1AcceptedFix"]="5"
        with self.assertRaisesRegex(ValueError, "global G1 conservation"):
            p3.inspect_row(stat,"p3_e128","huffbench","-","-")
    def test_p1_cannot_silently_veto(self):
        stat=fixture(True)
        with self.assertRaisesRegex(ValueError, "P1 original acceptance changed"):
            p3.inspect_row(stat,"p1_e128","huffbench","-","-")
    def test_prediction_scope_and_training_preserved(self):
        cc=(ROOT/"src/cpu/pred/tage_base.cc").read_text()
        self.assertEqual(cc.count("bi->c3G1Vetoed = c3G1Strong5Veto("),1)
        self.assertEqual(cc.count("c3PcChooser->train(snap, taken)"),1)
        self.assertIn("return bi->finalPred;",cc)
if __name__=="__main__":
    unittest.main()
