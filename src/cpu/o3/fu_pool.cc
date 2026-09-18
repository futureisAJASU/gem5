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

#include "cpu/o3/fu_pool.hh"
#include "sim/core.hh"

#include <sstream>

#include "cpu/func_unit.hh"

namespace gem5
{

namespace o3
{

////////////////////////////////////////////////////////////////////////////
//
//  A pool of function units
//

inline void
FUPool::FUIdxQueue::addFU(int fu_idx)
{
    funcUnitsIdx.push_back(fu_idx);
    ++size;
}

inline int
FUPool::FUIdxQueue::getFU()
{
    int retval = funcUnitsIdx[idx++];

    if (idx == size)
        idx = 0;

    return retval;
}

FUPool::~FUPool()
{
    for (FuncUnit* fu : funcUnits) {
        delete fu;
    }
}


// Constructor
FUPool::FUPool(const Params &p)
    : SimObject(p),
      lastFreeProcessTick(0),
      hasProcessedFreeTick(false),
      pairArbEpoch(0),
      pairRrArb(p.pairRrArb),
      ADD_STAT(pairRequesterGrants, statistics::units::Count::get(),
          "Successful pair-shared FU grants by requester"),
      ADD_STAT(pairContendedRequesterGrants, statistics::units::Count::get(),
          "Successful pair-shared FU grants while both requesters were pending"),
      ADD_STAT(pairContendedGrants, statistics::units::Count::get(),
          "Successful pair-shared FU grants under two-requester contention"),
      reactivePowerGating(p.reactivePowerGating),
      predictiveWakeEnabled(p.predictiveWakeEnabled),
      rawPredictiveWakeEnabled(p.rawPredictiveWakeEnabled),
      powerIdleThreshold(p.powerIdleThreshold),
      powerWakeLatency(p.powerWakeLatency),
      ADD_STAT(allocationStateSamples, statistics::units::Cycle::get(),
          "Global-tick samples of FU allocation state"),
      ADD_STAT(allocatedUnitSum, statistics::units::Count::get(),
          "Sum of allocated FU units across allocation-state samples"),
      ADD_STAT(anyAllocatedSamples, statistics::units::Cycle::get(),
          "Allocation-state samples with at least one allocated FU"),
      ADD_STAT(allIdleSamples, statistics::units::Cycle::get(),
          "Allocation-state samples with no allocated FU"),
      ADD_STAT(perUnitAllocatedSamples, statistics::units::Cycle::get(),
          "Allocation-state samples where each physical FU was allocated"),
      currentIdleRunLength(0),
      ADD_STAT(completedIdleRuns, statistics::units::Count::get(),
          "Completed consecutive allocation-idle runs"),
      ADD_STAT(idleRuns1To3, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 1-3 samples"),
      ADD_STAT(idleRuns4To7, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 4-7 samples"),
      ADD_STAT(idleRuns8To15, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 8-15 samples"),
      ADD_STAT(idleRuns16To31, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 16-31 samples"),
      ADD_STAT(idleRuns32To63, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 32-63 samples"),
      ADD_STAT(idleRuns64To127, statistics::units::Count::get(),
          "Completed allocation-idle runs of length 64-127 samples"),
      ADD_STAT(idleRuns128Plus, statistics::units::Count::get(),
          "Completed allocation-idle runs of length at least 128 samples"),
      ADD_STAT(idleBeyond8Samples, statistics::units::Cycle::get(),
          "Allocation-idle samples remaining after an 8-sample threshold"),
      ADD_STAT(idleBeyond16Samples, statistics::units::Cycle::get(),
          "Allocation-idle samples remaining after a 16-sample threshold"),
      ADD_STAT(idleBeyond32Samples, statistics::units::Cycle::get(),
          "Allocation-idle samples remaining after a 32-sample threshold"),
      ADD_STAT(idleBeyond64Samples, statistics::units::Cycle::get(),
          "Allocation-idle samples remaining after a 64-sample threshold"),
      ADD_STAT(completedIdleSamples, statistics::units::Cycle::get(),
          "Allocation-idle samples belonging to completed idle runs"),
      ADD_STAT(completedIdleBeyond8Samples, statistics::units::Cycle::get(),
          "Completed-run idle samples remaining after an 8-sample threshold"),
      ADD_STAT(completedIdleBeyond16Samples, statistics::units::Cycle::get(),
          "Completed-run idle samples remaining after a 16-sample threshold"),
      ADD_STAT(completedIdleBeyond32Samples, statistics::units::Cycle::get(),
          "Completed-run idle samples remaining after a 32-sample threshold"),
      ADD_STAT(completedIdleBeyond64Samples, statistics::units::Cycle::get(),
          "Completed-run idle samples remaining after a 64-sample threshold"),
      ADD_STAT(reactiveAwakeSamples, statistics::units::Cycle::get(),
          "Pair-shared FU-domain samples entering the tick awake"),
      ADD_STAT(reactiveSleepSamples, statistics::units::Cycle::get(),
          "Pair-shared FU-domain samples entering the tick asleep"),
      ADD_STAT(reactiveWakingSamples, statistics::units::Cycle::get(),
          "Pair-shared FU-domain samples entering the tick waking"),
      ADD_STAT(reactiveSleepTransitions, statistics::units::Count::get(),
          "Reactive transitions from awake to sleep"),
      ADD_STAT(reactiveWakeTransitions, statistics::units::Count::get(),
          "Demand-triggered transitions out of sleep"),
      ADD_STAT(reactivePowerBlockedRequests, statistics::units::Count::get(),
          "getUnit requests blocked because the FU domain was sleeping or waking"),
      ADD_STAT(decodeWakeHints, statistics::units::Count::get(),
          "Accepted Decode-stage predictive wake hints"),
      ADD_STAT(decodeWakeTransitions, statistics::units::Count::get(),
          "Decode-stage predictive transitions out of sleep"),
      ADD_STAT(decodeWakeAlreadyAwake, statistics::units::Count::get(),
          "Decode-stage wake hints received while the FU domain was awake"),
      ADD_STAT(decodeWakeAlreadyWaking, statistics::units::Count::get(),
          "Decode-stage wake hints received while the FU domain was already waking"),
      ADD_STAT(decodeWakeDemandMatched, statistics::units::Count::get(),
          "Predictive wake events followed by FU demand before expiry"),
      ADD_STAT(decodeWakeExpired, statistics::units::Count::get(),
          "Predictive wake events returning to sleep before FU demand"),
      ADD_STAT(decodeWakeDemandWhileWaking, statistics::units::Count::get(),
          "Matched predictive events first demanded while waking"),
      ADD_STAT(decodeWakeDemandWhileAwake, statistics::units::Count::get(),
          "Matched predictive events first demanded after becoming awake"),
      ADD_STAT(rawWakeHints, statistics::units::Count::get(),
          "Accepted raw-predecode predictive wake hints"),
      ADD_STAT(rawWakeTransitions, statistics::units::Count::get(),
          "Raw-predecode predictive transitions out of sleep"),
      ADD_STAT(rawWakeAlreadyAwake, statistics::units::Count::get(),
          "Raw-predecode wake hints received while the FU domain was awake"),
      ADD_STAT(rawWakeAlreadyWaking, statistics::units::Count::get(),
          "Raw-predecode wake hints received while the FU domain was waking"),
      ADD_STAT(rawWakeDemandMatched, statistics::units::Count::get(),
          "Raw-predecode wake events followed by FU demand before expiry"),
      ADD_STAT(rawWakeExpired, statistics::units::Count::get(),
          "Raw-predecode wake events returning to sleep before FU demand"),
      ADD_STAT(rawWakeDemandWhileWaking, statistics::units::Count::get(),
          "Matched raw wake events first demanded while waking"),
      ADD_STAT(rawWakeDemandWhileAwake, statistics::units::Count::get(),
          "Matched raw wake events first demanded after becoming awake")
{
    assert(!reactivePowerGating || pairRrArb);
    assert(!reactivePowerGating || powerIdleThreshold > 0);
    assert(!predictiveWakeEnabled || reactivePowerGating);
    assert(!predictiveWakeEnabled || pairRrArb);
    assert(!rawPredictiveWakeEnabled || reactivePowerGating);
    assert(!rawPredictiveWakeEnabled || pairRrArb);

    numFU = 0;

    funcUnits.clear();

    maxOpLatencies.fill(Cycles(0));
    pipelined.fill(true);
    pairRrDomainByCapability.fill(-1);

    //
    //  Iterate through the list of FUDescData structures
    //
    for (FUDesc *i : p.FUList) {
        //
        //  Don't bother with this if we're not going to create any FU's
        //
        if (i->number) {
            int pair_rr_domain = -1;

            if (pairRrArb) {
                pair_rr_domain =
                    static_cast<int>(pairRrDomains.size());
                pairRrDomains.emplace_back();

                PairRrDomainState &state =
                    pairRrDomains[pair_rr_domain];

                state.firstFuIdx = numFU;
                state.fuCount = i->number;
            }

            //
            //  Create the FuncUnit object from this structure
            //   - add the capabilities listed in the FU's operation
            //     description
            //
            //  We create the first unit, then duplicate it as needed
            //
            FuncUnit *fu = new FuncUnit;

            for (OpDesc *j : i->opDescList) {
                if (pairRrArb) {
                    const int old_domain =
                        pairRrDomainByCapability[j->opClass];

                    assert(
                        old_domain == -1 ||
                        old_domain == pair_rr_domain);

                    pairRrDomainByCapability[j->opClass] =
                        pair_rr_domain;
                }

                // indicate that this pool has this capability
                capabilityList.set(j->opClass);

                // Add each of the FU's that will have this capability to the
                // appropriate queue.
                for (int k = 0; k < i->number; ++k)
                    fuPerCapList[j->opClass].addFU(numFU + k);

                // indicate that this FU has the capability
                fu->addCapability(j->opClass, j->opLat, j->pipelined);

                if (j->opLat > maxOpLatencies[j->opClass])
                    maxOpLatencies[j->opClass] = j->opLat;

                if (!j->pipelined)
                    pipelined[j->opClass] = false;
            }

            /*
             * For a pair-shared domain consisting of exactly two
             * fully non-pipelined physical units, grant-count RR is
             * the wrong fairness unit when op latencies differ.
             *
             * Example:
             *   FloatDiv  = 12 cycles
             *   FloatSqrt = 24 cycles
             *
             * Assign one physical home lane to each requester.
             * A requester may still steal the peer lane while the
             * peer has no pending demand.
             *
             * The physical indices for one FUDesc are contiguous:
             *   [numFU, numFU + i->number)
             */
            if (pairRrArb && i->number == 2) {
                bool fully_non_pipelined =
                    !i->opDescList.empty();

                for (OpDesc *j : i->opDescList) {
                    if (j->pipelined) {
                        fully_non_pipelined = false;
                        break;
                    }
                }

                if (fully_non_pipelined) {
                    assert(pair_rr_domain >= 0);

                    PairRrDomainState &state =
                        pairRrDomains[pair_rr_domain];

                    state.homeLaneArb = true;
                    state.homeFuIdx = {
                        numFU,
                        numFU + 1,
                    };
                }
            }

            numFU++;

            //  Add the appropriate number of copies of this FU to the list
            fu->name = i->name() + "(0)";
            funcUnits.push_back(fu);

            for (int c = 1; c < i->number; ++c) {
                std::ostringstream s;
                numFU++;
                FuncUnit *fu2 = new FuncUnit(*fu);

                s << i->name() << "(" << c << ")";
                fu2->name = s.str();
                funcUnits.push_back(fu2);
            }
        }
    }

    unitBusy.resize(numFU);

    for (int i = 0; i < numFU; i++) {
        unitBusy[i] = false;
    }

    perUnitAllocatedSamples
        .init(numFU)
        .flags(statistics::total);

    for (int i = 0; i < numFU; ++i) {
        perUnitAllocatedSamples.subname(i, funcUnits[i]->name);
    }

    pairRequesterGrants
        .init(2)
        .flags(statistics::total);
    pairRequesterGrants.subname(0, "requester0");
    pairRequesterGrants.subname(1, "requester1");

    pairContendedRequesterGrants
        .init(2)
        .flags(statistics::total);
    pairContendedRequesterGrants.subname(0, "requester0");
    pairContendedRequesterGrants.subname(1, "requester1");
}

bool
FUPool::isCapable(OpClass capability)
{
    //  If this pool doesn't have the specified capability,
    //  return this information to the caller
    return capabilityList[capability];
}

void
FUPool::requestPredictiveWake(OpClass capability)
{
    /*
     * PM-B1 Decode-stage predictive wake.
     *
     * It changes only the reactive power-control state. It does not
     * create FU demand, allocate a unit, or touch RR/home-lane state.
     */
    if (!predictiveWakeEnabled)
        return;

    assert(reactivePowerGating);
    assert(pairRrArb);

    if (!capabilityList[capability])
        return;

    const int domain = pairRrDomainByCapability[capability];

    assert(domain >= 0);
    assert(domain < static_cast<int>(pairRrDomains.size()));

    PairRrDomainState &state = pairRrDomains[domain];

    decodeWakeHints++;

    switch (state.powerState) {
      case ReactivePowerState::Awake:
        decodeWakeAlreadyAwake++;
        return;

      case ReactivePowerState::Waking:
        /*
         * Idempotent: repeated/later hints must never restart wake
         * latency or steal ownership of an outstanding event.
         */
        decodeWakeAlreadyWaking++;
        return;

      case ReactivePowerState::Sleep:
        decodeWakeTransitions++;

        assert(!state.predictiveWakeOutstanding);

        state.predictiveWakeOutstanding = true;
        state.predictiveWakeFromRaw = false;
        state.powerIdleCounter = 0;

        if (powerWakeLatency == 0) {
            state.powerState = ReactivePowerState::Awake;
            state.wakeRemaining = 0;
        } else {
            state.powerState = ReactivePowerState::Waking;
            state.wakeRemaining = powerWakeLatency;
        }

        return;
    }

    panic("Unknown reactive FU power state");
}

void
FUPool::requestRawPredictiveWake(OpClass capability)
{
    /*
     * PM-B2 raw-predecode predictive wake.
     *
     * This request is intentionally source-distinct from PM-B1.
     * The source that actually performs the Sleep -> wake transition
     * owns the outstanding event until demand or expiry.
     */
    if (!rawPredictiveWakeEnabled)
        return;

    assert(reactivePowerGating);
    assert(pairRrArb);

    if (!capabilityList[capability])
        return;

    const int domain = pairRrDomainByCapability[capability];

    assert(domain >= 0);
    assert(domain < static_cast<int>(pairRrDomains.size()));

    PairRrDomainState &state = pairRrDomains[domain];

    rawWakeHints++;

    switch (state.powerState) {
      case ReactivePowerState::Awake:
        rawWakeAlreadyAwake++;
        return;

      case ReactivePowerState::Waking:
        rawWakeAlreadyWaking++;
        return;

      case ReactivePowerState::Sleep:
        rawWakeTransitions++;

        assert(!state.predictiveWakeOutstanding);

        state.predictiveWakeOutstanding = true;
        state.predictiveWakeFromRaw = true;
        state.powerIdleCounter = 0;

        if (powerWakeLatency == 0) {
            state.powerState = ReactivePowerState::Awake;
            state.wakeRemaining = 0;
        } else {
            state.powerState = ReactivePowerState::Waking;
            state.wakeRemaining = powerWakeLatency;
        }

        return;
    }

    panic("Unknown reactive FU power state");
}

int
FUPool::getUnit(OpClass capability, int requester_id)
{
    // If this pool doesn't have the specified capability,
    // return this information to the caller.
    if (!capabilityList[capability])
        return NoCapableFU;

    PairRrDomainState *rr_state = nullptr;

    if (pairRrArb) {
        /*
         * Shared pools use an IQ-provided pair-local requester
         * ID, not gem5's globally unique cpuId().
         */
        assert(requester_id == 0 || requester_id == 1);

        const int domain =
            pairRrDomainByCapability[capability];

        assert(domain >= 0);
        assert(
            domain <
            static_cast<int>(pairRrDomains.size()));

        rr_state = &pairRrDomains[domain];

        /*
         * Preserve pending demand even when every physical unit
         * in this domain is currently busy.
         */
        rr_state->requestedSinceGrant[requester_id] = true;

        /*
         * Pending and activity are intentionally separate.
         *
         * A successful grant may clear pending demand while the
         * requester is still in the middle of a sustained burst.
         * Remember that this requester touched the domain during
         * the current arbitration epoch.
         */
        rr_state->lastRequestEpoch[requester_id] =
            pairArbEpoch;

        rr_state->hasRequestEpoch[requester_id] =
            true;
    }

    /*
     * Reactive power wake is intentionally handled after pair-demand
     * bookkeeping but before physical FU arbitration.
     *
     * This preserves pending demand while reusing the existing
     * NoFreeFU scheduling/stall machinery.
     */
    if (reactivePowerGating) {
        assert(pairRrArb);
        assert(rr_state);

        if ((predictiveWakeEnabled || rawPredictiveWakeEnabled) &&
            rr_state->predictiveWakeOutstanding) {

            const bool from_raw =
                rr_state->predictiveWakeFromRaw;

            if (from_raw) {
                assert(rawPredictiveWakeEnabled);
                rawWakeDemandMatched++;
            } else {
                assert(predictiveWakeEnabled);
                decodeWakeDemandMatched++;
            }

            if (rr_state->powerState == ReactivePowerState::Waking) {
                if (from_raw)
                    rawWakeDemandWhileWaking++;
                else
                    decodeWakeDemandWhileWaking++;
            } else if (
                rr_state->powerState == ReactivePowerState::Awake) {

                if (from_raw)
                    rawWakeDemandWhileAwake++;
                else
                    decodeWakeDemandWhileAwake++;
            } else {
                panic("Predictive wake outstanding while domain is asleep");
            }

            rr_state->predictiveWakeOutstanding = false;
            rr_state->predictiveWakeFromRaw = false;
        }

        if (rr_state->powerState == ReactivePowerState::Sleep) {
            reactiveWakeTransitions++;
            rr_state->powerIdleCounter = 0;

            if (powerWakeLatency == 0) {
                rr_state->powerState = ReactivePowerState::Awake;
                rr_state->wakeRemaining = 0;
            } else {
                rr_state->powerState = ReactivePowerState::Waking;
                rr_state->wakeRemaining = powerWakeLatency;
                reactivePowerBlockedRequests++;
                return NoFreeFU;
            }
        } else if (
            rr_state->powerState == ReactivePowerState::Waking) {
            reactivePowerBlockedRequests++;
            return NoFreeFU;
        }
    }

    /*
     * Home-lane arbitration for a two-unit fully non-pipelined
     * pair-shared domain.
     *
     * Rules:
     *
     *  1. Prefer the requester's physical home lane.
     *  2. If the home lane is busy, the peer lane may be stolen
     *     only when the peer has no pending demand.
     *  3. A pending peer request remains remembered until that
     *     requester receives a grant.
     *  4. Already-running stolen work is never preempted.
     *
     * This intentionally allows a bounded first-arrival delay:
     * if both lanes were stolen while a peer was idle, a newly
     * arriving peer must wait for one in-flight non-pipelined op
     * to complete.  After that admission event, sustained
     * contention converges to one physical lane per requester.
     */
    if (
        pairRrArb &&
        rr_state &&
        rr_state->homeLaneArb) {

        const int peer_id =
            1 - requester_id;

        const int home_fu =
            rr_state->homeFuIdx[requester_id];

        const int peer_fu =
            rr_state->homeFuIdx[peer_id];

        assert(home_fu >= 0);
        assert(peer_fu >= 0);

        assert(home_fu < numFU);
        assert(peer_fu < numFU);

        int chosen_fu = NoFreeFU;
        const Tick now = curTick();

        /*
         * Protect an owner which requested this domain either in
         * the current epoch or in the immediately preceding one.
         *
         * This one-epoch hysteresis removes the grant-count hole:
         *
         *   owner receives grant
         *     -> pending bit clears
         *     -> peer must NOT immediately interpret that as idle
         *
         * A truly idle owner becomes stealable after one epoch
         * without any request.
         */
        const bool peer_recently_active =
            rr_state->hasRequestEpoch[peer_id] &&
            (
                rr_state->lastRequestEpoch[peer_id] ==
                    pairArbEpoch ||
                (
                    pairArbEpoch > 0 &&
                    rr_state->lastRequestEpoch[peer_id] ==
                        pairArbEpoch - 1
                )
            );

        if (!unitBusy[home_fu]) {
            /*
             * The owner always gets its own free physical lane.
             */
            chosen_fu = home_fu;
        } else if (!unitBusy[peer_fu]) {
            if (peer_recently_active) {
                /*
                 * The peer is still an active owner even if its
                 * instantaneous pending bit was cleared by a
                 * recent successful grant.
                 *
                 * Do not steal its physical home lane.
                 */
                return NoFreeFU;
            } else if (!rr_state->requestedSinceGrant[peer_id]) {
                /*
                 * Work-conserving steal:
                 *
                 *   no pending peer demand
                 *   AND
                 *   no recent peer activity
                 */
                chosen_fu = peer_fu;
            } else if (!rr_state->reservationActive) {
                /*
                 * Give the peer one free-lane opportunity.
                 *
                 * This also prevents IEW call ordering inside
                 * one global tick from letting the first
                 * requester steal a lane already demanded by
                 * the second requester.
                 */
                rr_state->reservationActive = true;
                rr_state->reservationTick = now;
                return NoFreeFU;
            } else if (rr_state->reservationTick == now) {
                /*
                 * Keep the reservation for the remainder of
                 * this global tick.
                 */
                return NoFreeFU;
            } else {
                /*
                 * The peer did not consume the reserved free
                 * opportunity.
                 *
                 * Its remembered request may have disappeared
                 * due to squash or other speculative recovery.
                 * Do not let a stale bit permanently disable
                 * work-conserving stealing.
                 */
                rr_state->requestedSinceGrant[peer_id] = false;
                rr_state->reservationActive = false;
                chosen_fu = peer_fu;
            }
        }

        if (chosen_fu == NoFreeFU)
            return NoFreeFU;

        /*
         * Only this requester's pending bit is consumed.
         *
         * Unlike grant-count RR, do NOT clear the peer bit:
         * that bit protects the peer's home lane until the peer
         * itself receives service.
         */
        const bool both_pending =
            rr_state->requestedSinceGrant[0] &&
            rr_state->requestedSinceGrant[1];

        pairRequesterGrants[requester_id]++;

        if (both_pending) {
            pairContendedRequesterGrants[requester_id]++;
            pairContendedGrants++;
        }

        rr_state->requestedSinceGrant[requester_id] =
            false;

        rr_state->reservationActive = false;

        unitBusy[chosen_fu] = true;

        return chosen_fu;
    }

    int fu_idx = fuPerCapList[capability].getFU();
    int start_idx = fu_idx;

    // Iterate through the circular queue if needed, stopping if we've reached
    // the first element again.
    while (unitBusy[fu_idx]) {
        fu_idx = fuPerCapList[capability].getFU();
        if (fu_idx == start_idx) {
            // No FU available.
            return NoFreeFU;
        }
    }

    assert(fu_idx < numFU);

    if (pairRrArb) {
        assert(rr_state);

        const Tick now = curTick();

        if (
            requester_id != rr_state->preferredRequester &&
            rr_state->requestedSinceGrant[
                rr_state->preferredRequester]) {

            /*
             * Reserve the free opportunity only inside this
             * physical FUDesc domain.
             */
            if (!rr_state->reservationActive) {
                rr_state->reservationActive = true;
                rr_state->reservationTick = now;
                return NoFreeFU;
            }

            if (rr_state->reservationTick == now) {
                return NoFreeFU;
            }
        }

        /*
         * A real grant rotates priority only inside this
         * physical execution domain.
         */
        const bool both_pending =
            rr_state->requestedSinceGrant[0] &&
            rr_state->requestedSinceGrant[1];

        pairRequesterGrants[requester_id]++;

        if (both_pending) {
            pairContendedRequesterGrants[requester_id]++;
            pairContendedGrants++;
        }

        rr_state->preferredRequester =
            1 - requester_id;

        rr_state->requestedSinceGrant =
            {false, false};

        rr_state->reservationActive = false;
    }

    unitBusy[fu_idx] = true;

    return fu_idx;
}

void
FUPool::freeUnitNextCycle(int fu_idx)
{
    assert(unitBusy[fu_idx]);
    unitsToBeFreed.push_back(fu_idx);
}

void
FUPool::processFreeUnits()
{
    /*
     * A shared FUPool can be visited by multiple IEW stages during the
     * same global tick.  Free at most once per tick so requests added
     * after the first visit retain the documented next-cycle semantics.
     */
    const Tick now = curTick();

    if (hasProcessedFreeTick && lastFreeProcessTick == now) {
        return;
    }

    lastFreeProcessTick = now;
    hasProcessedFreeTick = true;

    /*
     * The same shared pool may be visited by two IEW stages, but
     * the guard above ensures this epoch advances exactly once
     * per global tick.
     */
    if (pairRrArb)
        ++pairArbEpoch;

    /*
     * Reactive power-state clock.
     *
     * State residency is sampled at the beginning of the globally
     * deduplicated FU-pool control tick.  A waking countdown which
     * reaches zero here makes the domain available to getUnit() later
     * in the same IEW tick.
     *
     * Sleep entry occurs after T consecutive idle samples have been
     * observed.  The next idle sample is therefore counted in Sleep,
     * matching the A2b idleBeyondT definition.
     */
    if (reactivePowerGating) {
        assert(pairRrArb);

        for (auto &state : pairRrDomains) {
            switch (state.powerState) {
              case ReactivePowerState::Awake:
                reactiveAwakeSamples++;
                break;

              case ReactivePowerState::Sleep:
                reactiveSleepSamples++;
                break;

              case ReactivePowerState::Waking:
                reactiveWakingSamples++;
                break;
            }

            if (state.powerState == ReactivePowerState::Waking) {
                assert(state.wakeRemaining > 0);

                --state.wakeRemaining;

                if (state.wakeRemaining == 0) {
                    state.powerState = ReactivePowerState::Awake;
                    state.powerIdleCounter = 0;
                }
            }

            if (state.powerState == ReactivePowerState::Awake) {
                assert(state.firstFuIdx >= 0);
                assert(state.fuCount > 0);
                assert(state.firstFuIdx + state.fuCount <= numFU);

                unsigned domain_allocated = 0;

                for (
                    int fu_idx = state.firstFuIdx;
                    fu_idx < state.firstFuIdx + state.fuCount;
                    ++fu_idx) {
                    if (unitBusy[fu_idx])
                        ++domain_allocated;
                }

                if (domain_allocated == 0) {
                    ++state.powerIdleCounter;

                    if (state.powerIdleCounter >= powerIdleThreshold) {
                        if ((predictiveWakeEnabled ||
                             rawPredictiveWakeEnabled) &&
                            state.predictiveWakeOutstanding) {

                            if (state.predictiveWakeFromRaw) {
                                assert(rawPredictiveWakeEnabled);
                                rawWakeExpired++;
                            } else {
                                assert(predictiveWakeEnabled);
                                decodeWakeExpired++;
                            }

                            state.predictiveWakeOutstanding = false;
                            state.predictiveWakeFromRaw = false;
                        }

                        state.powerState = ReactivePowerState::Sleep;
                        state.powerIdleCounter = 0;
                        reactiveSleepTransitions++;
                    }
                } else {
                    state.powerIdleCounter = 0;
                }
            } else {
                state.powerIdleCounter = 0;
            }
        }
    }

    /*
     * Observation only: sample the allocation state before releasing
     * units scheduled to become free this cycle.  processFreeUnits()
     * is globally tick-guarded, so shared pools are sampled at most
     * once per global simulation tick.
     */
    if (numFU > 0) {
        unsigned allocated = 0;

        for (int i = 0; i < numFU; ++i) {
            if (unitBusy[i]) {
                ++allocated;
                perUnitAllocatedSamples[i]++;
            }
        }

        allocationStateSamples++;
        allocatedUnitSum += allocated;

        if (allocated == 0) {
            allIdleSamples++;
            ++currentIdleRunLength;

            if (currentIdleRunLength > 8)
                idleBeyond8Samples++;
            if (currentIdleRunLength > 16)
                idleBeyond16Samples++;
            if (currentIdleRunLength > 32)
                idleBeyond32Samples++;
            if (currentIdleRunLength > 64)
                idleBeyond64Samples++;
        } else {
            anyAllocatedSamples++;

            if (currentIdleRunLength != 0) {
                const uint64_t idle_run = currentIdleRunLength;

                completedIdleRuns++;
                completedIdleSamples += idle_run;

                if (idle_run > 8)
                    completedIdleBeyond8Samples += idle_run - 8;
                if (idle_run > 16)
                    completedIdleBeyond16Samples += idle_run - 16;
                if (idle_run > 32)
                    completedIdleBeyond32Samples += idle_run - 32;
                if (idle_run > 64)
                    completedIdleBeyond64Samples += idle_run - 64;

                if (currentIdleRunLength <= 3)
                    idleRuns1To3++;
                else if (currentIdleRunLength <= 7)
                    idleRuns4To7++;
                else if (currentIdleRunLength <= 15)
                    idleRuns8To15++;
                else if (currentIdleRunLength <= 31)
                    idleRuns16To31++;
                else if (currentIdleRunLength <= 63)
                    idleRuns32To63++;
                else if (currentIdleRunLength <= 127)
                    idleRuns64To127++;
                else
                    idleRuns128Plus++;

                currentIdleRunLength = 0;
            }
        }
    }

    while (!unitsToBeFreed.empty()) {
        int fu_idx = unitsToBeFreed.back();
        unitsToBeFreed.pop_back();

        assert(unitBusy[fu_idx]);

        unitBusy[fu_idx] = false;
    }
}

void
FUPool::dump()
{
    std::cout << "Function Unit Pool (" << name() << ")\n";
    std::cout << "======================================\n";
    std::cout << "Free List:\n";

    for (int i = 0; i < numFU; ++i) {
        if (unitBusy[i]) {
            continue;
        }

        std::cout << "  [" << i << "] : ";

        std::cout << funcUnits[i]->name << " ";

        std::cout << "\n";
    }

    std::cout << "======================================\n";
    std::cout << "Busy List:\n";
    for (int i = 0; i < numFU; ++i) {
        if (!unitBusy[i]) {
            continue;
        }

        std::cout << "  [" << i << "] : ";

        std::cout << funcUnits[i]->name << " ";

        std::cout << "\n";
    }
}

bool
FUPool::isDrained() const
{
    bool is_drained = true;
    for (int i = 0; i < numFU; i++)
        is_drained = is_drained && !unitBusy[i];

    return is_drained;
}

} // namespace o3
} // namespace gem5
