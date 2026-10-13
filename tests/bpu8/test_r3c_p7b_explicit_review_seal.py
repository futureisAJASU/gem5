#!/usr/bin/env python3
"""P7B review packet manual-signoff barriers and SHA-bound sealing tests."""
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import sys
import unittest
import json

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p7b_explicit_review_seal as p7b

class P7BReviewSealTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.draft={
            "kind":"BPU8_R3C_P7A_LOCK_DRAFT_REQUIRES_REVIEW",
            "verdict":"PRE_RESULT_11x6_CONFIG_DRAFT_NOT_LOCKED_NOT_AUTHORIZED",
            "corpus_lock":"NOT_CREATED",
            "authorized_holdout_jobs":0,"actual_six_profile_jobs":0,
            "holdout_result_inspected":False,
            "target_case_count":11,"target_profiles_per_case":6,"target_jobs":66,
            "profile_order":list(p7b.EXPECTED_PROFILES),
            "linked_simulator_gem5_sha256":p7b.p7a.EXPECTED_GEM5,
            "scope":"INTERNAL_RESEARCH_FIRST_ROI_ONLY_NOT_OFFICIAL_COREMARK",
            "manual_historical_scope_acceptance":"REQUIRED_FOR_FUTURE_LOCK",
            "manual_license_and_use_conditions_acceptance":"REQUIRED_FOR_FUTURE_LOCK",
            "source_limited_prior_exposure":{
                "absolute_unseen_claim":False,
                "five_named_archives_checked":5,"pre_R3C_Git_files_checked":84},
            "source_evidence_sha256":dict(p7b.p7a.ORIGINAL_PASS_SHA256),
            "source_revisions":{"mibench":{"commit":"m0"},
                                "coremark":{"commit":"c0"}},
            "frozen_r3_geometry_sha256":"f"*64,
            "frozen_geometry_profiles":{
                p:{"total_bits":45736} for p in p7b.EXPECTED_PROFILES},
            "case_list":[],
        }
        for i,name in enumerate(p7b.EXPECTED_CASES):
            license_path=self.root/(name+".LICENSE")
            license_path.write_text(
                name+" specific terms and notices; full text must be reviewed")
            lic_sha=p7b.p2.sha(license_path)
            self.draft["case_list"].append({
                "case":name,
                "elf":{"path":str(self.root/name),"sha256":"a"*64,"size":39},
                "correctness_gate":("EEMBC_UPSTREAM_2K_PERFORMANCE_CRC_ONLY"
                                    if name=="coremark_performance"
                                    else "RV64_QEMU_REFERENCE"),
                "expected_process_exit_code":1 if name=="patricia" else 0,
                "g5_reference_outputs":{"first_roi_sha256":"b"*64},
                "license":{
                    "files":[{"path":str(license_path),"sha256":lic_sha}],
                    "case_terms":"MANUAL_REVIEW_PENDING",
                    "publication_or_binary_redistribution":"NOT_APPROVED",
                },
            })
        self.review=p7b.review_template(self.draft)

    def fill_explicit(self):
        self.review["reviewer_identifier"]="independent_research_author"
        self.review["review_date_utc"]="2026-10-13T05:00:00Z"
        h=self.review["historical_exposure_review"]
        h["decision"]=p7b.REVIEW_SCOPE_DECISION
        h["review_notes"]="Historical audit only covers the five archives and 84 Git records."
        p=self.review["protocol_review"]
        p["decision"]=p7b.REVIEW_PROTOCOL_DECISION
        p["review_notes"]="No metric peeking, retuning or swapping candidates after lock."
        for entry in self.review["per_case_license_review"]:
            entry["decision"]=p7b.REVIEW_CASE_DECISION
            entry["review_notes"]="Reviewed pinned original terms for private research only."

    def test_review_template_contains_11_PENDING_cases_and_is_not_approval(self):
        self.assertEqual(self.review["kind"],p7b.REVIEW_KIND)
        self.assertEqual(len(self.review["per_case_license_review"]),11)
        self.assertTrue(all(x["decision"]=="PENDING"
                            for x in self.review["per_case_license_review"]))
        self.assertEqual(self.review["historical_exposure_review"]["decision"],
                         "PENDING")
        self.assertEqual(self.review["protocol_review"]["decision"],"PENDING")

    def test_draft_identity_and_pre_result_scope_required(self):
        self.assertTrue(p7b.verify_draft(
            self.draft,p7b.EXPECTED_DRAFT_SHA256))
        with self.assertRaisesRegex(ValueError,"observed OCI PASS SHA"):
            p7b.verify_draft(self.draft,"0"*64)
        self.draft["case_list"][5]["expected_process_exit_code"]=0
        with self.assertRaisesRegex(ValueError,"Patricia"):
            p7b.verify_draft(self.draft,p7b.EXPECTED_DRAFT_SHA256)

    def test_review_cannot_pass_without_manual_signoff(self):
        with self.assertRaisesRegex(ValueError,"explicit reviewer ID"):
            p7b.validate_review(self.draft,self.review)

    def test_review_requires_all_11_license_reads_and_notes(self):
        self.fill_explicit()
        self.review["per_case_license_review"][3]["decision"]="PENDING"
        with self.assertRaisesRegex(ValueError,"susan_edges"):
            p7b.validate_review(self.draft,self.review)
        self.review["per_case_license_review"][3]["decision"]=p7b.REVIEW_CASE_DECISION
        self.review["per_case_license_review"][-1]["review_notes"]=""
        with self.assertRaisesRegex(ValueError,"coremark_performance"):
            p7b.validate_review(self.draft,self.review)

    def test_review_fails_if_pinned_license_bytes_mutated(self):
        self.fill_explicit()
        file=Path(self.review["per_case_license_review"][4]["license_files"][0]["path"])
        file.write_text("Modified GPL license bytes")
        with self.assertRaisesRegex(ValueError,"dijkstra"):
            p7b.validate_review(self.draft,self.review)

    def test_explicitly_reviewed_case_can_be_sealed_without_running(self):
        self.fill_explicit()
        self.assertTrue(p7b.validate_review(self.draft,self.review))
        lock=p7b.seal(self.draft,self.review,
                      p7b.EXPECTED_DRAFT_SHA256,"review file sha")
        self.assertEqual(lock["kind"],"BPU8_R3C_FIXED_CORPUS_LOCK_V01")
        self.assertEqual(lock["planned_jobs"],66)
        self.assertEqual(lock["simulator_runs_executed_at_sealing"],0)
        self.assertIn("PENDING_GIT_COMMIT",lock["verdict"])
        self.assertEqual(lock["third_party_redistribution_rights"],"NOT_GRANTED")
        self.assertEqual(lock["review_scope"],
                         "BOUNDED_HISTORICAL_NO_KNOWN_OVERLAP_NOT_ABSOLUTE_UNSEEN")

    def test_cannot_report_absolutely_unseen_evidence(self):
        self.fill_explicit()
        self.review["historical_exposure_review"]["limitations"][
            "absolute_unseen_input_proof"]=True
        with self.assertRaisesRegex(ValueError,"bounded historical"):
            p7b.validate_review(self.draft,self.review)

if __name__=="__main__":
    unittest.main()
