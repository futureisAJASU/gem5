/*
 * Copyright (c) 2012-2013, 2025 Arm Limited
 * All rights reserved
 *
 * The license below extends only to copyright in the software and shall
 * not be construed as granting a license to any other intellectual
 * property including but not limited to intellectual property relating
 * to a hardware implementation of the functionality of the software
 * licensed hereunder.  You may use the software subject to the license
 * terms below provided that you ensure that this notice is replicated
 * unmodified and in its entirety in all distributions of the software,
 * modified or unmodified, in source code or in binary form.
 *
 * Copyright (c) 2006 The Regents of The University of Michigan
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef __CPU_O3_FU_POOL_HH__
#define __CPU_O3_FU_POOL_HH__

#include <array>
#include <bitset>
#include <cstdint>
#include <list>
#include <string>
#include <vector>

#include "base/statistics.hh"
#include "cpu/op_class.hh"
#include "params/FUPool.hh"
#include "sim/sim_object.hh"

namespace gem5
{

class FUDesc;
class FuncUnit;

namespace o3
{

/**
 * Pool of FU's, specific to the new CPU model. The old FU pool had lists of
 * free units and busy units, and whenever a FU was needed it would iterate
 * through the free units to find a FU that provided the capability. This pool
 * has lists of units specific to each of the capabilities, and whenever a FU
 * is needed, it iterates through that list to find a free unit. The previous
 * FU pool would have to be ticked each cycle to update which units became
 * free. This FU pool lets the IEW stage handle freeing units, which frees
 * them as their scheduled execution events complete. This limits units in this
 * model to either have identical issue and op latencies, or 1 cycle issue
 * latencies.
 */
class FUPool : public SimObject
{
  private:
    /** Maximum op execution latencies, per op class. */
    std::array<Cycles, Num_OpClasses> maxOpLatencies;
    /** Whether op is pipelined or not. */
    std::array<bool, Num_OpClasses> pipelined;

    /** Bitvector listing capabilities of this FU pool. */
    std::bitset<Num_OpClasses> capabilityList;

    /** Bitvector listing which FUs are busy. */
    std::vector<bool> unitBusy;

    /** List of units to be freed at the end of this cycle. */
    std::vector<int> unitsToBeFreed;

    /**
     * A FUPool may be referenced by more than one IEW stage when a
     * physical execution resource is shared across cores.
     *
     * IEW::tick() calls processFreeUnits() once per IEW.  Without a
     * global-tick guard, a second IEW referencing the same pool could
     * process units queued by the first IEW during the same global
     * cycle, turning freeUnitNextCycle() into a same-cycle release.
     *
     * Private pools are unaffected because they are naturally visited
     * only once per global cycle.
     */
    Tick lastFreeProcessTick;
    bool hasProcessedFreeTick;

    /**
     * Monotonic arbitration epoch for pair-shared pools.
     *
     * processFreeUnits() is globally guarded so this advances at
     * most once per global simulation tick even when two IEW stages
     * reference the same physical FUPool.
     *
     * Home-lane arbitration uses the epoch to distinguish:
     *
     *   pending demand
     *
     * from:
     *
     *   an owner which was recently active but happened to receive
     *   a grant and therefore temporarily cleared its pending bit.
     */
    Tick pairArbEpoch;

    /**
     * Optional two-requester arbitration for a physical FU pool shared
     * across one two-core pair.
     *
     * The request bits remember which cores attempted to acquire this
     * resource after the previous grant. This makes the arbitration
     * work-conserving when only one core is active while preserving
     * round-robin service when both cores contend.
     */
    const bool pairRrArb;


    /**
     * Optional reactive power-state model for pair-shared physical
     * FUDesc domains.
     *
     * Disabled by default so historical execution behavior is preserved.
     */
    const bool reactivePowerGating;
    const unsigned powerIdleThreshold;
    const unsigned powerWakeLatency;
    /**
     * Observation-only allocation-state statistics.
     *
     * For non-pipelined units, allocation residency is a useful
     * execution-occupancy proxy.  For pipelined units, it reflects
     * issue/allocation activity rather than full pipeline residency.
     */
    statistics::Scalar allocationStateSamples;
    statistics::Scalar allocatedUnitSum;
    statistics::Scalar anyAllocatedSamples;
    statistics::Scalar allIdleSamples;
    statistics::Vector perUnitAllocatedSamples;

    /** Current consecutive allocation-idle run length. */
    uint64_t currentIdleRunLength;

    /** Completed allocation-idle run statistics. */
    statistics::Scalar completedIdleRuns;
    statistics::Scalar idleRuns1To3;
    statistics::Scalar idleRuns4To7;
    statistics::Scalar idleRuns8To15;
    statistics::Scalar idleRuns16To31;
    statistics::Scalar idleRuns32To63;
    statistics::Scalar idleRuns64To127;
    statistics::Scalar idleRuns128Plus;

    /**
     * Idle samples remaining after an idle threshold has elapsed.
     * For example, a 100-cycle run contributes 84 samples to
     * idleBeyond16Samples.
     */
    statistics::Scalar idleBeyond8Samples;
    statistics::Scalar idleBeyond16Samples;
    statistics::Scalar idleBeyond32Samples;
    statistics::Scalar idleBeyond64Samples;

    /**
     * Exact accounting over completed idle runs only.
     *
     * These counters exclude an idle run still open when simulation
     * statistics are dumped, making them suitable for recurrent
     * sleep-threshold and wakeup-policy analysis.
     */
    statistics::Scalar completedIdleSamples;
    statistics::Scalar completedIdleBeyond8Samples;
    statistics::Scalar completedIdleBeyond16Samples;
    statistics::Scalar completedIdleBeyond32Samples;
    statistics::Scalar completedIdleBeyond64Samples;

