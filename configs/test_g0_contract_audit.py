"""Standalone fail-closed verifier regression; no gem5 binary required."""
import json
import tempfile
import unittest
from pathlib import Path

from g0_verify_effective_config import audit_run


class G0EffectiveConfigAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mode = "shared1"
        self.name = "system.cpu0.instQueues3.fuPool"
        self.config = self.root / "config.ini"
        self.log = self.root / "simulator.log"
        self.stats = self.root / "stats.txt"
        self.write_fixture()

    def write_fixture(self):
        n = self.name
        self.config.write_text(f"""
[system.cpu0.instQueues3]
fuPool={n}
[system.cpu1.instQueues3]
fuPool={n}
[{n}]
type=FUPool
FUList={n}.FUList0
pairRrArb=true
reactivePowerGating=false
predictiveWakeEnabled=false
rawPredictiveWakeEnabled=false
powerWakeLatency=0
powerIdleThreshold=8
[{n}.FUList0]
count=1
opList={n}.FUList0.opList0
[{n}.FUList0.opList0]
opClass=IntDiv
opLat=20
pipelined=false
""".strip()+"\n")
        self.log.write_text(
            f"G0_CXX_FU_POOL name={n} physical_units=1 pair_rr=1 "
            "reactive=0 decode=0 raw=0 latency=0 threshold=8\n"
            "G0_CONSTRUCTED_MANIFEST_JSON="
            + json.dumps({
                "mode": "shared1",
                "runtime_config_ini_and_cpp_instances_verified": False,
                "fpu_capability_manifest": [{"opClass": "FloatMultAcc"}]
            }) + "\n"
        )
        self.stats.write_text(
            "".join(f"{n}.{metric} 0 # synthetic\n" for metric in (
                "reactiveSleepTransitions",
                "reactiveWakingSamples",
                "reactivePowerBlockedRequests"
            ))
        )

    def test_all_constructed_counters_zero_and_count_one(self):
        output = audit_run(self.root, self.mode)
        self.assertEqual(output["pair_div_physical_units"], 1)
        self.assertEqual(output["performance_measurement_acceptance"], "OPEN")

    def test_wake_w0_but_reactive_true_fails(self):
        self.config.write_text(
            self.config.read_text().replace(
                "reactivePowerGating=false", "reactivePowerGating=true"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "gating FAIL"):
            audit_run(self.root, self.mode)

    def test_nonzero_sleep_counter_fails(self):
        self.stats.write_text(
            self.stats.read_text().replace(
                ".reactiveSleepTransitions 0", ".reactiveSleepTransitions 1"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "counter nonzero"):
            audit_run(self.root, self.mode)

    def test_missing_waking_stat_cannot_be_imputed_zero(self):
        self.stats.write_text(
            "\n".join(
                ln for ln in self.stats.read_text().splitlines()
                if ".reactiveWakingSamples" not in ln
            )
        )
        with self.assertRaisesRegex(RuntimeError, "UNOBSERVED"):
            audit_run(self.root, self.mode)

    def test_actual_cpp_two_fus_rejected_even_with_count_one_desc(self):
        self.log.write_text(
            self.log.read_text().replace(
                "physical_units=1", "physical_units=2"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "C\+\+ DIV FU count"):
            audit_run(self.root, self.mode)

    def test_source_manifest_cannot_self_certify_runtime(self):
        self.log.write_text(
            self.log.read_text().replace(
                '"runtime_config_ini_and_cpp_instances_verified": false',
                '"runtime_config_ini_and_cpp_instances_verified": true'
            )
        )
        with self.assertRaisesRegex(RuntimeError, "self-certify"):
            audit_run(self.root, self.mode)

    def test_no_cpp_record_is_invalid(self):
        self.log.write_text(
            "\n".join(
                line for line in self.log.read_text().splitlines()
                if not line.startswith("G0_CXX_FU_POOL")
            )
        )
        with self.assertRaisesRegex(RuntimeError, "inventory absent"):
            audit_run(self.root, self.mode)


if __name__ == "__main__":
    unittest.main()
