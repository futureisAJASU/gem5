#!/usr/bin/env python3
"""Offline synthetic test for MiBench RV64 LP64 sidecar patch anchors and custody."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import bpu_b8_r3c_p2b_lp64_overlay as p2b
import bpu_b8_r3c_p2_build as p2

class SidecarTests(unittest.TestCase):
    def test_patricia_rpc_header_removed_only_from_staged_copy(self):
        raw=(b'#include <stdio.h>\r\n#include <rpc/rpc.h>\r\n'
             b'#include <netinet/in.h>\r\n')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            original=root/"pristine.c"
            original.write_bytes(raw)
            staged=root/"patricia_test.c"
            staged.write_bytes(original.read_bytes())
            patches=[]
            p2b.modify_patricia(root,patches)
            self.assertEqual(original.read_bytes(),raw)
            self.assertNotIn(b'#include <rpc/rpc.h>',staged.read_bytes())
            self.assertIn(b'#include <netinet/in.h>',staged.read_bytes())
            self.assertEqual(len(patches),1)
            self.assertNotEqual(patches[0]["source_sha256"],patches[0]["patched_sha256"])

    def test_rijndael_lp64_patches_and_crlf(self):
        header=(b'typedef unsigned char   byte;           /* must be an 8-bit storage unit */\r\n'
                b'typedef unsigned long   word;           /* must be a 32-bit storage unit */\r\n')
        orig=(b'{   static unsigned long a[2], mt = 1, count = 4;\r\n'
              b'            *(unsigned long*)r = RAND(a[0], a[1]);\r\n'
              b'    fpos_t          flen;\r\n'
              b'    fgetpos(fin, &flen);\r\n'
              b'    inbuf[0] = ((char)flen & 15) | (inbuf[0] & ~15);\r\n')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"aes.h").write_bytes(header)
            (root/"aesxam.c").write_bytes(orig)
            patches=[]
            p2b.modify_rijndael(root,patches)
            self.assertEqual(len(patches),6)
            self.assertIn(b"typedef uint32_t        word;",(root/"aes.h").read_bytes())
            self.assertIn(b"uint32_t sample = RAND(a[0], a[1]);",(root/"aesxam.c").read_bytes())
            self.assertIn(b"memcpy(r, &sample, sizeof r);",(root/"aesxam.c").read_bytes())
            self.assertIn(b"flen = ftell(fin);",(root/"aesxam.c").read_bytes())
            self.assertNotIn(b"fgetpos(fin, &flen)",(root/"aesxam.c").read_bytes())
            self.assertNotIn(b"*(unsigned long*)r",(root/"aesxam.c").read_bytes())
            self.assertIn(b"\r\n", (root/"aesxam.c").read_bytes())
            self.assertFalse(any(b"\n" in (root/x).read_bytes().replace(b"\r\n", b"")
                                 for x in ("aes.h","aesxam.c")))

    def test_patch_anchor_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/"patricia_test.c"
            p.write_bytes(b'#include <stdio.h>\n')
            with self.assertRaisesRegex(ValueError, "patch anchor count 0"):
                p2b.modify_patricia(root,[])
            self.assertEqual(p.read_bytes(),b'#include <stdio.h>\n')

    def test_patch_duplicate_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/"patricia_test.c"
            p.write_bytes(b'#include <rpc/rpc.h>\n#include <rpc/rpc.h>\n')
            with self.assertRaisesRegex(ValueError, "patch anchor count 2"):
                p2b.modify_patricia(root,[])

if __name__ == "__main__":
    unittest.main()