    /**
     * Independent two-requester arbitration state for one
     * physical FUDesc domain.
     *
     * OpClasses implemented by the same FUDesc share one
     * state. Unrelated physical domains arbitrate independently.
     */
    enum class ReactivePowerState : uint8_t
    {
        Awake,
        Sleep,
        Waking,
    };

    struct PairRrDomainState
    {
        int preferredRequester = 0;
        std::array<bool, 2> requestedSinceGrant{{false, false}};
        Tick reservationTick = 0;
        bool reservationActive = false;

        /**
         * Two-unit fully non-pipelined pair-shared domains use
         * physical owner lanes instead of grant-count RR.
         *
         * Each requester owns one physical FU while both are active.
         * When the peer has no pending demand, its lane may be stolen.
         */
        bool homeLaneArb = false;
        std::array<int, 2> homeFuIdx{{-1, -1}};

        /**
         * Per-requester activity history.
         *
         * A requester which attempted to acquire this physical
         * domain in the current or immediately preceding
         * arbitration epoch is treated as active.  Its home lane
         * must not be stolen merely because a successful grant
         * temporarily cleared requestedSinceGrant.
         */
        std::array<Tick, 2> lastRequestEpoch{{0, 0}};
        std::array<bool, 2> hasRequestEpoch{{false, false}};

        /**
         * Physical FU index range belonging to this FUDesc domain.
         * FUs created from one FUDesc are contiguous.
         */
        int firstFuIdx = -1;
        int fuCount = 0;

        /**
         * Reactive power-control state.
         *
         * Deliberately independent from the A2b observation-only
         * idle-run counters.
         */
        ReactivePowerState powerState = ReactivePowerState::Awake;
        uint64_t powerIdleCounter = 0;
        uint64_t wakeRemaining = 0;
    };

    /** OpClass -> physical FUDesc arbitration domain. */
    std::array<int, Num_OpClasses> pairRrDomainByCapability;

    /** One RR state per physical FUDesc domain. */
    std::vector<PairRrDomainState> pairRrDomains;

    /**
     * Reactive power-state statistics.
     *
     * Aggregated across enabled pair-shared FUDesc domains.
     */
    statistics::Scalar reactiveAwakeSamples;
    statistics::Scalar reactiveSleepSamples;
    statistics::Scalar reactiveWakingSamples;
    statistics::Scalar reactiveSleepTransitions;
    statistics::Scalar reactiveWakeTransitions;
    statistics::Scalar reactivePowerBlockedRequests;

    /**
     * Class that implements a circular queue to hold FU indices. The hope is
     * that FUs that have been just used will be moved to the end of the queue
     * by iterating through it, thus leaving free units at the head of the
     * queue.
     */
    class FUIdxQueue
    {
      public:
        /** Constructs a circular queue of FU indices. */
        FUIdxQueue()
            : idx(0), size(0)
        { }

        /** Adds a FU to the queue. */
        inline void addFU(int fu_idx);

        /** Returns the index of the FU at the head of the queue, and changes
         *  the index to the next element.
         */
        inline int getFU();

      private:
        /** Circular queue index. */
        int idx;

        /** Size of the queue. */
        int size;

        /** Queue of FU indices. */
        std::vector<int> funcUnitsIdx;
    };

    /** Per op class queues of FUs that provide that capability. */
    FUIdxQueue fuPerCapList[Num_OpClasses];

    /** Number of FUs. */
    int numFU;

    /** Functional units. */
    std::vector<FuncUnit *> funcUnits;

  public:
    typedef FUPoolParams Params;
    /** Constructs a FU pool. */
    FUPool(const Params &p);
    ~FUPool();

    /**
     * Named constants to differentiate cases where an
     * instruction asked the FUPool for a free FU
     * but did not get one
     */

    /**
     * Instruction asked for a FU but does not actually
     * need any (e.g., NOP)
     */
    static constexpr auto NoNeedFU = -3;

    /**
     * Instruction asked for a FU but this FUPool does
     * not have a FU for this instruction op type
     */
    static constexpr auto NoCapableFU = -2;

    /**
     * Instruction asked for a FU but all FU for
     * this op type have already been allocated to
     * other instructions this cycle
     */
    static constexpr auto NoFreeFU = -1;

    /** Returns true if the FU has the required capability */
    bool isCapable(OpClass capability);

    /**
     * Gets a FU providing the requested capability. Will mark the
     * unit as busy, but leaves the freeing of the unit up to the IEW
     * stage.
     *
     * @param capability The capability requested.
     * @return Returns NoCapableFU if the FU pool does not have the
     * capability, NoFreeFU if there is no free FU, and the FU's index
     * otherwise.
     */
    int getUnit(OpClass capability, int requester_id = -1);

    /** Frees a FU at the end of this cycle. */
    void freeUnitNextCycle(int fu_idx);

    /** Frees all FUs on the list. */
    void processFreeUnits();

    /** Returns the total number of FUs. */
    int size() { return numFU; }

    /** Debugging function used to dump FU information. */
    void dump();

    /** Returns the operation execution latency of the given capability. */
    Cycles getOpLatency(OpClass capability) {
        return maxOpLatencies[capability];
    }

    /** Returns the issue latency of the given capability. */
    bool isPipelined(OpClass capability) {
        return pipelined[capability];
    }

    /** Have all the FUs drained? */
    bool isDrained() const;

    /** Takes over from another CPU's thread. */
    void takeOverFrom() {};
};

} // namespace o3
} // namespace gem5

#endif // __CPU_O3_FU_POOL_HH__
