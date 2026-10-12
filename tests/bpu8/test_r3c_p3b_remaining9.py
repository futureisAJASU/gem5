#!/usr/bin/env python3
"""R3C P3B synthetic correctness oracle tests: not simulator benchmarks."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bpu_b8_r3c_p3b_remaining9 as p3b


class P3BOracleTests(unittest.TestCase):
    def test_exact_original_case_set_and_task_count(self):
        self.assertEqual(len(p3b.CASES), 9)
        self.assertEqual(len(set(p3b.CASES)), 9)
        self.assertEqual(set(p3b.TASKS) | {"coremark_performance"}, set(p3b.CASES))

    def test_bitcount_host_timing_ignored_but_bits_kept(self):
        a=(b"Algorithm one                          > Time:  0.001 sec.; Bits: 100\n"
           b"Algorithm two                          > Time:  0.002 sec.; Bits: 100\n"
           b"Algorithm three                        > Time:  0.003 sec.; Bits: 100\n"
           b"\nBest  > Algorithm one\nWorst > Algorithm three\n")
        b=a.replace(b"0.001",b"1.001").replace(b"0.002",b"1.002")
        b=b.replace(b"Best  > Algorithm one",b"Best  > Algorithm two")
        self.assertEqual(p3b.bitcount_signature(a),p3b.bitcount_signature(b))
        self.assertEqual(len(p3b.bitcount_signature(a)),3)
        c=b.replace(b"Bits: 100",b"Bits: 101",1)
        self.assertNotEqual(p3b.bitcount_signature(a),p3b.bitcount_signature(c))

    def test_bitcount_needs_three_methods(self):
        with self.assertRaises(ValueError):
            p3b.bitcount_signature(b"Program runtime 0.05 seconds")

    def test_fft_printed_vector_tolerance_fixed(self):
        a=b"RealOut:\n"+(b"0.000000 \t"*128)+b"\nImagOut:\n"+(b"1.000000 \t"*128)
        b=b"RealOut:\n"+(b"0.000001 \t"*128)+b"\nImagOut:\n"+(b"1.000000 \t"*128)
        c=b"RealOut:\n"+(b"0.001000 \t"*128)+b"\nImagOut:\n"+(b"1.000000 \t"*128)
        self.assertTrue(p3b.fft_signature(a,b)["passed"])
        self.assertFalse(p3b.fft_signature(a,c)["passed"])
        self.assertEqual(p3b.FFT_ATOL,1e-4)
        self.assertEqual(p3b.FFT_RTOL,1e-5)

    def test_fft_nan_infinity_rejected(self):
        a=b"RealOut:\n"+(b"0.000000 \t"*128)+b"\nImagOut:\n"+(b"1.000000 \t"*128)
        with self.assertRaises(ValueError):
            p3b.fft_signature(a,b"RealOut:\nNaN\nImagOut:\ninf")

    def test_coremark_performance_published_2k_crc(self):
        self.assertEqual(p3b.COREMARK_EXPECTED["performance"],
                         {"seedcrc":"e9f5","crclist":"e714",
                          "crcmatrix":"1fd7","crcstate":"8e3a"})
        self.assertEqual(p3b.COREMARK_EXPECTED["validation"],
                         {"seedcrc":"18f2","crclist":"e3c1",
                          "crcmatrix":"0747","crcstate":"8d84"})

    def test_coremark_2k_crc_accepts_both_seeds(self):
        for mode, expected in p3b.COREMARK_EXPECTED.items():
            raw=b"\n".join(
                (b"seedcrc          : 0x"+expected["seedcrc"].encode(),
                 b"[0]crclist       : 0x"+expected["crclist"].encode(),
                 b"[0]crcmatrix     : 0x"+expected["crcmatrix"].encode(),
                 b"[0]crcstate      : 0x"+expected["crcstate"].encode(),
                 b"ERROR! Must execute for at least 10 secs for a valid result!",
                 b"Errors detected"))
            result=p3b.coremark_evaluate(raw,raw,mode)
            self.assertTrue(result["passed"])
            self.assertFalse(result["official_score_validated"])

    def test_coremark_corrupt_crc_rejected(self):
        e=p3b.COREMARK_EXPECTED["performance"]
        raw=b"\n".join((b"seedcrc : 0xe9f5",b"[0]crclist : 0xe714",
                        b"[0]crcmatrix : 0x1fd7",b"[0]crcstate : 0x8e3a"))
        bad=raw.replace(b"0xe714",b"0xe715")
        self.assertTrue(p3b.coremark_evaluate(raw,raw,"performance")["passed"])
        self.assertFalse(p3b.coremark_evaluate(raw,bad,"performance")["passed"])

    def test_coremark_duplicate_crc_rejected(self):
        raw=b"seedcrc : 0xe9f5\nseedcrc : 0xe9f5\n"
        with self.assertRaisesRegex(ValueError, "duplicate CoreMark"):
            p3b.coremark_crc(raw)

    def test_coremark_unknown_seed_rejected(self):
        raw=b"\n".join((b"seedcrc : 0xe9f5",b"[0]crclist : 0xe714",
                        b"[0]crcmatrix : 0x1fd7",b"[0]crcstate : 0x8e3a",
                        b"Cannot validate operation for these seed values"))
        self.assertFalse(p3b.coremark_evaluate(raw,raw,"performance")["passed"])

if __name__ == "__main__":
    unittest.main()
