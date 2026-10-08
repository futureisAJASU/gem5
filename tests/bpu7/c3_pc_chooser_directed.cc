/*
 * C3 independent PC-bias + disagreement-trained chooser, P1.
 * Standalone production-header tests; no fake gem5 ROI performance data.
 */
#include <cassert>
#include <cstdint>
#include <stdexcept>
#include "cpu/pred/little_c3_pc_chooser.hh"

using gem5::branch_prediction::LittleC3PcChooser;

static void
testNoColdOrSpuriousG5Inversion()
{
    LittleC3PcChooser c({128, 1, 10, 2, 3});
    assert(c.logicalBits() == 128 * 17);
    constexpr uint64_t pc = 0x220;
    auto a = c.lookup(pc, true, true);
    assert(a.eligible && !a.tagHit && !a.wouldOverride);

    // G5 wrong once does NOT imply the next G5 prediction should flip.
    auto u = c.train(a, false);
    assert(u.allocated && u.rowWrite && !u.chooserUpdated);
    a = c.lookup(pc, true, true);
    assert(a.tagHit && a.c3Taken == false);
    assert(a.disagrees && !a.strongDirection);
    assert(!a.wouldOverride);
    assert(a.chooserCount == 1);
}

static void
testChooserLearnsComparativeAccuracyAndForgets()
{
    LittleC3PcChooser c({128, 1, 10, 2, 3});
    constexpr uint64_t pc = 0x420;
    c.train(c.lookup(pc, true, true), false); // cold N, dir=1
    auto weak = c.lookup(pc, true, true);
    assert(weak.disagrees && !weak.strongDirection);
    auto u = c.train(weak, false); // makes direction strongly N
    assert(u.directionUpdated && !u.chooserUpdated);
    auto firstDisagree = c.lookup(pc, true, true);
    assert(firstDisagree.directionCount == 0);
    assert(firstDisagree.chooserCount == 1);
    assert(!firstDisagree.wouldOverride);
    u = c.train(firstDisagree, false); // compare: C3 correct, G5 wrong
    assert(u.chooserUpdated);
    assert(c.lookup(pc, true, true).chooserCount == 2);
    assert(!c.lookup(pc, true, true).wouldOverride);
    u = c.train(c.lookup(pc, true, true), false); // chooser 3
    auto accepted = c.lookup(pc, true, true);
    assert(accepted.chooserCount == 3);
    assert(accepted.wouldOverride && !accepted.c3Taken);
    // When G5 gets the same outcome correct, no override is needed.
    const auto agrees = c.lookup(pc, false, true);
    assert(!agrees.disagrees && !agrees.wouldOverride);
    assert(!c.train(agrees, false).chooserUpdated);

    // G5 learns or the environment changes: C3 does not get a
    // permanently guaranteed override. Incorrect C3 erodes confidence.
    const auto earlier = accepted; // saved prediction cannot change.
    u = c.train(accepted, true);
    assert(u.chooserUpdated);
    assert(c.lookup(pc, true, true).chooserCount == 2);
    assert(!c.lookup(pc, true, true).wouldOverride);
    assert(earlier.wouldOverride);
}

static void
testSelectorLearnsEvenWhenNotChosen()
{
    LittleC3PcChooser c({64, 1, 10, 2, 3});
    constexpr uint64_t pc = 0x700;
    c.train(c.lookup(pc, true, true), false);
    c.train(c.lookup(pc, true, true), false);
    auto snapshot = c.lookup(pc, true, true);
    assert(snapshot.chooserCount == 1 && !snapshot.wouldOverride);
    auto u = c.train(snapshot, false);
    assert(u.chooserUpdated);
    assert(c.lookup(pc, true, true).chooserCount == 2);
}

static void
testColdBiasLearnsTakenAndNotTaken()
{
    LittleC3PcChooser c({64, 1, 10, 2, 3});
    constexpr uint64_t t = 0x208, n = 0x210;
    c.train(c.lookup(t, false, true), true);
    c.train(c.lookup(n, true, true), false);
    const auto a = c.lookup(t, false, true);
    const auto b = c.lookup(n, true, true);
    assert(a.tagHit && a.c3Taken && a.directionCount == 2);
    assert(b.tagHit && !b.c3Taken && b.directionCount == 1);
    assert(!a.wouldOverride && !b.wouldOverride);
}

