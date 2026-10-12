#!/usr/bin/env python3
"""R3C P2 source-level ELF readelf gate regression; no target execution."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/bpu_b8_r3c_p2_build.py"
spec = importlib.util.spec_from_file_location("bpu8_r3c_p2", SCRIPT)
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)

VALID_HEADER = """ELF Header:
  Class:                             ELF64
  Data:                              2's complement, little endian
  Type:                              EXEC (Executable file)
  Machine:                           RISC-V
  Flags:                             0x5, RVC, double-float ABI
"""
STATIC_DYN = "\nThere is no dynamic section in this file.\n"

class RV64ELFHeaderTests(unittest.TestCase):
    def test_realistic_static_lp64d_readelf_passes(self):
        self.assertTrue(p2.is_static_rv64_lp64d(VALID_HEADER, STATIC_DYN))

    def test_rv32_rejected(self):
        self.assertFalse(p2.is_static_rv64_lp64d(
            VALID_HEADER.replace("ELF64", "ELF32"), STATIC_DYN))

    def test_wrong_isa_rejected(self):
        self.assertFalse(p2.is_static_rv64_lp64d(
            VALID_HEADER.replace("RISC-V", "AArch64"), STATIC_DYN))

    def test_wrong_abi_rejected(self):
        self.assertFalse(p2.is_static_rv64_lp64d(
            VALID_HEADER.replace("double-float ABI", "soft-float ABI"),
            STATIC_DYN))

    def test_dynamic_needed_rejected(self):
        self.assertFalse(p2.is_static_rv64_lp64d(
            VALID_HEADER,
            "Dynamic section at offset:\n 0x0000000000000001 (NEEDED) Shared library: [libc.so.6]"))

    def test_literal_slash_s_not_whitespace(self):
        bad_header=VALID_HEADER.replace("Class:                             ELF64",
                                        r"Class:\s+ELF64")
        self.assertFalse(p2.is_static_rv64_lp64d(bad_header, STATIC_DYN))

if __name__ == "__main__":
    unittest.main()
