"""Synthetic RED/GREEN tests for strict G0 two-core synchronized ROI ledger.

This is NOT a gem5 simulation; it proves parser acceptance and refusal rules.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from g0_verify_pair_roi import PAIRS, MODES, compare_pair, read_run


class G0PairRoiParserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.iters = 32
        for pair in PAIRS:
            speeds = (1 if pair.split("_")[0] == "heavy" else 16,
                      1 if pair.split("_")[1] == "heavy" else 16)
            for mode in MODES:
                d = self.root / pair / mode
                d.mkdir(parents=True)
                divs = [2*((self.iters+e-1)//e) for e in speeds]
                span = [2600 + divs[0]*2, 2100 + divs[1]*2]
                if mode == "shared1":
                    span = [x+750 for x in span]
                start = 10000
                end0,end1 = start+span[0],start+span[1]
                first = 0 if end0<=end1 else 1
                outputs = "\n".join(
                    f"G0_RESULT every={e} iterations={self.iters} "
                    f"div_ops_expected={dcount} checksum={e:016x}"
                    for e,dcount in zip(speeds,divs)
                )
                d.joinpath("effective_config_audit.json").write_text(json.dumps({
                    "status":"G0_A_CONFIG_AND_POWER_DISABLED_VERIFIED_NOT_PERFORMANCE",
                    "mode":mode,"pair_div_physical_units":2 if mode=="private2" else 1,
                }))
                d.joinpath("simulator.log").write_text(
                    "G0_PAIR_ROI_READY core=0 ready_tick=9000\n"
                    "G0_PAIR_ROI_READY core=1 ready_tick=10000\n"
                    "G0_PAIR_ROI_SYNC start_tick=10000 ready0=9000 ready1=10000 "
                    "clock_period_ticks=714 early_core_idle_policy=quiesce\n"
                    f"G0_PAIR_ROI_FINISH core=0 finish_tick={end0} "
                    f"pair_start_tick=10000 committed_insts={10000+divs[0]} "
                    f"committed_intdivs={divs[0]}\n"
                    f"G0_PAIR_ROI_FINISH core=1 finish_tick={end1} "
                    f"pair_start_tick=10000 committed_insts={10000+divs[1]} "
                    f"committed_intdivs={divs[1]}\n"
                    f"G0_PAIR_ROI_SUMMARY pair_start_tick=10000 finish0={end0} "
                    f"finish1={end1} pair_makespan_ticks={max(span)} "
                    f"clock_period_ticks=714 first_finished_core={first}\n"
                    +outputs+"\nSIMULATION_EXIT_CODE=0\n"
                )

    def mutate(self, case, mode, orig, updated):
        p = self.root / case / mode / "simulator.log"
        s=p.read_text()
        self.assertIn(orig,s)
        p.write_text(s.replace(orig, updated, 1))

    def test_pair_pilot_parses_and_computes_slowdown(self):
        for case in PAIRS:
            row = compare_pair(self.root, case, self.iters)
            self.assertGreater(row["pair_shared_over_private_makespan"],1)
            self.assertEqual(row["weighted_speedup"],"OPEN_NO_SOLO_BASELINES")

    def test_missing_second_core_end_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "G0_PAIR_ROI_FINISH core=1",
                    "G0_PAIR_ROI_FINISH core=0")
        with self.assertRaisesRegex(RuntimeError,"duplicate"):
            read_run(self.root,"heavy_sparse","shared1",self.iters)

    def test_legitimate_same_tick_arrival_is_not_false_failure(self):
        self.mutate("heavy_sparse", "private2",
                    "G0_PAIR_ROI_READY core=0 ready_tick=9000",
                    "G0_PAIR_ROI_READY core=0 ready_tick=10000")
        self.mutate("heavy_sparse", "private2",
                    "ready0=9000 ready1=10000",
                    "ready0=10000 ready1=10000")
        result=read_run(self.root,"heavy_sparse","private2",self.iters)
        self.assertFalse(result["arrival_barrier_quiesce_exercised"])
        self.assertEqual(result["ready_tick_skew"],0)

    def test_div_dynamic_count_incorrect_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "committed_intdivs=64",
                    "committed_intdivs=63")
        with self.assertRaisesRegex(RuntimeError,"retired IntDiv count"):
            read_run(self.root,"heavy_sparse","shared1",self.iters)

    def test_pair_end_mismatch_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "pair_makespan_ticks=3478",
                    "pair_makespan_ticks=12")
        with self.assertRaisesRegex(RuntimeError,"invalid pair makespan"):
            read_run(self.root,"heavy_sparse","shared1",self.iters)

    def test_sync_missing_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "G0_PAIR_ROI_SYNC",
                    "NOT_A_SYNC")
        with self.assertRaisesRegex(RuntimeError,"missing/duplicate ROI"):
            read_run(self.root,"heavy_sparse","shared1",self.iters)

    def test_unsynchronized_barrier_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "ready_tick=9000",
                    "ready_tick=10000")
        with self.assertRaisesRegex(RuntimeError,"ready/summary timestamps"):
            read_run(self.root,"heavy_sparse","shared1",self.iters)

    def test_checksum_mismatch_between_modes_rejected(self):
        self.mutate("heavy_sparse","shared1",
                    "checksum=0000000000000001",
                    "checksum=000000000000dead")
        with self.assertRaisesRegex(RuntimeError,"checksum"):
            compare_pair(self.root,"heavy_sparse",self.iters)

    def test_missing_cpp_fu_audit_rejected(self):
        p=self.root/"heavy_sparse"/"private2"/"effective_config_audit.json"
        p.write_text(json.dumps({"mode":"private2","status":"OPEN"}))
        with self.assertRaisesRegex(RuntimeError,"effective-config gate"):
            read_run(self.root,"heavy_sparse","private2",self.iters)


if __name__=="__main__":
    unittest.main()
