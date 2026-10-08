/*
 * Little v0.52 BPU-7 C3 — PC-bias tagged residual corrector.
 *
 * First candidate only. This pure finite-state engine contains NO frontend
 * redirection and is currently integrated in diagnostic SHADOW mode.
 *
 * IMPORTANT: A tag hit alone never overrides G5; a trained, positive
 * signed residual score >= threshold is required. Training learns the
 * correctness of INVERTING the prediction-time G5 direction, not
 * the taken/not-taken direction of the branch.
 *
 * Initial C3 S0 = 128 entries × (valid1 + PC tag10 + score3 +
 * collision-protection2) = 2048 logical persistent bits.
 *
 * The two "replacement" bits in the proposed contract are implemented as
 * per-entry collision-protection (not ways in a direct-mapped array).
 * Freeze this semantic choice only after review.
 */

#ifndef __CPU_PRED_LITTLE_C3_PC_BIAS_HH__
#define __CPU_PRED_LITTLE_C3_PC_BIAS_HH__

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace gem5
{
namespace branch_prediction
{

class LittleC3PcBias
{
  public:
    struct Config
    {
        unsigned entries = 128;
        unsigned pcShift = 1;
        unsigned tagBits = 10;
        unsigned scoreBits = 3;
        unsigned protectionBits = 2;
        int overrideThreshold = 2;
    };

    struct Lookup
    {
        bool eligible = false;
        bool tagHit = false;
        bool wouldFlip = false;
        std::size_t index = 0;
        uint32_t tag = 0;
        int score = 0;
    };

    struct Update
    {
        bool trained = false;
        bool allocated = false;
        bool evicted = false;
        bool collisionBlocked = false;
    };

    explicit LittleC3PcBias(const Config& cfg)
        : config(cfg), table(cfg.entries)
    {
        if (!cfg.entries || (cfg.entries & (cfg.entries - 1))) {
            throw std::invalid_argument("C3 entries must be a power of two");
        }
        if (cfg.pcShift >= 64 || !cfg.tagBits || cfg.tagBits > 16) {
            throw std::invalid_argument("C3 invalid PC shift/tag width");
        }
        if (cfg.scoreBits < 2 || cfg.scoreBits > 8 ||
            cfg.protectionBits < 1 || cfg.protectionBits > 8) {
            throw std::invalid_argument("C3 counter width out of bounds");
        }
        if (cfg.overrideThreshold < 1 ||
            cfg.overrideThreshold > ((1 << (cfg.scoreBits - 1)) - 1)) {
            throw std::invalid_argument("C3 threshold cannot be met");
        }

        unsigned size = cfg.entries;
        while (size > 1) {
            ++indexBits;
            size >>= 1;
        }
    }

    Lookup
    lookup(uint64_t pc, bool g0Eligible) const
    {
        Lookup result;
        // G0 is deliberately only a post-TAGE-read activation gate.
        // Ineligible accesses do not touch the corrector table.
        if (!g0Eligible) {
            return result;
        }
        result.eligible = true;
        const uint64_t shiftedPc = pc >> config.pcShift;
        result.index = shiftedPc & (config.entries - 1);
        result.tag = static_cast<uint32_t>(
            (shiftedPc >> indexBits) & ((1ULL << config.tagBits) - 1));
        const Entry& row = table[result.index];
        result.tagHit = row.valid && row.tag == result.tag;
        result.score = result.tagHit ? row.score : 0;
        result.wouldFlip = result.tagHit &&
                           result.score >= config.overrideThreshold;
        return result;
    }

    Update
    train(const Lookup& saved, bool predictionTimeG5WasWrong)
    {
        Update result;
        if (!saved.eligible) {
            return result;
        }

        Entry& row = table.at(saved.index);
        const int delta = predictionTimeG5WasWrong ? 1 : -1;
        if (row.valid && row.tag == saved.tag) {
            row.score = saturateScore(static_cast<int>(row.score) + delta);
            if (predictionTimeG5WasWrong) {
                if (row.protection < maxProtection()) {
                    ++row.protection;
                }
            } else if (row.protection) {
                --row.protection;
            }
            result.trained = true;
            return result;
        }

        // Direct-mapped conflict handling. Non-zero protection delays
        // eviction, but *never* pretends that a tag miss was a tag hit.
        if (row.valid && row.protection) {
            --row.protection;
            result.collisionBlocked = true;
            return result;
        }
        result.evicted = row.valid;
        row.valid = true;
        row.tag = saved.tag;
        row.score = static_cast<int8_t>(delta);
        row.protection = predictionTimeG5WasWrong ? 1 : 0;
        result.allocated = true;
        result.trained = true;
        return result;
    }

    std::size_t
    logicalBits() const
    {
        return static_cast<std::size_t>(config.entries) *
               (1 + config.tagBits + config.scoreBits +
                config.protectionBits);
    }

    unsigned
    entryCount() const
    {
        return config.entries;
    }

  private:
    struct Entry
    {
        uint32_t tag = 0;
        int8_t score = 0;
        uint8_t protection = 0;
        bool valid = false;
    };

    const Config config;
    std::vector<Entry> table;
    unsigned indexBits = 0;

    unsigned
    maxProtection() const
    {
        return (1u << config.protectionBits) - 1u;
    }

    int8_t
    saturateScore(int value) const
    {
        const int lo = -(1 << (config.scoreBits - 1));
        const int hi = (1 << (config.scoreBits - 1)) - 1;
        if (value < lo) {
            value = lo;
        } else if (value > hi) {
            value = hi;
        }
        return static_cast<int8_t>(value);
    }
};

} // namespace branch_prediction
} // namespace gem5

#endif // __CPU_PRED_LITTLE_C3_PC_BIAS_HH__
