/*
 * TAGE speculative-history rollover pointer proof.
 *
 * This helper validates simulator bookkeeping only; it never changes a
 * prediction, index, branch-history bit, or the persistent TAGE bit budget.
 * A rollover copies original history[source ...] to [base ...]. A saved
 * pointer from the previous generation thus maps to:
 *        base + (saved_pointer - source_pointer).
 * A restored branch must also pass the full raw-window/folded-history checks.
 */
#ifndef __CPU_PRED_TAGE_ROLLOVER_RESTORE_HH__
#define __CPU_PRED_TAGE_ROLLOVER_RESTORE_HH__

#include <cstdint>

namespace gem5
{
namespace branch_prediction
{

// Returns -1 for a transition not proven by a single valid rollover.
constexpr int
expectedTageRestorePointer(int savedPointer, std::uint64_t savedGeneration,
                           std::uint64_t currentGeneration, int sourcePointer,
                           int bufferSize, int maxHistory,
                           int rollbackBuffer)
{
    if (savedPointer < 0 || sourcePointer < 0 ||
        bufferSize <= maxHistory + rollbackBuffer || maxHistory <= 0 ||
        rollbackBuffer <= 0) {
        return -1;
    }
    if (savedGeneration == currentGeneration) {
        return savedPointer;
    }
    // An in-flight speculative branch cannot survive two full-buffer
    // rollovers. Do not silently normalize arbitrary generation drift.
    if (currentGeneration <= savedGeneration ||
        currentGeneration - savedGeneration != 1) {
        return -1;
    }
    const int offset = savedPointer - sourcePointer;
    // Only the copied maxHistory+rollbackBuffer window is recoverable;
    // the entire maxHistory window starting at savedPointer must fit.
    if (offset < 0 || offset > rollbackBuffer) {
        return -1;
    }
    return bufferSize - maxHistory - rollbackBuffer + offset;
}

} // namespace branch_prediction
} // namespace gem5

#endif // __CPU_PRED_TAGE_ROLLOVER_RESTORE_HH__
