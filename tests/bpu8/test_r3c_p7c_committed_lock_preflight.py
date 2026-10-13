#!/usr/bin/env python3
"""P7C true Git HEAD byte custody; never mistake untracked/drafted lock for frozen."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p7c_committed_lock_preflight as p7c

class P7CCommittedGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd=Path(self.tmp.name)
        def cmd(*parts):
            subprocess.run(["git",*parts],cwd=self.cwd,check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.cmd=cmd
        self.cmd("init","-q")
        self.cmd("config","user.email","p7c-test@example.invalid")
        self.cmd("config","user.name","P7C Test")
        self.out=self.cwd/"docs/r3c_corpus_lock.json"
        self.out.parent.mkdir()
        (self.cwd/"README").write_text("R3C P7C\n")
        self.cmd("add","README")
        self.cmd("commit","-qm","initial")
        self.root_patch=patch.object(p7c.p2,"ROOT",self.cwd)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_untracked_lock_is_not_a_freeze(self):
        self.out.write_text('{"verdict":"UNTRACKED"}\n')
        with self.assertRaisesRegex(ValueError,"not tracked"):
            p7c.verify_committed_lock(self.out)

    def test_git_committed_exact_bytes_allowed(self):
        self.out.write_text('{"verdict":"COMMITTED"}\n')
        self.cmd("add","docs/r3c_corpus_lock.json")
        self.cmd("commit","-qm","freeze literal lock")
        head,digest=p7c.verify_committed_lock(self.out)
        self.assertEqual(len(head),40)
        self.assertEqual(digest,p7c.p2.sha(self.out))

    def test_dirty_committed_lock_is_rejected(self):
        self.out.write_text('{"verdict":"ORIGINAL"}\n')
        self.cmd("add","docs/r3c_corpus_lock.json")
        self.cmd("commit","-qm","freeze")
        self.out.write_text('{"verdict":"CHANGED"}\n')
        with self.assertRaisesRegex(ValueError,"uncommitted modifications"):
            p7c.verify_committed_lock(self.out)

    def test_git_staged_lock_change_is_rejected(self):
        self.out.write_text('{"verdict":"ORIGINAL"}\n')
        self.cmd("add","docs/r3c_corpus_lock.json")
        self.cmd("commit","-qm","freeze")
        self.out.write_text('{"verdict":"STAGED_CHANGE"}\n')
        self.cmd("add","docs/r3c_corpus_lock.json")
        with self.assertRaisesRegex(ValueError,"uncommitted modifications"):
            p7c.verify_committed_lock(self.out)

    def test_tracked_uncommitted_unrelated_source_change_is_rejected(self):
        self.out.write_text('{"verdict":"ORIGINAL"}\n')
        self.cmd("add","docs/r3c_corpus_lock.json")
        self.cmd("commit","-qm","freeze")
        (self.cwd/"README").write_text("modified code after frozen")
        with self.assertRaisesRegex(ValueError,"uncommitted modifications"):
            p7c.verify_committed_lock(self.out)

    def test_script_cannot_execute_geometry_comparison(self):
        src=(ROOT/"scripts/bpu_b8_r3c_p7c_committed_lock_preflight.py").read_text()
        self.assertIn('"comparison_executions_completed_by_this_tool":0',src)
        self.assertIn("future_runner_must_recheck_every_gate",src)
        self.assertIn('"HEAD:"+LOCK_REL',src)

if __name__=="__main__":
    unittest.main()