static void
testGateDoesNotReadOrTrain()
{
    LittleC3PcChooser c({64, 1, 10, 2, 3});
    auto a = c.lookup(0x200, true, false);
    assert(!a.eligible && !a.tagHit && !a.wouldOverride);
    auto u = c.train(a, false);
    assert(!u.rowWrite && !u.allocated);
    assert(!c.lookup(0x200, true, true).tagHit);
}

static void
testAliasingAndStaleSnapshot()
{
    LittleC3PcChooser c({64, 1, 10, 2, 3});
    constexpr uint64_t a = 0x200, b = a + 128;
    const auto old = c.lookup(a, true, true);
    const auto coll = c.lookup(b, true, true);
    assert(old.index == coll.index && old.tag != coll.tag);
    c.train(old, false); // installs a (with protection 0)
    auto u = c.train(coll, true); // installs b, evicts a
    assert(u.allocated && u.evicted);
    assert(!c.lookup(a, true, true).tagHit);
    assert(c.lookup(b, true, true).tagHit);
    // Committing a branch that had seen a different generation is not
    // allowed to train a mismatching tag as though it were its own.
    u = c.train(c.lookup(a, true, true), false); // new allocation
    assert(u.evicted && u.allocated);
    // Make a strong C3 N & chooser 3 to grow collision protection.
    for (int i = 0; i < 6; ++i) c.train(c.lookup(a, true, true), false);
    const auto stale = c.lookup(a, true, true);
    assert(stale.tagHit);
    const auto blocked = c.train(c.lookup(b, true, true), true);
    assert(blocked.collisionBlocked && blocked.rowWrite);
    assert(!blocked.directionUpdated);
    assert(!c.lookup(b, true, true).tagHit);
    // A snapshot from a different PC cannot use a's direction.
    assert(!c.lookup(b, true, true).wouldOverride);
}

static void
testStaleTagCannotUpdateEvictedChooser()
{
    LittleC3PcChooser c({64, 1, 10, 2, 3});
    constexpr uint64_t a = 0x200, b = a + 128;
    c.train(c.lookup(a, true, true), false);
    const auto savedA = c.lookup(a, true, true);
    assert(savedA.tagHit);
    const auto installB = c.train(c.lookup(b, true, true), true);
    assert(installB.allocated && installB.evicted);
    // An already in-flight prediction for A now sees B's tag in the row.
    // It must NOT update B's chooser using a saved A prediction.
    const auto u = c.train(savedA, false);
    assert(u.stalePrediction);
    assert(!u.chooserUpdated);
    assert(u.allocated && u.evicted); // replaces B, whose protection was 0
    const auto nextA = c.lookup(a, true, true);
    assert(nextA.tagHit && nextA.chooserCount == 1);
}

static void
testSaturationAndConfiguration()
{
    LittleC3PcChooser c({256, 1, 10, 2, 3});
    assert(c.logicalBits() == 4352);
    const auto p = c.lookup(0x300, true, true);
    const auto q = c.lookup(0x302, true, true);
    assert(p.index != q.index); // RVC PC shift1.
    bool caught = false;
    try {
        LittleC3PcChooser bad({65, 1, 10, 2, 3});
        (void)bad;
    } catch (const std::invalid_argument&) { caught = true; }
    assert(caught);
    caught = false;
    try {
        LittleC3PcChooser bad({128, 1, 10, 2, 1});
        (void)bad;
    } catch (const std::invalid_argument&) { caught = true; }
    assert(caught);
}

int
main()
{
    testNoColdOrSpuriousG5Inversion();
    testChooserLearnsComparativeAccuracyAndForgets();
    testSelectorLearnsEvenWhenNotChosen();
    testColdBiasLearnsTakenAndNotTaken();
    testGateDoesNotReadOrTrain();
    testAliasingAndStaleSnapshot();
    testStaleTagCannotUpdateEvictedChooser();
    testSaturationAndConfiguration();
}
