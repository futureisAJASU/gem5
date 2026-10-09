/*
 * Little v0.52 / BPU-7 / C3 PC_CHOOSER P1
 *
 * Independent PC-bias direction + disagreement-trained chooser.
 * A SHADOW prototype only: must not change G5 fetch or claim M1 cycles.
 * This is an alternative to, not a silent replacement for, the earlier
 * PC_RESIDUAL inversion-benefit baseline.
 *
 * Logical persistent state per entry:
 *  valid(1) + truncated PC tag(10) + direction(2) +
 *  chooser(2) + collision protection(2) = 17 bits.
 * C3 direction and G5 direction are independently formed at prediction
 * time. Chooser is trained only when saved predictions disagree.
 */
#ifndef __CPU_PRED_LITTLE_C3_PC_CHOOSER_HH__
#define __CPU_PRED_LITTLE_C3_PC_CHOOSER_HH__

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace gem5
{
namespace branch_prediction
{

class LittleC3PcChooser
{
  public:
    struct Config
    {
        unsigned entries = 128;
        unsigned pcShift = 1;
        unsigned tagBits = 10;
        unsigned protectionBits = 2;
        // 0/1 favors G5, 2/3 favors C3, but choose only at 3.
        unsigned selectC3At = 3;
    };

    struct Lookup
    {
        bool eligible = false;
        bool tagHit = false;
        bool c3Taken = false;
        bool g5Taken = false;
        bool strongDirection = false;
        bool disagrees = false;
        bool wouldOverride = false;
        std::size_t index = 0;
        uint32_t tag = 0;
        unsigned directionCount = 0;
        unsigned chooserCount = 0;
    };

    struct Update
    {
        bool rowWrite = false;
        bool directionUpdated = false;
        bool chooserUpdated = false;
        bool allocated = false;
        bool evicted = false;
        bool collisionBlocked = false;
        bool stalePrediction = false;
    };

    explicit LittleC3PcChooser(const Config &cfg)
      : config(cfg), table(cfg.entries)
    {
        if (!cfg.entries || (cfg.entries & (cfg.entries - 1)) ||
            cfg.pcShift >= 64 || cfg.tagBits == 0 || cfg.tagBits > 16 ||
            cfg.protectionBits == 0 || cfg.protectionBits > 8 ||
            cfg.selectC3At < 2 || cfg.selectC3At > 3) {
            throw std::invalid_argument("C3 chooser invalid geometry");
        }
        for (unsigned n = cfg.entries; n > 1; n >>= 1) {
            ++indexBits;
        }
        // When adding a mode that has multiple simultaneous threads,
        // separate state banks per thread or document intentional sharing.
    }

    Lookup
    lookup(uint64_t pc, bool g5Taken, bool g0Eligible) const
    {
        Lookup x;
        x.g5Taken = g5Taken;
        if (!g0Eligible) {
            return x; // No auxiliary SRAM read.
        }
        x.eligible = true;
        const uint64_t key = pc >> config.pcShift;
        x.index = static_cast<std::size_t>(key & (config.entries - 1));
        x.tag = static_cast<uint32_t>(
            (key >> indexBits) & ((1ULL << config.tagBits) - 1));
        const Entry &row = table[x.index];
        x.tagHit = row.valid && row.tag == x.tag;
        if (!x.tagHit) {
            return x; // Never use an aliased row's direction/chooser.
        }
        x.directionCount = row.direction;
        x.chooserCount = row.chooser;
        x.c3Taken = row.direction >= 2;
        x.strongDirection = row.direction == 0 || row.direction == 3;
        x.disagrees = x.c3Taken != x.g5Taken;
        x.wouldOverride =
            x.strongDirection && x.disagrees &&
            row.chooser >= config.selectC3At;
        return x;
    }

    Update
    train(const Lookup &saved, bool actualTaken)
    {
        Update u;
        if (!saved.eligible) {
            return u;
        }
        Entry &row = table.at(saved.index);
        if (row.valid && row.tag == saved.tag) {
            // The outcome updates the independent direction estimator.
            row.direction = saturate2(row.direction, actualTaken);
            u.directionUpdated = true;
            u.rowWrite = true;

            // The chooser learns *comparative* correctness from the
            // prediction-time snapshot, never recomputes predictions
            // using newer table state.
            if (saved.tagHit && saved.disagrees && saved.strongDirection) {
                const bool c3WasRight = saved.c3Taken == actualTaken;
                row.chooser = saturate2(row.chooser, c3WasRight);
                u.chooserUpdated = true;
                if (c3WasRight) {
                    if (row.protection < maxProtection()) {
                        ++row.protection;
                    }
                } else if (row.protection) {
                    --row.protection;
                }
            }
            return u;
        }

        // A tag mismatch may mean an intervening commit evicted the
        // prediction-time row. Never train an old row as if tag matched.
        u.stalePrediction = saved.tagHit;
        if (row.valid && row.protection) {
            --row.protection;
            u.collisionBlocked = true;
            u.rowWrite = true; // Age counter changed, not direction.
            return u;
        }
        u.evicted = row.valid;
        row.valid = true;
        row.tag = saved.tag;
        // Cold start with a *weak* direction favored by the first outcome,
        // and a chooser biased toward trusting G5.
        row.direction = actualTaken ? 2 : 1;
        row.chooser = 1;
        row.protection = 0;
        u.allocated = true;
        u.rowWrite = true;
        return u;
    }

    std::size_t
    logicalBits() const
    {
        return static_cast<std::size_t>(config.entries) *
            (1 + config.tagBits + 2 + 2 + config.protectionBits);
    }

  private:
    struct Entry
    {
        bool valid = false;
        uint32_t tag = 0;
        uint8_t direction = 1; // 2-bit PHT: 0/1=N, 2/3=T
        uint8_t chooser = 1;   // 2-bit PHT: low favors G5
        uint8_t protection = 0;
    };

    const Config config;
    std::vector<Entry> table;
    unsigned indexBits = 0;

    unsigned
    maxProtection() const
    {
        return (1u << config.protectionBits) - 1u;
    }

    static uint8_t
    saturate2(uint8_t v, bool increment)
    {
        if (increment) {
            return v < 3 ? static_cast<uint8_t>(v + 1) : v;
        }
        return v > 0 ? static_cast<uint8_t>(v - 1) : v;
    }
};

} // namespace branch_prediction
} // namespace gem5
#endif // __CPU_PRED_LITTLE_C3_PC_CHOOSER_HH__
