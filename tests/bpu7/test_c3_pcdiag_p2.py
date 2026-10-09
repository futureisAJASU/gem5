"""Tests only synthetic debug-record parsing; not measured branch performance."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "pcdiag", ROOT / "scripts/bpu_b7_c3_pcdiag_p2.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def line(pc=0x120, ghr=0x3, actual=0, chooser=3, fix=1, brk=0):
    vals = {
        "pc": hex(pc), "ghr16": hex(ghr), "g5": "1",
        "c3": "0", "actual": str(actual),
        "conf": "1", "strength": "3", "provider": "1",
        "bank": "2", "idx": "12", "tag": "7",
        "hit": "1", "strong": "1", "disagree": "1",
        "dircnt": "0", "choosecnt": str(chooser),
        "override": "1", "fix": str(fix), "break": str(brk),
        "rowwrite": "1", "dirupd": "1",
        "chooseupd": "1", "alloc": "0", "evict": "0",
        "blocked": "0", "stale": "0",
    }
    return "100: cpu: C3DIAG " + " ".join(f"{k}={v}" for k,v in vals.items()) + "\n"


class PcDiagTraceTest(unittest.TestCase):
    def test_record_parse_exact_prediction_and_commit(self):
        x=mod.parse_event(line())
        self.assertEqual(x["pc"],0x120)
        self.assertEqual(x["ghr16"],3)
        self.assertEqual(x["fix"],1)
        self.assertEqual(x["override"],1)
        self.assertIsNone(mod.parse_event("100: other log\n"))

    def test_reject_harmful_override_wrong_accounting(self):
        with self.assertRaisesRegex(ValueError,"override vs fix/break"):
            mod.parse_event(line().replace("break=0","break=1"))
        with self.assertRaisesRegex(ValueError,"invalid hypothetical fix"):
            mod.parse_event(line(actual=1,fix=1,brk=0))
        with self.assertRaisesRegex(ValueError,"chooser threshold"):
            mod.parse_event(line(chooser=2))
        with self.assertRaisesRegex(ValueError,"C3 trace missing"):
            mod.parse_event(line().replace(" stale=0",""))

    def test_end_to_end_PC_vs_context_aggregation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"synthetic.trace"
            path.write_text(
                line(0x120,0x1,0,3,1,0) +
                line(0x120,0x2,1,3,0,1) +
                line(0x120,0x1,0,3,1,0) +
                line(0x222,0x3,1,3,0,1)
            )
            pcs,ctx,seen=mod.collect_trace(path,"synthetic")
            self.assertEqual(seen,4)
            self.assertEqual(len(pcs),2)
            self.assertEqual(len(ctx),3)
            rows=mod.format_records(pcs,ctx,"synthetic")
            pc120=next(r for r in rows if r["pc"]=="0x120")
            self.assertEqual(pc120["events"],3)
            self.assertEqual(pc120["fixes"],2)
            self.assertEqual(pc120["breaks"],1)
            self.assertEqual(pc120["unique_ghr16"],2)
            self.assertEqual(pc120["net"],1)

    def test_missing_actual_file_and_empty_trace_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"empty.trace"
            p.write_text("no C3 event\n")
            with self.assertRaisesRegex(ValueError,"no committed C3DIAG"):
                mod.collect_trace(p,"test")

    def test_runner_never_conflates_full_trace_and_first_roi(self):
        s=(ROOT/"scripts/bpu_b7_c3_pcdiag_p2.py").read_text()
        self.assertIn("FULL_EXECUTION_DEBUG_TRACE_NOT_ROI_ALIGNED",s)
        self.assertIn("trace_events_equal_first_roi_eligible",s)
        self.assertIn('if diffs:',s)
        c=(ROOT/"src/cpu/pred/tage_base.cc").read_text()
        self.assertIn('"C3DIAG pc=%#lx ghr16=%#x',c)
        self.assertIn('if (debug::TageC3Diag)',c)
        self.assertIn('DPRINTF(TageC3Diag,',c)
        self.assertIn('c3PcChooser->train(snap, taken)',c)


if __name__=="__main__":
    unittest.main()
