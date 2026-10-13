#!/usr/bin/env python3
"""P7B AI-assisted license review: exact SHA, literal anchors, real source of signoff."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p7b_explicit_review_seal as p7b
import bpu_b8_r3c_p7b_ai_assisted_ack as assisted

class AssistedLicenseTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        notes=[]
        self.draft={"case_list":[]}
        for name in p7b.EXPECTED_CASES:
            file=self.root/(name+".LICENSE")
            file.write_text(name+" anchored usage clause, private-only")
            entry={"path":str(file),"sha256":p7b.p2.sha(file)}
            self.draft["case_list"].append({
                "case":name,"license":{"files":[entry]}})
            notes.append({
                "case":name,
                "required_literal_license_phrases":["anchored usage clause"],
                "model_summary":name+" is source reviewed for restricted nonredistribution research.",
            })
        self.policy=self.root/"assisted_policy.json"
        self.policy.write_text(json.dumps({
            "kind":"BPU8_R3C_P7B_AI_ASSISTED_LICENSE_NOTES_V01",
            "scope":"PRIVATE_INTERNAL_ACADEMIC_ONLY_NO_SOURCE_OR_BINARY_DISTRIBUTION",
            "cases":notes,
        }))
        self.patches=[
            patch.object(assisted,"SOURCE",self.policy),
            patch.object(p7b,"ASSISTED_NOTES",self.policy),
            patch.object(p7b,"verify_draft",return_value=True),
        ]
        for x in self.patches:x.start()
        self.addCleanup(lambda: [x.stop() for x in self.patches[::-1]])
        self.pending=p7b.review_template(self.draft)
        self.brief=lambda:assisted.make_brief(
            self.draft,self.pending,p7b.EXPECTED_DRAFT_SHA256,
            "original pending sha")

    def test_all_11_brief_status_stays_unsigned(self):
        b=self.brief()
        self.assertEqual(len(b["cases"]),11)
        self.assertTrue(all(r["review_status"].endswith("NOT_YET_ACKNOWLEDGED")
                            for r in b["cases"]))
        self.assertEqual(b["assistant_summary_source_sha256"],p7b.p2.sha(self.policy))
        self.assertEqual(self.pending["historical_exposure_review"]["decision"],"PENDING")

    def test_phrase_mismatch_fails_closed(self):
        p=self.root/"basicmath.LICENSE"
        p.write_text("different original")
        with self.assertRaisesRegex(ValueError,"pinned original license bytes changed"):
            self.brief()
        self.draft["case_list"][0]["license"]["files"][0]["sha256"]=p7b.p2.sha(p)
        self.pending["per_case_license_review"][0]["license_files"][0]["sha256"]=p7b.p2.sha(p)
        with self.assertRaisesRegex(ValueError,"differs from AI-reviewed source"):
            self.brief()

    def test_case_reordered_fails_closed(self):
        self.pending["per_case_license_review"][0]["case"]="different"
        with self.assertRaisesRegex(ValueError,"11.*unsigned review|eleven individual|original P7B"):
            self.brief()

    def fill(self):
        self.pending["review_method"]=p7b.ASSISTED_METHOD
        self.pending["ai_assisted_notes_sha256"]=p7b.p2.sha(self.policy)
        self.pending["acknowledgement_source"]="USER_INTERACTIVE_TERMINAL_ACK"
        self.pending["reviewer_identifier"]="operator"
        self.pending["review_date_utc"]="2026-10-13T07:00:00Z"
        h=self.pending["historical_exposure_review"]
        h["decision"]=p7b.REVIEW_SCOPE_DECISION
        h["review_notes"]="Bounded 5 archives and 84 Git files only, possible missing OCI runs."
        p=self.pending["protocol_review"]
        p["decision"]=p7b.REVIEW_PROTOCOL_DECISION
        p["review_notes"]="No metric peeking and no geometry retuning before locked six-way campaign."
        for entry in self.pending["per_case_license_review"]:
            entry["decision"]=p7b.REVIEW_CASE_DECISION
            entry["review_notes"]=(
                "AI_ASSISTED_PINNED_SOURCE_CHECK: operator reviewed brief, no redistribution.")

    def test_assisted_review_validates_explicit_mode(self):
        self.fill()
        self.assertTrue(p7b.validate_review(self.draft,self.pending))
        sealed=p7b.seal(self.draft,self.pending,
                        p7b.EXPECTED_DRAFT_SHA256,"pending SHA")
        self.assertEqual(sealed["review_method"],p7b.ASSISTED_METHOD)
        self.assertEqual(sealed["acknowledgement_source"],
                         "USER_INTERACTIVE_TERMINAL_ACK")
        self.assertEqual(sealed["simulator_runs_executed_at_sealing"],0)

    def test_assisted_false_method_or_changed_source_rejected(self):
        self.fill()
        self.pending["acknowledgement_source"]="AUTOMATED_ASSISTANT_APPROVED"
        with self.assertRaisesRegex(ValueError,"acknowledgement missing"):
            p7b.validate_review(self.draft,self.pending)
        self.pending["acknowledgement_source"]="USER_INTERACTIVE_TERMINAL_ACK"
        self.policy.write_text("{}")
        with self.assertRaisesRegex(ValueError,"summary SHA"):
            p7b.validate_review(self.draft,self.pending)

    def test_missing_explicit_assisted_notes_rejected(self):
        self.fill()
        self.pending["per_case_license_review"][5]["review_notes"]="User read a summary"
        with self.assertRaisesRegex(ValueError,"patricia"):
            p7b.validate_review(self.draft,self.pending)

if __name__=="__main__":
    unittest.main()
