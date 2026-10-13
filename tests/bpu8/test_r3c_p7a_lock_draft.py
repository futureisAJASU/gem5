#!/usr/bin/env python3
"""P7A lock-draft whole-11 integration and fail-closed evidence-mutation tests."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p7a_lock_draft as p7

class P7ALockDraftTests(unittest.TestCase):
    def setUp(self):
        self.working=tempfile.TemporaryDirectory()
        self.addCleanup(self.working.cleanup)
        self.d=Path(self.working.name)
        self.gem5=self.d/"gem5.opt"
        self.gem5.write_bytes(b"dummy in-process sim hash fixture")
        self.prereg=self.d/"prereg.json"
        self.matrix=self.d/"r3.json"
        self.fingerprints=dict(p7.ORIGINAL_PASS_SHA256)
        self.fingerprints.update(p1="p1 frozen SHA",p4a="p4a frozen SHA")
        self.dev=["aha-mont64","crc32","cubic","edn","huffbench",
                  "matmult-int","minver","nbody","nettle-aes",
                  "nettle-sha256","nsichneu","picojpeg","qrduino",
                  "sglib-combined","slre","st","statemate","ud","wikisort"]
        geometry={name:{"total_bits":45736,
                        "bp_type":"tage-r3-locked-"+name}
                  for name in p7.EXPECTED_6}
        self.matrix.write_text(json.dumps({
            "experiment":"BPU8_R3_G5_LOCK_HASH_GEOMETRY_V01",
            "profiles":geometry,"workloads":self.dev}))
        self.prereg.write_text(json.dumps({
            "status":"PRE_RESULT_CANDIDATE_SUITE_NOT_YET_FEASIBILITY_LOCKED",
            "no_actual_holdout_runs":True,
            "tracked_bits_each":45736,
            "suite_candidates":[{"id":x} for x in p7.p2.ORDER],
            "fixed_profiles":list(p7.EXPECTED_6),
        }))
        self.plan={
            "kind":"BPU8_R3C_P4A_STATIC_SE_INTERFACE_NOT_CORPUS_LOCK",
            "corpus_lock":False,
            "future_six_comparators":list(p7.EXPECTED_6),
            "dev_full19_names":self.dev,
            "cases":{},
        }
        self.p6a={
            "kind":"R3C_P6A_PRELOCK_SOURCE_CUSTODY_SNAPSHOT",
            "verdict":p7.P6A_VERDICT,
            "r3c_corpus_lock":"NOT_CREATED",
            "historical_unseen_workload_independence":"UNVERIFIED",
            "comparison_performance_started":False,
            "p4a_plan_sha256":self.fingerprints["p4a"],
            "simulator_gem5_sha256":p7.EXPECTED_GEM5,
            "six_profiles":list(p7.EXPECTED_6),
            "logical_bits_each":45736,
            "candidate_performance_jobs_NOT_authorized":66,
            "prereg_source_sha256":p7.p2.sha(self.prereg),
            "case_count":11,
            "cases":[],
        }
        self.p6b={
            "p6a_sha256":self.fingerprints["p6a"],
            "verdict":"PRIOR_EVIDENCE_DISCOVERY_REQUIRES_COMPLETENESS_REVIEW_NO_CORPUS_LOCK",
            "corpus_lock":"NOT_AUTHORIZED",
            "prior_sources":[{} for _ in range(5)],
            "prior_exact_candidate_SHA_occurrences":[],
            "skipped_or_unreadable_members":[],
        }
        self.p6c={
            "p6a_sha256":self.fingerprints["p6a"],
            "p6b_sha256":self.fingerprints["p6b"],
            "verdict":"PRE_R3C_GIT_SOURCE_BOUNDARY_REVIEWED_HISTORICAL_COMPLETENESS_UNVERIFIED_NO_LOCK",
            "reference_file_count":0,
            "historic_source_file_count":84,
            "historical_registries_recovered":[{} for _ in range(5)],
        }
        self.p6d={
            "kind":"BPU8_R3C_P6D_FINAL_PRELOCK_SOURCE_AND_LICENSE_DOSSIER",
            "verdict":p7.P6D_VERDICT,
            "r3c_corpus_lock":"NOT_CREATED",
            "manual_license_review":"REQUIRED",
            "manual_historical_exposure_signoff":"REQUIRED",
            "authorized_six_profile_holdout_runs":0,
            "p1_source_sha256":self.fingerprints["p1"],
            "p6a_sha256":self.fingerprints["p6a"],
            "p6b_sha256":self.fingerprints["p6b"],
            "p6c_sha256":self.fingerprints["p6c"],
            "source_and_licensing_records":[],
            "source_checkouts":{"mibench":{"commit":"pinned mibench"},
                                "coremark":{"commit":"pinned coremark"}},
        }
        for idx,name in enumerate(p7.p2.ORDER):
            elf=self.d/(name+".rv64.elf")
            elf.write_bytes((name+":RV64 dummy binary").encode())
            inputs=[]
            if name=="basicmath":
                data=self.d/"basicmath.input"
                data.write_bytes(b"input binary original")
                inputs=[{"name":"small.dat","source_path":str(data),
                         "sha256":p7.p2.sha(data),"size":data.stat().st_size}]
            case={
                "binary":str(elf),"binary_sha256":p7.p2.sha(elf),
                "argv":["small"],"input_files":inputs,
                "expected_process_exit_code":1 if name=="patricia" else 0,
                "correctness_gate":"RV64_QEMU_reference",
                "stdin_file_relative":None,
                "program_output_file_relative":None,
                "source_kind":"ORIGINAL_P1_PINNED",
            }
            self.plan["cases"][name]=case
            self.p6a["cases"].append({
                "case":name,"rv64_elf_sha256":case["binary_sha256"],
                "rv64_elf_path":str(elf.resolve()),"argv":case["argv"],
                "input_files":[{k:i[k] for k in ("name","sha256","size")}
                               for i in inputs],
                "expected_process_exit_code":case["expected_process_exit_code"],
                "correctness_gate":case["correctness_gate"],
                "stdin_file_relative":None,
                "program_output_file_relative":None,
                "original_g5_stdout_sha256":"a"*64,
                "original_g5_stderr_sha256":"b"*64,
                "original_g5_output_file_sha256":None,
                "original_g5_roi_sha256":"c"*64,
            })
            self.p6d["source_and_licensing_records"].append({
                "case":name,"license_material_present":True,
                "license_files":[{"sha256":"d"*64,
                                  "path":"/pinned/"+name+"/LICENSE"}],
            })

    def run_draft(self):
        sha=p7.p2.sha
        def fake_sha(path):
            if Path(path)==self.gem5:
                return p7.EXPECTED_GEM5
            return sha(Path(path))
        with (patch.object(p7.p4a,"CANDIDATE_JSON",self.prereg),
              patch.object(p7.p4a,"R3_MATRIX",self.matrix),
              patch.object(p7.p2,"sha",side_effect=fake_sha)):
            return p7.validate_chain(
                {},self.plan,self.p6a,self.p6b,self.p6c,self.p6d,
                self.fingerprints,self.gem5,{})

    def test_complete_11x6_draft_has_zero_authorization(self):
        draft=self.run_draft()
        self.assertEqual(draft["target_jobs"],66)
        self.assertEqual(len(draft["case_list"]),11)
        self.assertEqual(draft["locked_case_count"],0)
        self.assertEqual(draft["corpus_lock"],"NOT_CREATED")
        self.assertEqual(draft["authorized_holdout_jobs"],0)
        self.assertFalse(draft["source_limited_prior_exposure"]["absolute_unseen_claim"])

    def test_mutated_elf_is_blocked(self):
        case=self.d/"basicmath.rv64.elf"
        case.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError,"ELF content differs"):
            self.run_draft()

    def test_mutated_input_is_blocked(self):
        source=self.d/"basicmath.input"
        source.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError,"source input changed"):
            self.run_draft()

    def test_fake_prior_audit_sha_is_blocked(self):
        self.fingerprints["p6d"]="0"*64
        with self.assertRaisesRegex(ValueError,"original PASS digest"):
            self.run_draft()

    def test_changed_six_geometry_list_is_blocked(self):
        self.plan["future_six_comparators"][4]="custom_retuned_TG7"
        with self.assertRaisesRegex(ValueError,"P4A original case/profiles altered"):
            self.run_draft()

    def test_unsigned_license_state_required(self):
        self.p6d["manual_license_review"]="APPROVED"
        with self.assertRaisesRegex(ValueError,"P6D pending human review"):
            self.run_draft()

if __name__=="__main__":
    unittest.main()
