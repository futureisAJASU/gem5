/*
 * C3 PC_BIAS standalone directed correctness tests.
 * This intentionally uses real C++ predictor state and never fabricates
 * gem5 ROI cycle/MPKI data.
 */
#include <cassert>
#include <cstdint>
#include <stdexcept>

#include "cpu/pred/little_c3_pc_bias.hh"

using gem5::branch_prediction::LittleC3PcBias;

static void
testColdAndSaturation()
{
    LittleC3PcBias c3({128, 1, 10, 3, 2, 2});
    assert(c3.logicalBits() == 2048);
    assert(c3.entryCount() == 128);
    constexpr uint64_t pc = 0x480;
    auto cold = c3.lookup(pc, true);
    assert(cold.eligible && !cold.tagHit && !cold.wouldFlip);
    assert(cold.score == 0);

    // A single mispredicted G5 event cannot cause an immediate override.
    auto u1 = c3.train(cold, true);
    assert(u1.allocated && u1.trained && !u1.evicted);
    auto once = c3.lookup(pc, true);
    assert(once.tagHit && once.score == 1 && !once.wouldFlip);

    c3.train(once, true);
    auto twice = c3.lookup(pc, true);
    assert(twice.score == 2 && twice.wouldFlip);

    for (int i = 0; i < 20; ++i) {
        c3.train(c3.lookup(pc, true), true);
    }
    assert(c3.lookup(pc, true).score == 3); // signed three-bit max
    for (int i = 0; i < 20; ++i) {
        c3.train(c3.lookup(pc, true), false);
    }
    auto end = c3.lookup(pc, true);
    assert(end.score == -4 && !end.wouldFlip);
}

static void
testTagAliasAndCollisionProtection()
{
    LittleC3PcBias c3({128, 1, 10, 3, 2, 2});
    const uint64_t a = 0x240;
    const uint64_t b = a + 256; // same 7-bit index, different tag
    auto first = c3.lookup(a, true);
    auto alloc = c3.train(first, true);
    assert(alloc.allocated);
    assert(c3.lookup(a, true).tagHit);
    const auto mismatch = c3.lookup(b, true);
    assert(mismatch.index == first.index && mismatch.tag != first.tag);
    assert(!mismatch.tagHit && !mismatch.wouldFlip);

    // The first collision ages the prior entry rather than falsely
    // training or predicting against its tag.
    auto blocked = c3.train(mismatch, true);
    assert(blocked.collisionBlocked && !blocked.trained);
    assert(c3.lookup(a, true).tagHit);
    auto replaced = c3.train(c3.lookup(b, true), false);
    assert(replaced.evicted && replaced.allocated);
    assert(!c3.lookup(a, true).tagHit);
    assert(c3.lookup(b, true).tagHit);
    assert(c3.lookup(b, true).score == -1);
}

static void
testGateAndSavedLookupMetadata()
{
    LittleC3PcBias c3({64, 1, 10, 3, 2, 2});
    assert(c3.logicalBits() == 1024);
    constexpr uint64_t pc = 0x560;
    const auto off = c3.lookup(pc, false);
    assert(!off.eligible && !off.tagHit && !off.wouldFlip);
    const auto noWrite = c3.train(off, true);
    assert(!noWrite.trained);
    assert(!c3.lookup(pc, true).tagHit);

    // The prediction metadata is a value snapshot, not a live table
    // pointer. An older branch can train while a younger lookup remains
    // in flight, without retroactively changing its saved outcome.
    auto old = c3.lookup(pc, true);
    assert(!old.tagHit);
    c3.train(old, true);
    auto young = c3.lookup(pc, true);
    assert(young.score == 1 && !young.wouldFlip);
    c3.train(old, true);
    assert(!young.wouldFlip && young.score == 1);
    assert(c3.lookup(pc, true).wouldFlip);
}

static void
testPcShiftAndWidthConfiguration()
{
    LittleC3PcBias c3({256, 1, 10, 3, 2, 2});
    assert(c3.logicalBits() == 4096);
    // A branch at a 2-byte boundary has its own index (RV64C safe).
    auto p = c3.lookup(0x200, true);
    auto q = c3.lookup(0x202, true);
    assert(p.index != q.index);
    assert(c3.lookup(0x200, true).index == p.index);

    bool failed = false;
    try {
        LittleC3PcBias invalid({96, 1, 10, 3, 2, 2});
        (void)invalid;
    } catch (const std::invalid_argument&) {
        failed = true;
    }
    assert(failed);
    failed = false;
    try {
        LittleC3PcBias invalid({128, 1, 10, 3, 2, 5});
        (void)invalid;
    } catch (const std::invalid_argument&) {
        failed = true;
    }
    assert(failed);
}

int
main()
{
    testColdAndSaturation();
    testTagAliasAndCollisionProtection();
    testGateAndSavedLookupMetadata();
    testPcShiftAndWidthConfiguration();
    return 0;
}
