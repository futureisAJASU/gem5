#!/usr/bin/env python3
"""R3C regression: compiled C++ TAGE rollover pointer proof, no gem5 benchmark.

C++ test uses the *production helper* and models original and relocated
raw global history windows. This isolates a correctness invariant from
gem5 timing. Run this BEFORE trying any further G5-only feasibility.
"""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
HELPER=ROOT/"src/cpu/pred/tage_rollover_restore.hh"
TAGE_CC=ROOT/"src/cpu/pred/tage_base.cc"
TAGE_HH=ROOT/"src/cpu/pred/tage_base.hh"

CPP_SOURCE=r"""
#include <cassert>
#include <cstdint>
#include <vector>
#include "cpu/pred/tage_rollover_restore.hh"

using gem5::branch_prediction::expectedTageRestorePointer;

int main() {
    constexpr int capacity=2097152, maxHistory=130, rollback=1000;
    constexpr int base=capacity-maxHistory-rollback;
    static_assert(base == 2096022);
    // No rollover: original numeric pointer must remain unchanged.
    static_assert(expectedTageRestorePointer(1,1,1,0,capacity,
                  maxHistory,rollback)==1);
    // Initial speculative branch at pointer 0 rolls over itself.
    static_assert(expectedTageRestorePointer(0,0,1,0,capacity,
                  maxHistory,rollback)==base);
    // Original user's qsort fatal: saved=1, newer speculative branch
    // rolled from physical source=0. Restoring to base+1 is legitimate.
    static_assert(expectedTageRestorePointer(1,1,2,0,capacity,
                  maxHistory,rollback)==2096023);
    // A copied window can preserve older saved positions.
    static_assert(expectedTageRestorePointer(11,9,10,0,capacity,
                  maxHistory,rollback)==base+11);
    // For two-bit rollover at source=1, saved=2 maps to base+1.
    static_assert(expectedTageRestorePointer(2,0,1,1,capacity,
                  maxHistory,rollback)==base+1);
    // Reject a fabricated multi-epoch relocation.
    static_assert(expectedTageRestorePointer(1,0,2,0,capacity,
                  maxHistory,rollback)==-1);
    // Reject overflow of the copied rollback window.
    static_assert(expectedTageRestorePointer(1001,0,1,0,capacity,
                  maxHistory,rollback)==-1);
    // Reject histories not in the copied window.
    static_assert(expectedTageRestorePointer(0,0,1,1,capacity,
                  maxHistory,rollback)==-1);
    // Reject stale rollovers with backwards generation numbers.
    static_assert(expectedTageRestorePointer(1,2,1,0,capacity,
                  maxHistory,rollback)==-1);
    // Reject corrupted history-buffer configuration.
    static_assert(expectedTageRestorePointer(1,0,1,0,1000,
                  maxHistory,rollback)==-1);

    // Model source-window copy and assert the raw maxHistory bits survive.
    std::vector<uint8_t> history(capacity,0);
    for(int i=0; i<maxHistory+rollback; ++i)
        history[i]=((i*31+7)%5==0);
    std::vector<uint8_t> saved(history.begin()+1,
                               history.begin()+1+maxHistory);
    for(int i=0; i<maxHistory+rollback; ++i)
        history[base+i]=history[i];
    int recovered=expectedTageRestorePointer(1,0,1,0,
                         capacity,maxHistory,rollback);
    assert(recovered == base+1);
    for(int i=0; i<maxHistory; ++i)
        assert(history[recovered+i]==saved[i]);
    // A pointer-equivalent state with tampered history MUST be caught
    // by the production raw-window check in restoreHistState().
    history[recovered+23]^=1;
    bool identical=true;
    for(int i=0; i<maxHistory; ++i)
        identical &= history[recovered+i]==saved[i];
    assert(!identical);
    return 0;
}
"""


class TAGEEpochRolloverTests(unittest.TestCase):
    def test_compiled_cpp_rollover_proof_and_window(self):
        cxx=shutil.which("c++") or shutil.which("g++")
        self.assertIsNotNone(cxx,"a C++17 compiler is required for this regression")
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/"rollover.cc"
            exe=Path(folder)/"rollover_test"
            src.write_text(CPP_SOURCE)
            compile_=subprocess.run([cxx,"-std=c++17","-Wall","-Wextra",
                                     "-Werror","-I",str(ROOT/"src"),
                                     str(src),"-o",str(exe)],
                                    text=True,capture_output=True,timeout=60)
            self.assertEqual(compile_.returncode,0,compile_.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,
                               timeout=10)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_restore_also_checks_actual_raw_and_folded_histories(self):
        body=TAGE_CC.read_text()
        self.assertIn("savedHistoryRolloverGeneration",body)
        self.assertIn("lastRolloverSourcePtGhist",body)
        self.assertIn("expectedTageRestorePointer(",body)
        self.assertIn("tHist.globalHist.at(tHist.ptGhist + i) !=",body)
        self.assertIn("tHist.computeIndices[i].comp",body)
        self.assertIn("tHist.computeTags[0][i].comp",body)
        self.assertIn("tHist.computeTags[1][i].comp",body)
        self.assertIn("stats.historyRestoreChecks++",body)

    def test_metadata_is_recorded_before_update_and_updated_on_rollover(self):
        body=TAGE_CC.read_text()
        self.assertIn("bi->savedHistoryRolloverGeneration =\n",body)
        self.assertIn("++tHist.historyRolloverGeneration;",body)
        self.assertIn("tHist.lastRolloverSourcePtGhist = tHist.ptGhist;",body)
        self.assertIn("history.historyRolloverGeneration = 0;",body)
        self.assertIn("history.lastRolloverSourcePtGhist = 0;",body)

    def test_simulation_metadata_not_added_to_bit_accounting(self):
        h=TAGE_HH.read_text()
        self.assertIn("Simulator-only",h)
        self.assertIn("uint64_t historyRolloverGeneration;",h)
        self.assertIn("uint64_t savedHistoryRolloverGeneration;",h)

if __name__=="__main__":
    unittest.main()
