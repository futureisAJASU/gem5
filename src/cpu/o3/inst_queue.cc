/*
 * Copyright (c) 2011-2014, 2017-2020, 2025 Arm Limited
 * Copyright (c) 2013 Advanced Micro Devices, Inc.
 * All rights reserved.
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
 * Copyright (c) 2004-2006 The Regents of The University of Michigan
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

#include "cpu/o3/inst_queue.hh"

#include <algorithm>
#include <limits>
#include <vector>

#include "base/logging.hh"
#include "cpu/o3/dyn_inst.hh"
#include "cpu/o3/fu_pool.hh"
#include "cpu/o3/limits.hh"
#include "debug/IQ.hh"
#include "enums/OpClass.hh"
#include "params/BaseO3CPU.hh"
#include "params/IQUnit.hh"
#include "sim/core.hh"

// clang complains about std::set being overloaded with Packet::set if
// we open up the entire namespace std
using std::list;

namespace gem5
{

namespace o3
{

IQUnit::IQUnit(const IQUnitParams &params)
    : SimObject(params),
      iqPolicy(params.smtIQPolicy),
      numThreads(params.numThreads),
      activeThreads(nullptr),
      _enableNSkip(params.enableNSkip),
      _nSkip(params.nSkip),
      _dispatchWriteCap(params.dispatchWriteCap),
      _freeEntries(params.numEntries),
      _numEntries(params.numEntries),
      _fuPool(params.fuPool),
      _fuRequesterId(params.fuRequesterId)
{
    assert(_fuPool);
    // Figure out resource sharing policy
    if (iqPolicy == SMTQueuePolicy::Dynamic) {
        // Set Max Entries to Total IQs Capacity
        for (ThreadID tid = 0; tid < numThreads; tid++) {
            maxEntries[tid] = _numEntries;
        }

    } else if (iqPolicy == SMTQueuePolicy::Partitioned) {
        //@todo:make work if part_amt doesnt divide evenly.
        int part_amt = _numEntries / numThreads;

        // Divide ROB up evenly
        for (ThreadID tid = 0; tid < numThreads; tid++) {
            maxEntries[tid] = part_amt;
        }

        DPRINTF(IQ,
                "IQ sharing policy set to Partitioned:"
                "%i entries per thread.\n",
                part_amt);
    } else if (iqPolicy == SMTQueuePolicy::Threshold) {
        double threshold = (double)params.smtIQThreshold / 100;

        int thresholdIQ = (int)((double)threshold * _numEntries);

        // Divide up by threshold amount
        for (ThreadID tid = 0; tid < numThreads; tid++) {
            maxEntries[tid] = thresholdIQ;
        }

        DPRINTF(IQ,
                "IQ sharing policy set to Threshold:"
                "%i entries per thread.\n",
                thresholdIQ);
    }

    for (ThreadID tid = numThreads; tid < MaxThreads; tid++) {
        maxEntries[tid] = 0;
    }
}

void
IQUnit::insert(const DynInstPtr &inst)
{
    assert(_freeEntries != 0);
    _freeEntries--;

    inst->setInIQ(this);
    _orderedInsts.push_back(inst);

    count[inst->threadNumber]++;
}

void
IQUnit::remove(const DynInstPtr &inst)
{
    // Any instruction leaving the physical IQ must also leave its
    // scheduler-ready mirror.  This covers squash and normal completion.
    markNotReady(inst);

    bool found = false;

    for (auto it = _orderedInsts.begin(); it != _orderedInsts.end(); ++it) {
        if (*it == inst) {
            _orderedInsts.erase(it);
            found = true;
            break;
        }
    }

    assert(found);

    _freeEntries++;
    assert(_freeEntries <= _numEntries);

    count[inst->threadNumber]--;
}

void
IQUnit::setActiveThreads(list<ThreadID> *at_ptr)
{
    activeThreads = at_ptr;
}

void
IQUnit::resetState()
{
    _orderedInsts.clear();
    _readyInsts.clear();
    _freeEntries = _numEntries;
    for (ThreadID tid = 0; tid < numThreads; ++tid) {
        count[tid] = 0;
    }
}

void
IQUnit::resetEntries()
{
    if (iqPolicy != SMTQueuePolicy::Dynamic || numThreads > 1) {
        int active_threads = activeThreads->size();

        for (ThreadID tid : *activeThreads) {
            if (iqPolicy == SMTQueuePolicy::Partitioned) {
                maxEntries[tid] = _numEntries / active_threads;
            } else if (iqPolicy == SMTQueuePolicy::Threshold &&
                       active_threads == 1) {
                maxEntries[tid] = _numEntries;
            }
        }
    }
}

int
IQUnit::entryAmount(ThreadID num_threads)
{
    if (iqPolicy == SMTQueuePolicy::Partitioned) {
        return _numEntries / num_threads;
    } else {
        return 0;
    }
}

unsigned
IQUnit::numFreeEntries(const DynInstPtr &inst) const
{
    const ThreadID tid = inst->threadNumber;
    const OpClass op_class = inst->opClass();
    // Return 0 if the IQ cannot accept the specific op class
    if (op_class != No_OpClass && !_fuPool->isCapable(op_class)) {
        return 0;
    } else {
        return numFreeEntries(tid);
    }
}

int
IQUnit::issueWindowOffset(const DynInstPtr &inst) const
{
    int offset = 0;

    for (const auto &entry : _orderedInsts) {
        /*
         * Issued memory operations may remain allocated until completion.
         * They no longer occupy a visible position in the issue window.
         */
        if (entry->isIssued() || entry->isSquashed()) {
            continue;
        }

        if (entry == inst) {
            return offset;
        }

        ++offset;
    }

    return -1;
}

void
IQUnit::markReady(const DynInstPtr &inst)
{
    assert(inst);
    assert(inst->iq == this);

    for (const auto &entry : _readyInsts) {
        if (entry == inst) {
            return;
        }
    }

    _readyInsts.push_back(inst);
}

void
IQUnit::markNotReady(const DynInstPtr &inst)
{
    for (auto it = _readyInsts.begin(); it != _readyInsts.end(); ++it) {
        if (*it == inst) {
            _readyInsts.erase(it);
            return;
        }
    }
}

bool
IQUnit::isReady(const DynInstPtr &inst) const
{
    for (const auto &entry : _readyInsts) {
        if (entry == inst) {
            return true;
        }
    }

    return false;
}

std::vector<DynInstPtr>
IQUnit::visibleInstructions() const
{
    std::vector<DynInstPtr> visible;
    int offset = 0;

    for (const auto &entry : _orderedInsts) {
        if (entry->isIssued() || entry->isSquashed()) {
            continue;
        }

        if (_enableNSkip &&
            offset > static_cast<int>(_nSkip)) {
            break;
        }

        visible.push_back(entry);
        ++offset;
    }

    return visible;
}

std::vector<DynInstPtr>
IQUnit::readyCandidates() const
{
    std::vector<DynInstPtr> candidates;

    for (const auto &entry : visibleInstructions()) {
        if (isReady(entry)) {
            candidates.push_back(entry);
        }
    }

    return candidates;
}

InstructionQueue::FUCompletion::FUCompletion(const DynInstPtr &_inst,
                                             FUPool *fu_pool, int fu_idx,
                                             InstructionQueue *iq_ptr)
    : Event(Stat_Event_Pri, AutoDelete),
      inst(_inst),
      fuPool(fu_pool),
      fuIdx(fu_idx),
      iqPtr(iq_ptr),
      freeFU(false)
{
}

void
InstructionQueue::FUCompletion::process()
{
    if (freeFU) {
        iqPtr->processFUCompletion(inst, fuPool, fuIdx);
    } else {
        iqPtr->processFUCompletion(inst, nullptr, -1);
    }
    inst = NULL;
}


const char *
InstructionQueue::FUCompletion::description() const
{
    return "Functional unit completion";
}

InstructionQueue::InstructionQueue(CPU *cpu_ptr, IEW *iew_ptr,
                                   const BaseO3CPUParams &params)
    : cpu(cpu_ptr),
      iewStage(iew_ptr),
      iqs(params.instQueues),
      iqSteeringPolicy(params.iqSteeringPolicy),
      nextIntAluIQ(0),
      useLocalIQPicker(params.useLocalIQPicker),
      numThreads(params.numThreads),
      totalWidth(params.issueWidth),
      commitToIEWDelay(params.commitToIEWDelay),
      iqStats(cpu, totalWidth, params.instQueues.size()),
      iqIOStats(cpu)
{
    assert(iqSteeringPolicy <= 3);

    const auto &reg_classes = params.isa[0]->regClasses();
    // Set the number of total physical registers
    // As the vector registers have two addressing modes, they are added twice
    numPhysRegs =
        params.numPhysIntRegs + params.numPhysFloatRegs +
        params.numPhysVecRegs +
        params.numPhysVecRegs * (reg_classes.at(VecElemClass)->numRegs() /
                                 reg_classes.at(VecRegClass)->numRegs()) +
        params.numPhysVecPredRegs + params.numPhysMatRegs +
        params.numPhysCCRegs + reg_classes.at(MiscRegClass)->numRegs();

    //Create an entry for each physical register within the
    //dependency graph.
    dependGraph.resize(numPhysRegs);

    // Resize the register scoreboard.
    regScoreboard.resize(numPhysRegs);

    //Initialize Mem Dependence Units
    for (ThreadID tid = 0; tid < MaxThreads; tid++) {
        memDepUnit[tid].init(params, tid, cpu_ptr);
        memDepUnit[tid].setIQ(this);
    }

    resetState();
}

InstructionQueue::~InstructionQueue()
{
    dependGraph.reset();
#ifdef GEM5_DEBUG
    cprintf("Nodes traversed: %i, removed: %i\n",
            dependGraph.nodesTraversed, dependGraph.nodesRemoved);
#endif
}

std::string
InstructionQueue::name() const
{
    return cpu->name() + ".iq";
}

InstructionQueue::IQStats::IQStats(
    CPU *cpu,
    const unsigned &total_width,
    unsigned num_iqs)
    : statistics::Group(cpu),
      ADD_STAT(instsAdded, statistics::units::Count::get(),
               "Number of instructions added to the IQ (excludes non-spec)"),
      ADD_STAT(nonSpecInstsAdded, statistics::units::Count::get(),
               "Number of non-speculative instructions added to the IQ"),
      ADD_STAT(steerDispatches, statistics::units::Count::get(),
               "Instructions dispatched into each physical IQ"),
      ADD_STAT(steerIntAluDispatches, statistics::units::Count::get(),
               "IntAlu instructions dispatched into each physical IQ"),
      ADD_STAT(steerIntMultDispatches, statistics::units::Count::get(),
               "IntMult instructions dispatched into each physical IQ"),
      ADD_STAT(steerOccupancySum, statistics::units::Count::get(),
               "Sum of physical IQ occupancy samples"),
      ADD_STAT(steerFullCycles, statistics::units::Cycle::get(),
               "Scheduler samples where each physical IQ was full"),
      ADD_STAT(steerEmptyCycles, statistics::units::Cycle::get(),
               "Scheduler samples where each physical IQ was empty"),
      ADD_STAT(steerAtOrBelowHalfCycles, statistics::units::Cycle::get(),
               "Scheduler samples where physical IQ occupancy was <= 1/2"),
      ADD_STAT(steerAtOrBelowThreeQuarterCycles, statistics::units::Cycle::get(),
               "Scheduler samples where physical IQ occupancy was <= 3/4"),
      ADD_STAT(steerOccupancySamples, statistics::units::Cycle::get(),
               "Number of physical IQ occupancy samples"),
      ADD_STAT(dispatchWrite1Cycles, statistics::units::Cycle::get(),
               "Cycles with exactly one dispatch write into each physical IQ"),
      ADD_STAT(dispatchWrite2Cycles, statistics::units::Cycle::get(),
               "Cycles with exactly two dispatch writes into each physical IQ"),
      ADD_STAT(dispatchWrite3PlusCycles, statistics::units::Cycle::get(),
               "Cycles with three or more dispatch writes into each physical IQ"),
      ADD_STAT(instsIssued, statistics::units::Count::get(),
               "Number of instructions issued"),
      ADD_STAT(intInstsIssued, statistics::units::Count::get(),
               "Number of integer instructions issued"),
      ADD_STAT(floatInstsIssued, statistics::units::Count::get(),
               "Number of float instructions issued"),
      ADD_STAT(branchInstsIssued, statistics::units::Count::get(),
               "Number of branch instructions issued"),
      ADD_STAT(memInstsIssued, statistics::units::Count::get(),
               "Number of memory instructions issued"),
      ADD_STAT(miscInstsIssued, statistics::units::Count::get(),
               "Number of miscellaneous instructions issued"),
      ADD_STAT(squashedInstsIssued, statistics::units::Count::get(),
               "Number of squashed instructions issued"),
      ADD_STAT(squashedInstsExamined, statistics::units::Count::get(),
               "Number of squashed instructions iterated over during squash; "
               "mainly for profiling"),
      ADD_STAT(squashedOperandsExamined, statistics::units::Count::get(),
               "Number of squashed operands that are examined and possibly "
               "removed from graph"),
      ADD_STAT(squashedNonSpecRemoved, statistics::units::Count::get(),
               "Number of squashed non-spec instructions that were removed"),
      ADD_STAT(nSkipWindowRejects, statistics::units::Count::get(),
               "Ready candidates rejected outside the N-SKIP window"),
      ADD_STAT(nSkipBlockedCycles, statistics::units::Cycle::get(),
               "Zero-issue cycles with an N-SKIP window rejection"),
      ADD_STAT(nSkipLocalHiddenReadySamples, statistics::units::Count::get(),
               "Ready instructions hidden beyond local N-SKIP windows at scheduling-cycle entry"),
      ADD_STAT(nSkipLocalHiddenReadyCycles, statistics::units::Cycle::get(),
               "Scheduling cycles with at least one ready instruction hidden beyond a local N-SKIP window"),
      ADD_STAT(nSkipLocalNoVisibleReadyCycles, statistics::units::Cycle::get(),
               "Scheduling cycles where an IQ had hidden ready work but no visible ready candidate"),
      ADD_STAT(nSkipLocalHiddenReadySamplesByIQ, statistics::units::Count::get(),
               "Ready instructions hidden beyond local N-SKIP windows by physical IQ"),
      ADD_STAT(nSkipLocalNoVisibleReadyCyclesByIQ, statistics::units::Cycle::get(),
               "Cycles with hidden ready work but no visible ready candidate by physical IQ"),
      ADD_STAT(nSkipSameCycleNewExposureCycles, statistics::units::Cycle::get(),
               "Scheduling cycles where a later issue round exposed a new N-SKIP position"),
      ADD_STAT(nSkipSameCycleNewExposurePositions, statistics::units::Count::get(),
               "Distinct positions first exposed after round zero in the same scheduling cycle"),
      ADD_STAT(nSkipSameCycleNewExposureByIQ, statistics::units::Count::get(),
               "Same-cycle newly exposed positions by physical IQ"),
      ADD_STAT(nSkipRoundVisiblePositions, statistics::units::Count::get(),
               "Total N-SKIP structural positions visible in each selection round"),
      ADD_STAT(nSkipCycleUniqueVisiblePositions, statistics::units::Count::get(),
               "Distinct N-SKIP structural positions exposed across one scheduling cycle"),
      ADD_STAT(nSkipHeadIssued, statistics::units::Count::get(),
               "N-SKIP instructions issued from the queue head"),
      ADD_STAT(nSkipBypassIssued, statistics::units::Count::get(),
               "N-SKIP instructions issued from non-head offsets"),
      ADD_STAT(nSkipIssuedOffset, statistics::units::Count::get(),
               "Distribution of N-SKIP issue-window offsets"),
      ADD_STAT(numIssuedDist, statistics::units::Count::get(),
               "Number of insts issued each cycle"),
      ADD_STAT(statFuBusy, statistics::units::Count::get(),
               "attempts to use FU when none available"),
      ADD_STAT(issuedInstType, statistics::units::Count::get(),
               "Number of instructions issued per FU type, per thread"),
      ADD_STAT(issueRate,
               statistics::units::Rate<statistics::units::Count,
                                       statistics::units::Cycle>::get(),
               "Inst issue rate", instsIssued / cpu->baseStats.numCycles),
      ADD_STAT(fuBusy, statistics::units::Count::get(),
               "FU busy when requested"),
      ADD_STAT(fuBusyRate,
               statistics::units::Rate<statistics::units::Count,
                                       statistics::units::Count>::get(),
               "FU busy rate (busy events/executed inst)")
{
    steerDispatches
        .init(num_iqs)
        .flags(statistics::total);

    steerIntAluDispatches
        .init(num_iqs)
        .flags(statistics::total);

    steerIntMultDispatches
        .init(num_iqs)
        .flags(statistics::total);

    steerOccupancySum
        .init(num_iqs)
        .flags(statistics::total);

    steerFullCycles
        .init(num_iqs)
        .flags(statistics::total);

    steerEmptyCycles.init(num_iqs).flags(statistics::total);
    steerAtOrBelowHalfCycles.init(num_iqs).flags(statistics::total);
    steerAtOrBelowThreeQuarterCycles.init(num_iqs).flags(statistics::total);

    dispatchWrite1Cycles.init(num_iqs).flags(statistics::total);
    dispatchWrite2Cycles.init(num_iqs).flags(statistics::total);
    dispatchWrite3PlusCycles.init(num_iqs).flags(statistics::total);

    nSkipLocalHiddenReadySamplesByIQ
        .init(num_iqs)
        .flags(statistics::total);
    nSkipLocalNoVisibleReadyCyclesByIQ
        .init(num_iqs)
        .flags(statistics::total);
    nSkipSameCycleNewExposureByIQ
        .init(num_iqs)
        .flags(statistics::total);

    nSkipRoundVisiblePositions
        .init(0, 64, 1)
        .flags(statistics::pdf);
    nSkipCycleUniqueVisiblePositions
        .init(0, 64, 1)
        .flags(statistics::pdf);

    for (unsigned i = 0; i < num_iqs; ++i) {
        const std::string iq_name = "IQ" + std::to_string(i);

        steerDispatches.subname(i, iq_name);
        steerIntAluDispatches.subname(i, iq_name);
        steerIntMultDispatches.subname(i, iq_name);
        steerOccupancySum.subname(i, iq_name);
        steerFullCycles.subname(i, iq_name);
        steerEmptyCycles.subname(i, iq_name);
        steerAtOrBelowHalfCycles.subname(i, iq_name);
        steerAtOrBelowThreeQuarterCycles.subname(i, iq_name);
        dispatchWrite1Cycles.subname(i, iq_name);
        dispatchWrite2Cycles.subname(i, iq_name);
        dispatchWrite3PlusCycles.subname(i, iq_name);
        nSkipLocalHiddenReadySamplesByIQ.subname(i, iq_name);
        nSkipLocalNoVisibleReadyCyclesByIQ.subname(i, iq_name);
        nSkipSameCycleNewExposureByIQ.subname(i, iq_name);
    }

    steerOccupancySamples
        .prereq(steerOccupancySamples);

    instsAdded
        .prereq(instsAdded);

    nonSpecInstsAdded
        .prereq(nonSpecInstsAdded);

    instsIssued
        .prereq(instsIssued);

    intInstsIssued
        .prereq(intInstsIssued);

    floatInstsIssued
        .prereq(floatInstsIssued);

    branchInstsIssued
        .prereq(branchInstsIssued);

    memInstsIssued
        .prereq(memInstsIssued);

    miscInstsIssued
        .prereq(miscInstsIssued);

    squashedInstsIssued
        .prereq(squashedInstsIssued);

    squashedInstsExamined
        .prereq(squashedInstsExamined);

    squashedOperandsExamined
        .prereq(squashedOperandsExamined);

    squashedNonSpecRemoved
        .prereq(squashedNonSpecRemoved);

    nSkipWindowRejects
        .prereq(nSkipWindowRejects);

    nSkipBlockedCycles
        .prereq(nSkipBlockedCycles);

    nSkipLocalHiddenReadySamples
        .prereq(nSkipLocalHiddenReadySamples);

    nSkipLocalHiddenReadyCycles
        .prereq(nSkipLocalHiddenReadyCycles);

    nSkipLocalNoVisibleReadyCycles
        .prereq(nSkipLocalNoVisibleReadyCycles);

    nSkipSameCycleNewExposureCycles
        .prereq(nSkipSameCycleNewExposureCycles);
    nSkipSameCycleNewExposurePositions
        .prereq(nSkipSameCycleNewExposurePositions);

    nSkipHeadIssued
        .prereq(nSkipHeadIssued);

    nSkipBypassIssued
        .prereq(nSkipBypassIssued);

    nSkipIssuedOffset
        .init(0, 16, 1)
        .flags(statistics::pdf);
/*
    queueResDist
        .init(Num_OpClasses, 0, 99, 2)
        .name(name() + ".IQ:residence:")
        .desc("cycles from dispatch to issue")
        .flags(total | pdf | cdf )
        ;
    for (int i = 0; i < Num_OpClasses; ++i) {
        queueResDist.subname(i, opClassStrings[i]);
    }
*/
    numIssuedDist
        .init(0,total_width,1)
        .flags(statistics::pdf)
        ;
/*
    dist_unissued
        .init(Num_OpClasses+2)
        .name(name() + ".unissued_cause")
        .desc("Reason ready instruction not issued")
        .flags(pdf | dist)
        ;
    for (int i=0; i < (Num_OpClasses + 2); ++i) {
        dist_unissued.subname(i, unissued_names[i]);
    }
*/
    issuedInstType.init(cpu->numThreads, enums::Num_OpClass)
        .flags(statistics::total | statistics::pdf | statistics::dist);
    issuedInstType.ysubnames(enums::OpClassStrings);

    //
    //  How long did instructions for a particular FU type wait prior to issue
    //
/*
    issueDelayDist
        .init(Num_OpClasses,0,99,2)
        .name(name() + ".")
        .desc("cycles from operands ready to issue")
        .flags(pdf | cdf)
        ;
    for (int i=0; i<Num_OpClasses; ++i) {
        std::stringstream subname;
        subname << opClassStrings[i] << "_delay";
        issueDelayDist.subname(i, subname.str());
    }
*/
    issueRate
        .flags(statistics::total)
        ;

    statFuBusy
        .init(Num_OpClasses)
        .flags(statistics::pdf | statistics::dist)
        ;
    for (int i=0; i < Num_OpClasses; ++i) {
        statFuBusy.subname(i, enums::OpClassStrings[i]);
    }

    fuBusy
        .init(cpu->numThreads)
        .flags(statistics::total)
        ;

    fuBusyRate
        .flags(statistics::total)
        ;
    fuBusyRate = fuBusy / instsIssued;
}

InstructionQueue::IQIOStats::IQIOStats(statistics::Group *parent)
    : statistics::Group(parent),
    ADD_STAT(intInstQueueReads, statistics::units::Count::get(),
             "Number of integer instruction queue reads"),
    ADD_STAT(intInstQueueWrites, statistics::units::Count::get(),
             "Number of integer instruction queue writes"),
    ADD_STAT(intInstQueueWakeupAccesses, statistics::units::Count::get(),
             "Number of integer instruction queue wakeup accesses"),
    ADD_STAT(fpInstQueueReads, statistics::units::Count::get(),
             "Number of floating instruction queue reads"),
    ADD_STAT(fpInstQueueWrites, statistics::units::Count::get(),
             "Number of floating instruction queue writes"),
    ADD_STAT(fpInstQueueWakeupAccesses, statistics::units::Count::get(),
             "Number of floating instruction queue wakeup accesses"),
    ADD_STAT(vecInstQueueReads, statistics::units::Count::get(),
             "Number of vector instruction queue reads"),
    ADD_STAT(vecInstQueueWrites, statistics::units::Count::get(),
             "Number of vector instruction queue writes"),
    ADD_STAT(vecInstQueueWakeupAccesses, statistics::units::Count::get(),
             "Number of vector instruction queue wakeup accesses"),
    ADD_STAT(intAluAccesses, statistics::units::Count::get(),
             "Number of integer alu accesses"),
    ADD_STAT(fpAluAccesses, statistics::units::Count::get(),
             "Number of floating point alu accesses"),
    ADD_STAT(vecAluAccesses, statistics::units::Count::get(),
             "Number of vector alu accesses")
{
    using namespace statistics;
    intInstQueueReads
        .flags(total);

    intInstQueueWrites
        .flags(total);

    intInstQueueWakeupAccesses
        .flags(total);

    fpInstQueueReads
        .flags(total);

    fpInstQueueWrites
        .flags(total);

    fpInstQueueWakeupAccesses
        .flags(total);

    vecInstQueueReads
        .flags(total);

    vecInstQueueWrites
        .flags(total);

    vecInstQueueWakeupAccesses
        .flags(total);

    intAluAccesses
        .flags(total);

    fpAluAccesses
        .flags(total);

    vecAluAccesses
        .flags(total);
}

void
InstructionQueue::resetState()
{
    //Initialize thread IQ counts
    for (ThreadID tid = 0; tid < MaxThreads; tid++) {
        instList[tid].clear();
    }

    // Initialize the number of free IQ entries.
    for (auto iq : iqs) {
        iq->resetState();
    }

    // Note that in actuality, the registers corresponding to the logical
    // registers start off as ready.  However this doesn't matter for the
    // IQ as the instruction should have been correctly told if those
    // registers are ready in rename.  Thus it can all be initialized as
    // unready.
    for (int i = 0; i < numPhysRegs; ++i) {
        regScoreboard[i] = false;
    }

    for (ThreadID tid = 0; tid < MaxThreads; ++tid) {
        squashedSeqNum[tid] = 0;
    }

    for (int i = 0; i < Num_OpClasses; ++i) {
        while (!readyInsts[i].empty())
            readyInsts[i].pop();
        queueOnList[i] = false;
        readyIt[i] = listOrder.end();
    }
    nonSpecInsts.clear();
    listOrder.clear();
    deferredMemInsts.clear();
    blockedMemInsts.clear();
    retryMemInsts.clear();
    wbOutstanding = 0;
}

void
InstructionQueue::setActiveThreads(list<ThreadID> *at_ptr)
{
    for (auto iq : iqs) {
        iq->setActiveThreads(at_ptr);
    }
}

void
InstructionQueue::setIssueToExecuteQueue(TimeBuffer<IssueStruct> *i2e_ptr)
{
      issueToExecuteQueue = i2e_ptr;
}

void
InstructionQueue::setTimeBuffer(TimeBuffer<TimeStruct> *tb_ptr)
{
    timeBuffer = tb_ptr;

    fromCommit = timeBuffer->getWire(-commitToIEWDelay);
}

bool
InstructionQueue::isDrained() const
{
    bool drained = dependGraph.empty() &&
                   instsToExecute.empty() &&
                   wbOutstanding == 0;
    for (ThreadID tid = 0; tid < numThreads; ++tid)
        drained = drained && memDepUnit[tid].isDrained();

    return drained;
}

void
InstructionQueue::drainSanityCheck() const
{
    assert(dependGraph.empty());
    assert(instsToExecute.empty());
    for (ThreadID tid = 0; tid < numThreads; ++tid)
        memDepUnit[tid].drainSanityCheck();
}

void
InstructionQueue::takeOverFrom()
{
    resetState();
}

unsigned
InstructionQueue::numFreeEntries()
{
    unsigned free_entries = 0;
    for (auto iq : iqs) {
        free_entries += iq->numFreeEntries();
    }
    return free_entries;
}

unsigned
InstructionQueue::numFreeEntries(ThreadID tid)
{
    unsigned free_entries = 0;
    for (auto iq : iqs) {
        free_entries += iq->numFreeEntries(tid);
    }
    return free_entries;
}

unsigned
InstructionQueue::numFreeEntries(const DynInstPtr &inst)
{
    unsigned free_entries = 0;
    for (auto iq : iqs) {
        free_entries += iq->numFreeEntries(inst);
    }
    return free_entries;
}

// Might want to do something more complex if it knows how many instructions
// will be issued this cycle.
bool
InstructionQueue::isFull()
{
    return numFreeEntries() == 0;
}

bool
InstructionQueue::isFull(ThreadID tid)
{
    return numFreeEntries(tid) == 0;
}

bool
InstructionQueue::isFull(const DynInstPtr &inst)
{
    return !hasDispatchSlot(inst);
}

std::vector<FUPool *>
InstructionQueue::allFUPools()
{
    std::vector<FUPool *> res;
    for (auto iq : iqs) {
        res.push_back(iq->fuPool());
    }
    return res;
}

bool
InstructionQueue::hasReadyInsts()
{
    /*
     * The distributed local picker does not populate the legacy
     * readyInsts/listOrder structures.  Use the same bounded local
     * visibility as scheduleReadyInsts() when deciding whether IEW
     * still has schedulable work.
     *
     * This is especially important when a visible ready instruction
     * is waiting for a busy/shared FU: IEW must remain active so the
     * request can be retried on a later cycle.
     */
    if (useLocalIQPicker) {
        for (auto iq : iqs) {
            if (!iq->readyCandidates().empty()) {
                return true;
            }
        }

        return false;
    }

    if (!listOrder.empty()) {
        return true;
    }

    for (int i = 0; i < Num_OpClasses; ++i) {
        if (!readyInsts[i].empty()) {
            return true;
        }
    }

    return false;
}

bool
InstructionQueue::iqCanAcceptDispatch(
    unsigned iq_index, const DynInstPtr &inst) const
{
    assert(inst);
    assert(iq_index < iqs.size());

    IQUnit *iq = iqs[iq_index];

    if (iq->numFreeEntries(inst) == 0) {
        return false;
    }

    const unsigned cap = iq->dispatchWriteCap();

    if (cap == 0) {
        return true;
    }

    const unsigned writes =
        dispatchWritesThisCycle.size() == iqs.size() ?
        dispatchWritesThisCycle[iq_index] : 0;

    return writes < cap;
}

bool
InstructionQueue::hasDispatchSlot(const DynInstPtr &inst) const
{
    for (unsigned i = 0; i < iqs.size(); ++i) {
        if (iqCanAcceptDispatch(i, inst)) {
            return true;
        }
    }

    return false;
}

IQUnit *
InstructionQueue::findIQ(const DynInstPtr &inst)
{
    const bool steer_int_alu =
        inst->opClass() == enums::IntAlu &&
        iqs.size() > 1;

    if (!steer_int_alu || iqSteeringPolicy == 0) {
        for (unsigned i = 0; i < iqs.size(); ++i) {
            if (iqCanAcceptDispatch(i, inst)) {
                return iqs[i];
            }
        }

        return nullptr;
    }

    if (iqSteeringPolicy == 1) {
        IQUnit *best = nullptr;
        unsigned best_used = 0;

        for (unsigned i = 0; i < iqs.size(); ++i) {
            if (!iqCanAcceptDispatch(i, inst)) {
                continue;
            }

            IQUnit *iq = iqs[i];
            const unsigned used =
                iq->numEntries() - iq->numFreeEntries();

            if (!best || used < best_used) {
                best = iq;
                best_used = used;
            }
        }

        return best;
    }

    if (iqSteeringPolicy == 2) {
        for (unsigned offset = 0; offset < iqs.size(); ++offset) {
            const unsigned index =
                (nextIntAluIQ + offset) % iqs.size();

            if (iqCanAcceptDispatch(index, inst)) {
                nextIntAluIQ = (index + 1) % iqs.size();
                return iqs[index];
            }
        }

        return nullptr;
    }

    assert(iqSteeringPolicy == 3);

    for (unsigned offset = 0; offset < iqs.size(); ++offset) {
        const unsigned index = iqs.size() - 1 - offset;

        if (iqCanAcceptDispatch(index, inst)) {
            return iqs[index];
        }
    }

    return nullptr;
}

void
InstructionQueue::beginDispatchCycle()
{
    if (dispatchWritesThisCycle.size() != iqs.size()) {
        dispatchWritesThisCycle.assign(iqs.size(), 0);
    } else {
        std::fill(
            dispatchWritesThisCycle.begin(),
            dispatchWritesThisCycle.end(),
            0);
    }
}

void
InstructionQueue::endDispatchCycle()
{
    assert(dispatchWritesThisCycle.size() == iqs.size());

    for (unsigned i = 0; i < dispatchWritesThisCycle.size(); ++i) {
        const unsigned writes = dispatchWritesThisCycle[i];

        if (writes == 1) {
            iqStats.dispatchWrite1Cycles[i]++;
        } else if (writes == 2) {
            iqStats.dispatchWrite2Cycles[i]++;
        } else if (writes >= 3) {
            iqStats.dispatchWrite3PlusCycles[i]++;
        }
    }
}

void
InstructionQueue::recordSteeringDispatch(
    IQUnit *iq, const DynInstPtr &inst)
{
    assert(iq);
    assert(inst);

    unsigned iq_index = 0;

    while (iq_index < iqs.size() && iqs[iq_index] != iq) {
        ++iq_index;
    }

    assert(iq_index < iqs.size());

    if (dispatchWritesThisCycle.size() != iqs.size()) {
        dispatchWritesThisCycle.assign(iqs.size(), 0);
    }

    const unsigned cap = iq->dispatchWriteCap();

    assert(
        cap == 0 ||
        dispatchWritesThisCycle[iq_index] < cap
    );

    dispatchWritesThisCycle[iq_index]++;

    iqStats.steerDispatches[iq_index]++;

    if (inst->opClass() == enums::IntAlu) {
        iqStats.steerIntAluDispatches[iq_index]++;
    } else if (inst->opClass() == enums::IntMult) {
        iqStats.steerIntMultDispatches[iq_index]++;
    }
}

void
InstructionQueue::insert(const DynInstPtr &new_inst)
{
    if (new_inst->isFloating()) {
        iqIOStats.fpInstQueueWrites++;
    } else if (new_inst->isVector()) {
        iqIOStats.vecInstQueueWrites++;
    } else {
        iqIOStats.intInstQueueWrites++;
    }
    // Make sure the instruction is valid
    assert(new_inst);

    DPRINTF(IQ, "Adding instruction [sn:%llu] PC %s to the IQ.\n",
            new_inst->seqNum, new_inst->pcState());

    instList[new_inst->threadNumber].push_back(new_inst);

    auto iq = findIQ(new_inst);
    assert(iq);
    iq->insert(new_inst);
    recordSteeringDispatch(iq, new_inst);

    // Look through its source registers (physical regs), and mark any
    // dependencies.
    addToDependents(new_inst);

    // Have this instruction set itself as the producer of its destination
    // register(s).
    addToProducers(new_inst);

    if (new_inst->isMemRef()) {
        memDepUnit[new_inst->threadNumber].insert(new_inst);
    } else {
        addIfReady(new_inst);
    }

    ++iqStats.instsAdded;
}

void
InstructionQueue::insertNonSpec(const DynInstPtr &new_inst)
{
    // @todo: Clean up this code; can do it by setting inst as unable
    // to issue, then calling normal insert on the inst.
    if (new_inst->isFloating()) {
        iqIOStats.fpInstQueueWrites++;
    } else if (new_inst->isVector()) {
        iqIOStats.vecInstQueueWrites++;
    } else {
        iqIOStats.intInstQueueWrites++;
    }

    assert(new_inst);

    nonSpecInsts[new_inst->seqNum] = new_inst;

    DPRINTF(IQ, "Adding non-speculative instruction [sn:%llu] PC %s "
            "to the IQ.\n",
            new_inst->seqNum, new_inst->pcState());

    instList[new_inst->threadNumber].push_back(new_inst);

    auto iq = findIQ(new_inst);
    assert(iq);
    iq->insert(new_inst);
    recordSteeringDispatch(iq, new_inst);

    // Have this instruction set itself as the producer of its destination
    // register(s).
    addToProducers(new_inst);

    // If it's a memory instruction, add it to the memory dependency
    // unit.
    if (new_inst->isMemRef()) {
        memDepUnit[new_inst->threadNumber].insertNonSpec(new_inst);
    }

    ++iqStats.nonSpecInstsAdded;
}

void
InstructionQueue::insertBarrier(const DynInstPtr &barr_inst)
{
    memDepUnit[barr_inst->threadNumber].insertBarrier(barr_inst);

    insertNonSpec(barr_inst);
}

DynInstPtr
InstructionQueue::getInstToExecute()
{
    assert(!instsToExecute.empty());
    DynInstPtr inst = std::move(instsToExecute.front());
    instsToExecute.pop_front();
    if (inst->isFloating()) {
        iqIOStats.fpInstQueueReads++;
    } else if (inst->isVector()) {
        iqIOStats.vecInstQueueReads++;
    } else {
        iqIOStats.intInstQueueReads++;
    }
    return inst;
}

void
InstructionQueue::addToOrderList(OpClass op_class)
{
    assert(!readyInsts[op_class].empty());

    ListOrderEntry queue_entry;

    queue_entry.queueType = op_class;

    queue_entry.oldestInst = readyInsts[op_class].top()->seqNum;

    ListOrderIt list_it = listOrder.begin();
    ListOrderIt list_end_it = listOrder.end();

    while (list_it != list_end_it) {
        if ((*list_it).oldestInst > queue_entry.oldestInst) {
            break;
        }

        list_it++;
    }

    readyIt[op_class] = listOrder.insert(list_it, queue_entry);
    queueOnList[op_class] = true;
}

void
InstructionQueue::moveToYoungerInst(ListOrderIt list_order_it)
{
    // Get iterator of next item on the list
    // Delete the original iterator
    // Determine if the next item is either the end of the list or younger
    // than the new instruction.  If so, then add in a new iterator right here.
    // If not, then move along.
    ListOrderEntry queue_entry;
    OpClass op_class = (*list_order_it).queueType;
    ListOrderIt next_it = list_order_it;

    ++next_it;

    queue_entry.queueType = op_class;
    queue_entry.oldestInst = readyInsts[op_class].top()->seqNum;

    while (next_it != listOrder.end() &&
           (*next_it).oldestInst < queue_entry.oldestInst) {
        ++next_it;
    }

    readyIt[op_class] = listOrder.insert(next_it, queue_entry);
}

void
InstructionQueue::processFUCompletion(const DynInstPtr &inst, FUPool *fu_pool,
                                      int fu_idx)
{
    DPRINTF(IQ, "Processing FU completion [sn:%llu]\n", inst->seqNum);
    assert(!cpu->switchedOut());
    // The CPU could have been sleeping until this op completed (*extremely*
    // long latency op).  Wake it if it was.  This may be overkill.
   --wbOutstanding;
    iewStage->wakeCPU();

    if (fu_pool) {
        assert(fu_idx > -1);
        fu_pool->freeUnitNextCycle(fu_idx);
    }

    // @todo: Ensure that these FU Completions happen at the beginning
    // of a cycle, otherwise they could add too many instructions to
    // the queue.
    issueToExecuteQueue->access(-1)->size++;
    instsToExecute.push_back(inst);
}

// @todo: Figure out a better way to remove the squashed items from the
// lists.  Checking the top item of each list to see if it's squashed
// wastes time and forces jumps.
void
InstructionQueue::scheduleReadyInsts()
{
    DPRINTF(IQ, "Attempting to schedule ready instructions from "
            "the IQ.\n");

    IssueStruct *i2e_info = issueToExecuteQueue->access(0);

    DynInstPtr mem_inst;
    while ((mem_inst = getDeferredMemInstToExecute())) {
        addReadyMemInst(mem_inst);
    }

    // See if any cache blocked instructions are able to be executed
    while ((mem_inst = getBlockedMemInstToExecute())) {
        addReadyMemInst(mem_inst);
    }

    // Have iterator to head of the list
    // While I haven't exceeded bandwidth or reached the end of the list,
    // Try to get a FU that can do what this op needs.
    // If successful, change the oldestInst to the new top of the list, put
    // the queue in the proper place in the list.
    // Increment the iterator.
    // This will avoid trying to schedule a certain op class if there are no
    // FUs that handle it.
    /*
     * Sample physical queue pressure once per scheduling cycle.
     *
     * This is observation only and must not influence scheduling.
     */
    iqStats.steerOccupancySamples++;

    for (unsigned i = 0; i < iqs.size(); ++i) {
        const unsigned used =
            iqs[i]->numEntries() - iqs[i]->numFreeEntries();

        iqStats.steerOccupancySum[i] += used;

        const unsigned entries = iqs[i]->numEntries();

        if (used == 0)
            iqStats.steerEmptyCycles[i]++;

        if (used * 2 <= entries)
            iqStats.steerAtOrBelowHalfCycles[i]++;

        if (used * 4 <= entries * 3)
            iqStats.steerAtOrBelowThreeQuarterCycles[i]++;

        if (iqs[i]->numFreeEntries() == 0) {
            iqStats.steerFullCycles[i]++;
        }
    }

    /*
     * Shadow validation for the future distributed picker.
     *
     * This must not affect issue selection.  It only verifies that each
     * IQ can independently reconstruct its scheduler-ready candidates
     * from local ownership + ready-state information.
     */
    for (auto iq : iqs) {
        const auto candidates = iq->readyCandidates();

        InstSeqNum previous = 0;
        bool first = true;

        for (const auto &candidate : candidates) {
            assert(candidate);
            assert(candidate->iq == iq);
            assert(iq->isReady(candidate));
            assert(!candidate->isIssued());
            assert(!candidate->isSquashed());

            const int offset = iq->issueWindowOffset(candidate);
            assert(offset >= 0);

            if (iq->nSkipEnabled()) {
                assert(offset <= static_cast<int>(iq->nSkip()));
            }

            if (!first) {
                assert(previous < candidate->seqNum);
            }

            previous = candidate->seqNum;
            first = false;
        }
    }

    if (useLocalIQPicker) {
        int total_issued = 0;

        /*
         * Behavior-neutral local N-SKIP visibility observation.
         *
         * The local picker truncates candidate discovery at Head..Head+N,
         * so legacy nSkipWindowRejects/nSkipBlockedCycles intentionally stay
         * zero here. Sample the hidden scheduler-ready work directly instead.
         */
        uint64_t hidden_ready = 0;
        bool any_hidden_ready = false;
        bool any_iq_hidden_with_no_visible = false;

        for (unsigned iq_index = 0; iq_index < iqs.size(); ++iq_index) {
            auto iq = iqs[iq_index];

            if (!iq->nSkipEnabled())
                continue;

            const auto visible = iq->readyCandidates();
            const unsigned ready = iq->readyCount();

            assert(visible.size() <= ready);

            if (ready > visible.size()) {
                const uint64_t hidden =
                    static_cast<uint64_t>(ready - visible.size());

                hidden_ready += hidden;
                any_hidden_ready = true;
                iqStats.nSkipLocalHiddenReadySamplesByIQ[iq_index] += hidden;

                if (visible.empty()) {
                    any_iq_hidden_with_no_visible = true;
                    iqStats.nSkipLocalNoVisibleReadyCyclesByIQ[iq_index]++;
                }
            }
        }

        iqStats.nSkipLocalHiddenReadySamples += hidden_ready;

        if (any_hidden_ready)
            iqStats.nSkipLocalHiddenReadyCycles++;

        if (any_iq_hidden_with_no_visible)
            iqStats.nSkipLocalNoVisibleReadyCycles++;

        /*
         * A candidate that saw NoFreeFU cannot become issuable again
         * within this scheduling cycle because FU release occurs on a
         * later cycle.  Remember it so repeated slot refreshes do not
         * retry the same blocked instruction.
         */
        std::vector<InstSeqNum> fu_blocked;

        while (total_issued < totalWidth) {
            std::vector<DynInstPtr> candidates;

            /*
             * Refresh after every successful issue.  Issuing an older
             * instruction can slide a bounded N-SKIP window forward and
             * expose a new candidate for another issue slot in the same
             * cycle.
             */
            for (auto iq : iqs) {
                const auto local = iq->readyCandidates();

                for (const auto &inst : local) {
                    if (std::find(
                            fu_blocked.begin(),
                            fu_blocked.end(),
                            inst->seqNum) == fu_blocked.end()) {
                        candidates.push_back(inst);
                    }
                }
            }

            if (candidates.empty()) {
                break;
            }

            std::sort(
                candidates.begin(),
                candidates.end(),
                [](const DynInstPtr &a, const DynInstPtr &b) {
                    return a->seqNum < b->seqNum;
                });

            bool issued_this_slot = false;

            for (const auto &issuing_inst : candidates) {
                assert(issuing_inst);
                assert(!issuing_inst->isIssued());
                assert(!issuing_inst->isSquashed());

                IQUnit *iq = issuing_inst->iq;
                assert(iq);
                assert(iq->isReady(issuing_inst));

                const OpClass op_class =
                    issuing_inst->opClass();

                if (issuing_inst->isFloating()) {
                    iqIOStats.fpInstQueueReads++;
                } else if (issuing_inst->isVector()) {
                    iqIOStats.vecInstQueueReads++;
                } else {
                    iqIOStats.intInstQueueReads++;
                }

                int nSkipOffset = -1;

                if (iq->nSkipEnabled()) {
                    nSkipOffset =
                        iq->issueWindowOffset(issuing_inst);

                    /*
                     * readyCandidates() is the authoritative bounded
                     * local view, so every returned candidate must be
                     * visible.
                     */
                    assert(nSkipOffset >= 0);
                    assert(
                        nSkipOffset <=
                        static_cast<int>(iq->nSkip()));
                }

                int idx = FUPool::NoNeedFU;
                Cycles op_latency = Cycles(1);
                ThreadID tid =
                    issuing_inst->threadNumber;

                auto fu_pool = iq->fuPool();

                if (op_class != No_OpClass) {
                    idx = fu_pool->getUnit(op_class, iq->fuRequesterId());

                    if (issuing_inst->isFloating()) {
                        iqIOStats.fpAluAccesses++;
                    } else if (issuing_inst->isVector()) {
                        iqIOStats.vecAluAccesses++;
                    } else {
                        iqIOStats.intAluAccesses++;
                    }

                    if (idx > FUPool::NoFreeFU) {
                        op_latency =
                            fu_pool->getOpLatency(op_class);
                    }
                }

                if (idx == FUPool::NoFreeFU) {
                    iqStats.statFuBusy[op_class]++;
                    iqStats.fuBusy[tid]++;
                    fu_blocked.push_back(
                        issuing_inst->seqNum);
                    continue;
                }

                assert(
                    idx > FUPool::NoFreeFU ||
                    idx == FUPool::NoNeedFU ||
                    idx == FUPool::NoCapableFU);

                if (op_latency == Cycles(1)) {
                    i2e_info->size++;
                    instsToExecute.push_back(
                        issuing_inst);

                    if (idx >= 0) {
                        fu_pool->freeUnitNextCycle(idx);
                    }

                    if (idx == FUPool::NoCapableFU) {
                        issuing_inst->setNoCapableFU();
                    }
                } else {
                    assert(idx != FUPool::NoCapableFU);

                    const bool pipelined =
                        fu_pool->isPipelined(op_class);

                    ++wbOutstanding;

                    auto execution =
                        new FUCompletion(
                            issuing_inst,
                            fu_pool,
                            idx,
                            this);

                    cpu->schedule(
                        execution,
                        cpu->clockEdge(
                            Cycles(op_latency - 1)));

                    if (!pipelined) {
                        execution->setFreeFU();
                    } else {
                        fu_pool->freeUnitNextCycle(idx);
                    }
                }

                DPRINTF(
                    IQ,
                    "Local picker issuing PC %s "
                    "[sn:%llu] opclass:%i\\n",
                    issuing_inst->pcState(),
                    issuing_inst->seqNum,
                    op_class);

                iq->markNotReady(issuing_inst);
                issuing_inst->setIssued();

                if (iq->nSkipEnabled()) {
                    assert(nSkipOffset >= 0);

                    iqStats.nSkipIssuedOffset.sample(
                        nSkipOffset);

                    if (nSkipOffset == 0) {
                        iqStats.nSkipHeadIssued++;
                    } else {
                        iqStats.nSkipBypassIssued++;
                    }
                }

                ++total_issued;

#if TRACING_ON
                issuing_inst->issueTick =
                    curTick() -
                    issuing_inst->fetchTick;
#endif

                if (issuing_inst->firstIssue == -1) {
                    issuing_inst->firstIssue = curTick();
                }

                if (!issuing_inst->isMemRef()) {
                    issuing_inst->clearInIQ();
                } else {
                    memDepUnit[tid].issue(
                        issuing_inst);
                }

                iqStats.issuedInstType[
                    tid][op_class]++;

                issued_this_slot = true;
                break;
            }

            if (!issued_this_slot) {
                break;
            }
        }

        iqStats.numIssuedDist.sample(total_issued);
        iqStats.instsIssued += total_issued;

        if (
            total_issued ||
            !retryMemInsts.empty() ||
            !deferredMemInsts.empty()
        ) {
            cpu->activityThisCycle();
        } else {
            DPRINTF(
                IQ,
                "Local picker not able to "
                "schedule any instructions.\\n");
        }

        return;
    }

    int total_issued = 0;
    bool nSkipRejectedThisCycle = false;
    ListOrderIt order_it = listOrder.begin();
    ListOrderIt order_end_it = listOrder.end();

    while (total_issued < totalWidth && order_it != order_end_it) {
        OpClass op_class = (*order_it).queueType;

        assert(!readyInsts[op_class].empty());

        DynInstPtr issuing_inst = readyInsts[op_class].top();

        if (issuing_inst->isFloating()) {
            iqIOStats.fpInstQueueReads++;
        } else if (issuing_inst->isVector()) {
            iqIOStats.vecInstQueueReads++;
        } else {
            iqIOStats.intInstQueueReads++;
        }

        assert(issuing_inst->seqNum == (*order_it).oldestInst);

        if (issuing_inst->isSquashed()) {
            readyInsts[op_class].pop();

            if (!readyInsts[op_class].empty()) {
                moveToYoungerInst(order_it);
            } else {
                readyIt[op_class] = listOrder.end();
                queueOnList[op_class] = false;
            }

            listOrder.erase(order_it++);

            ++iqStats.squashedInstsIssued;

            continue;
        }

        IQUnit *iq = issuing_inst->iq;
        assert(iq);

        /*
         * Non-squashed entries visible to the legacy ready picker must
         * also exist in their owning IQ's local readiness mirror.
         */
        assert(iq->isReady(issuing_inst));

        int nSkipOffset = -1;

        if (iq->nSkipEnabled()) {
            nSkipOffset = iq->issueWindowOffset(issuing_inst);

            if (nSkipOffset < 0 ||
                nSkipOffset > static_cast<int>(iq->nSkip())) {
                iqStats.nSkipWindowRejects++;
                nSkipRejectedThisCycle = true;
                ++order_it;
                continue;
            }
        }

        int idx = FUPool::NoNeedFU;
        Cycles op_latency = Cycles(1);
        ThreadID tid = issuing_inst->threadNumber;

        auto fu_pool = iq->fuPool();
        if (op_class != No_OpClass) {
            idx = fu_pool->getUnit(op_class, iq->fuRequesterId());
            if (issuing_inst->isFloating()) {
                iqIOStats.fpAluAccesses++;
            } else if (issuing_inst->isVector()) {
                iqIOStats.vecAluAccesses++;
            } else {
                iqIOStats.intAluAccesses++;
            }
            if (idx > FUPool::NoFreeFU) {
                op_latency = fu_pool->getOpLatency(op_class);
            }
        }

        // If we have an instruction that doesn't require a FU, or a
        // valid FU, then schedule for execution.
        if (idx > FUPool::NoFreeFU || idx == FUPool::NoNeedFU ||
            idx == FUPool::NoCapableFU) {
            if (op_latency == Cycles(1)) {
                i2e_info->size++;
                instsToExecute.push_back(issuing_inst);

                // Add the FU onto the list of FU's to be freed next
                // cycle if we used one.
                if (idx >= 0)
                    fu_pool->freeUnitNextCycle(idx);

                // CPU has no capable FU for the instruction
                // but this may be OK if the instruction gets
                // squashed. Remember this and give IEW
                // the opportunity to trigger a fault
                // if the instruction is unsupported.
                // Otherwise, commit will panic.
                if (idx == FUPool::NoCapableFU)
                  issuing_inst->setNoCapableFU();
            } else {
                assert(idx != FUPool::NoCapableFU);
                bool pipelined = fu_pool->isPipelined(op_class);
                // Generate completion event for the FU
                ++wbOutstanding;
                auto execution =
                    new FUCompletion(issuing_inst, fu_pool, idx, this);

                cpu->schedule(execution,
                              cpu->clockEdge(Cycles(op_latency - 1)));

                if (!pipelined) {
                    // If FU isn't pipelined, then it must be freed
                    // upon the execution completing.
                    execution->setFreeFU();
                } else {
                    // Add the FU onto the list of FU's to be freed next cycle.
                    fu_pool->freeUnitNextCycle(idx);
                }
            }

            DPRINTF(IQ, "Thread %i: Issuing instruction PC %s "
                    "[sn:%llu]\n",
                    tid, issuing_inst->pcState(),
                    issuing_inst->seqNum);

            iq->markNotReady(issuing_inst);
            readyInsts[op_class].pop();

            if (!readyInsts[op_class].empty()) {
                moveToYoungerInst(order_it);
            } else {
                readyIt[op_class] = listOrder.end();
                queueOnList[op_class] = false;
            }

            issuing_inst->setIssued();

            if (iq->nSkipEnabled()) {
                assert(nSkipOffset >= 0);
                iqStats.nSkipIssuedOffset.sample(nSkipOffset);

                if (nSkipOffset == 0) {
                    iqStats.nSkipHeadIssued++;
                } else {
                    iqStats.nSkipBypassIssued++;
                }
            }

            ++total_issued;

#if TRACING_ON
            issuing_inst->issueTick = curTick() - issuing_inst->fetchTick;
#endif

            if (issuing_inst->firstIssue == -1)
                issuing_inst->firstIssue = curTick();

            if (!issuing_inst->isMemRef()) {
                // Memory instructions can not be freed from the IQ until they
                // complete.
                issuing_inst->clearInIQ();
            } else {
                memDepUnit[tid].issue(issuing_inst);
            }

            listOrder.erase(order_it++);
            iqStats.issuedInstType[tid][op_class]++;
        } else {
            assert(idx == FUPool::NoFreeFU);
            iqStats.statFuBusy[op_class]++;
            iqStats.fuBusy[tid]++;
            ++order_it;
        }
    }

    if (total_issued == 0 && nSkipRejectedThisCycle) {
        iqStats.nSkipBlockedCycles++;
    }

    iqStats.numIssuedDist.sample(total_issued);
    iqStats.instsIssued+= total_issued;

    // If we issued any instructions, tell the CPU we had activity.
    // @todo If the way deferred memory instructions are handeled due to
    // translation changes then the deferredMemInsts condition should be
    // removed from the code below.
    if (total_issued || !retryMemInsts.empty() || !deferredMemInsts.empty()) {
        cpu->activityThisCycle();
    } else {
        DPRINTF(IQ, "Not able to schedule any instructions.\n");
    }
}

void
InstructionQueue::scheduleNonSpec(const InstSeqNum &inst)
{
    DPRINTF(IQ, "Marking nonspeculative instruction [sn:%llu] as ready "
            "to execute.\n", inst);

    NonSpecMapIt inst_it = nonSpecInsts.find(inst);

    assert(inst_it != nonSpecInsts.end());

    ThreadID tid = (*inst_it).second->threadNumber;

    (*inst_it).second->setAtCommit();

    (*inst_it).second->setCanIssue();

    if (!(*inst_it).second->isMemRef()) {
        addIfReady((*inst_it).second);
    } else {
        memDepUnit[tid].nonSpecInstReady((*inst_it).second);
    }

    (*inst_it).second = NULL;

    nonSpecInsts.erase(inst_it);
}

void
InstructionQueue::commit(const InstSeqNum &inst, ThreadID tid)
{
    DPRINTF(IQ, "[tid:%i] Committing instructions older than [sn:%llu]\n",
            tid,inst);

    ListIt iq_it = instList[tid].begin();

    while (iq_it != instList[tid].end() &&
           (*iq_it)->seqNum <= inst) {
        ++iq_it;
        instList[tid].pop_front();
    }
}

int
InstructionQueue::wakeDependents(const DynInstPtr &completed_inst)
{
    int dependents = 0;

    // The instruction queue here takes care of both floating and int ops
    if (completed_inst->isFloating()) {
        iqIOStats.fpInstQueueWakeupAccesses++;
    } else if (completed_inst->isVector()) {
        iqIOStats.vecInstQueueWakeupAccesses++;
    } else {
        iqIOStats.intInstQueueWakeupAccesses++;
    }

    completed_inst->lastWakeDependents = curTick();

    DPRINTF(IQ, "Waking dependents of completed instruction.\n");

    assert(!completed_inst->isSquashed());

    // Tell the memory dependence unit to wake any dependents on this
    // instruction if it is a memory instruction.  Also complete the memory
    // instruction at this point since we know it executed without issues.
    ThreadID tid = completed_inst->threadNumber;
    if (completed_inst->isMemRef()) {
        memDepUnit[tid].completeInst(completed_inst);

        DPRINTF(IQ, "Completing mem instruction PC: %s [sn:%llu]\n",
            completed_inst->pcState(), completed_inst->seqNum);

        completed_inst->clearInIQ();
        completed_inst->memOpDone(true);
    } else if (completed_inst->isReadBarrier() ||
               completed_inst->isWriteBarrier()) {
        // Completes a non mem ref barrier
        memDepUnit[tid].completeInst(completed_inst);
    }

    for (int dest_reg_idx = 0;
         dest_reg_idx < completed_inst->numDestRegs();
         dest_reg_idx++)
    {
        PhysRegIdPtr dest_reg =
            completed_inst->renamedDestIdx(dest_reg_idx);

        // Special case of uniq or control registers.  They are not
        // handled by the IQ and thus have no dependency graph entry.
        if (dest_reg->isAlwaysReady()) {
            DPRINTF(IQ, "Reg %d [%s] is part of a fix mapping, skipping\n",
                    dest_reg->index(), dest_reg->className());
            continue;
        }

        // Avoid waking up dependents if the register is pinned
        dest_reg->decrNumPinnedWritesToComplete();
        if (dest_reg->isPinned())
            completed_inst->setPinnedRegsWritten();

        if (dest_reg->getNumPinnedWritesToComplete() != 0) {
            DPRINTF(IQ, "Reg %d [%s] is pinned, skipping\n",
                    dest_reg->index(), dest_reg->className());
            continue;
        }

        DPRINTF(IQ, "Waking any dependents on register %i (%s).\n",
                dest_reg->index(),
                dest_reg->className());

        //Go through the dependency chain, marking the registers as
        //ready within the waiting instructions.
        DynInstPtr dep_inst = dependGraph.pop(dest_reg->flatIndex());

        while (dep_inst) {
            DPRINTF(IQ, "Waking up a dependent instruction, [sn:%llu] "
                    "PC %s.\n", dep_inst->seqNum, dep_inst->pcState());

            // Might want to give more information to the instruction
            // so that it knows which of its source registers is
            // ready.  However that would mean that the dependency
            // graph entries would need to hold the src_reg_idx.
            dep_inst->markSrcRegReady();

            addIfReady(dep_inst);

            dep_inst = dependGraph.pop(dest_reg->flatIndex());

            ++dependents;
        }

        // Reset the head node now that all of its dependents have
        // been woken up.
        assert(dependGraph.empty(dest_reg->flatIndex()));
        dependGraph.clearInst(dest_reg->flatIndex());

        // Mark the scoreboard as having that register ready.
        regScoreboard[dest_reg->flatIndex()] = true;
    }
    return dependents;
}

void
InstructionQueue::addReadyMemInst(const DynInstPtr &ready_inst)
{
    OpClass op_class = ready_inst->opClass();

    assert(op_class < Num_OpClasses);

    /*
     * Memory instructions may remain in the deferred/cache-retry lists
     * across a squash.  Squash removes them from their physical IQ and
     * therefore clears DynInst::iq.
     *
     * The legacy global ready path deliberately tolerates this: a
     * squashed entry may be re-added to readyInsts and is discarded by
     * scheduleReadyInsts() before its IQ owner is dereferenced.
     *
     * The per-IQ readiness mirror must therefore only be updated for
     * live, non-squashed instructions.
     */
    if (ready_inst->isSquashed()) {
        if (useLocalIQPicker) {
            ++iqStats.squashedInstsIssued;
            return;
        }
    } else {
        assert(ready_inst->iq);
        ready_inst->iq->markReady(ready_inst);
    }

    if (useLocalIQPicker) {
        DPRINTF(IQ, "Memory instruction is locally ready to issue, "
                "PC %s opclass:%i [sn:%llu].\n",
                ready_inst->pcState(), op_class, ready_inst->seqNum);
        return;
    }

    readyInsts[op_class].push(ready_inst);

    // Will need to reorder the list if either a queue is not on the list,
    // or it has an older instruction than last time.
    if (!queueOnList[op_class]) {
        addToOrderList(op_class);
    } else if (readyInsts[op_class].top()->seqNum  <
               (*readyIt[op_class]).oldestInst) {
        listOrder.erase(readyIt[op_class]);
        addToOrderList(op_class);
    }

    DPRINTF(IQ, "Instruction is ready to issue, putting it onto "
            "the ready list, PC %s opclass:%i [sn:%llu].\n",
            ready_inst->pcState(), op_class, ready_inst->seqNum);
}

void
InstructionQueue::rescheduleMemInst(const DynInstPtr &resched_inst)
{
    DPRINTF(IQ, "Rescheduling mem inst [sn:%llu]\n", resched_inst->seqNum);

    // Reset DTB translation state
    resched_inst->translationStarted(false);
    resched_inst->translationCompleted(false);

    resched_inst->clearCanIssue();
    memDepUnit[resched_inst->threadNumber].reschedule(resched_inst);
}

void
InstructionQueue::replayMemInst(const DynInstPtr &replay_inst)
{
    memDepUnit[replay_inst->threadNumber].replay();
}

void
InstructionQueue::deferMemInst(const DynInstPtr &deferred_inst)
{
    deferredMemInsts.push_back(deferred_inst);
}

void
InstructionQueue::blockMemInst(const DynInstPtr &blocked_inst)
{
    blocked_inst->clearIssued();
    blocked_inst->clearCanIssue();
    blockedMemInsts.push_back(blocked_inst);
    DPRINTF(IQ, "Memory inst [sn:%llu] PC %s is blocked, will be "
            "reissued later\n", blocked_inst->seqNum,
            blocked_inst->pcState());
}

void
InstructionQueue::retryMemInst(const DynInstPtr &retry_inst)
{
    retryMemInsts.push_back(retry_inst);
}

void
InstructionQueue::cacheUnblocked()
{
    DPRINTF(IQ, "Cache is unblocked, rescheduling blocked memory "
            "instructions\n");
    retryMemInsts.splice(retryMemInsts.end(), blockedMemInsts);
    // Get the CPU ticking again
    cpu->wakeCPU();
}

DynInstPtr
InstructionQueue::getDeferredMemInstToExecute()
{
    for (ListIt it = deferredMemInsts.begin(); it != deferredMemInsts.end();
         ++it) {
        if ((*it)->translationCompleted() || (*it)->isSquashed()) {
            DynInstPtr mem_inst = std::move(*it);
            deferredMemInsts.erase(it);
            return mem_inst;
        }
    }
    return nullptr;
}

DynInstPtr
InstructionQueue::getBlockedMemInstToExecute()
{
    if (retryMemInsts.empty()) {
        return nullptr;
    } else {
        DynInstPtr mem_inst = std::move(retryMemInsts.front());
        retryMemInsts.pop_front();
        return mem_inst;
    }
}

void
InstructionQueue::violation(const DynInstPtr &store,
        const DynInstPtr &faulting_load)
{
    iqIOStats.intInstQueueWrites++;
    memDepUnit[store->threadNumber].violation(store, faulting_load);
}

unsigned
InstructionQueue::getCount(ThreadID tid) const
{
    unsigned count = 0;
    for (auto iq : iqs) {
        count += iq->getCount(tid);
    }
    return count;
}

void
InstructionQueue::squash(ThreadID tid)
{
    DPRINTF(IQ, "[tid:%i] Starting to squash instructions in "
            "the IQ.\n", tid);

    // Read instruction sequence number of last instruction out of the
    // time buffer.
    squashedSeqNum[tid] = fromCommit->commitInfo[tid].doneSeqNum;

    doSquash(tid);

    // Also tell the memory dependence unit to squash.
    memDepUnit[tid].squash(squashedSeqNum[tid], tid);
}

void
InstructionQueue::doSquash(ThreadID tid)
{
    // Start at the tail.
    ListIt squash_it = instList[tid].end();
    --squash_it;

    DPRINTF(IQ, "[tid:%i] Squashing until sequence number %i!\n",
            tid, squashedSeqNum[tid]);

    // Squash any instructions younger than the squashed sequence number
    // given.
    while (squash_it != instList[tid].end() &&
           (*squash_it)->seqNum > squashedSeqNum[tid]) {

        DynInstPtr squashed_inst = (*squash_it);
        if (squashed_inst->isFloating()) {
            iqIOStats.fpInstQueueWrites++;
        } else if (squashed_inst->isVector()) {
            iqIOStats.vecInstQueueWrites++;
        } else {
            iqIOStats.intInstQueueWrites++;
        }

        // Only handle the instruction if it actually is in the IQ and
        // hasn't already been squashed in the IQ.
        if (squashed_inst->threadNumber != tid ||
            squashed_inst->isSquashedInIQ()) {
            --squash_it;
            continue;
        }

        if (!squashed_inst->isIssued() ||
            (squashed_inst->isMemRef() &&
             !squashed_inst->memOpDone())) {

            DPRINTF(IQ, "[tid:%i] Instruction [sn:%llu] PC %s squashed.\n",
                    tid, squashed_inst->seqNum, squashed_inst->pcState());

            bool is_acq_rel = squashed_inst->isFullMemBarrier() &&
                         (squashed_inst->isLoad() ||
                          (squashed_inst->isStore() &&
                             !squashed_inst->isStoreConditional()));

            // Remove the instruction from the dependency list.
            if (is_acq_rel ||
                (!squashed_inst->isNonSpeculative() &&
                 !squashed_inst->isStoreConditional() &&
                 !squashed_inst->isAtomic() &&
                 !squashed_inst->isReadBarrier() &&
                 !squashed_inst->isWriteBarrier())) {

                for (int src_reg_idx = 0;
                     src_reg_idx < squashed_inst->numSrcRegs();
                     src_reg_idx++)
                {
                    PhysRegIdPtr src_reg =
                        squashed_inst->renamedSrcIdx(src_reg_idx);

                    // Only remove it from the dependency graph if it
                    // was placed there in the first place.

                    // Instead of doing a linked list traversal, we
                    // can just remove these squashed instructions
                    // either at issue time, or when the register is
                    // overwritten.  The only downside to this is it
                    // leaves more room for error.

                    if (!squashed_inst->readySrcIdx(src_reg_idx) &&
                        !src_reg->isAlwaysReady()) {
                        dependGraph.remove(src_reg->flatIndex(),
                                           squashed_inst);
                    }

                    ++iqStats.squashedOperandsExamined;
                }

            } else if (!squashed_inst->isStoreConditional() ||
                       !squashed_inst->isCompleted()) {
                NonSpecMapIt ns_inst_it =
                    nonSpecInsts.find(squashed_inst->seqNum);

                // we remove non-speculative instructions from
                // nonSpecInsts already when they are ready, and so we
                // cannot always expect to find them
                if (ns_inst_it == nonSpecInsts.end()) {
                    // loads that became ready but stalled on a
                    // blocked cache are alreayd removed from
                    // nonSpecInsts, and have not faulted
                    assert(squashed_inst->getFault() != NoFault ||
                           squashed_inst->isMemRef());
                } else {

                    (*ns_inst_it).second = NULL;

                    nonSpecInsts.erase(ns_inst_it);

                    ++iqStats.squashedNonSpecRemoved;
                }
            }

            // Might want to also clear out the head of the dependency graph.

            // Mark it as squashed within the IQ.
            squashed_inst->setSquashedInIQ();

            // @todo: Remove this hack where several statuses are set so the
            // inst will flow through the rest of the pipeline.
            squashed_inst->setIssued();
            squashed_inst->setCanCommit();
            squashed_inst->clearInIQ();
        }

        // IQ clears out the heads of the dependency graph only when
        // instructions reach writeback stage. If an instruction is squashed
        // before writeback stage, its head of dependency graph would not be
        // cleared out; it holds the instruction's DynInstPtr. This
        // prevents freeing the squashed instruction's DynInst.
        // Thus, we need to manually clear out the squashed instructions'
        // heads of dependency graph.
        for (int dest_reg_idx = 0;
             dest_reg_idx < squashed_inst->numDestRegs();
             dest_reg_idx++)
        {
            PhysRegIdPtr dest_reg =
                squashed_inst->renamedDestIdx(dest_reg_idx);
            if (dest_reg->isAlwaysReady()) {
                continue;
            }
            assert(dependGraph.empty(dest_reg->flatIndex()));
            dependGraph.clearInst(dest_reg->flatIndex());
        }
        instList[tid].erase(squash_it--);
        ++iqStats.squashedInstsExamined;
    }
}

bool
InstructionQueue::PqCompare::operator()(
        const DynInstPtr &lhs, const DynInstPtr &rhs) const
{
    return lhs->seqNum > rhs->seqNum;
}

bool
InstructionQueue::addToDependents(const DynInstPtr &new_inst)
{
    // Loop through the instruction's source registers, adding
    // them to the dependency list if they are not ready.
    int8_t total_src_regs = new_inst->numSrcRegs();
    bool return_val = false;

    for (int src_reg_idx = 0;
         src_reg_idx < total_src_regs;
         src_reg_idx++)
    {
        // Only add it to the dependency graph if it's not ready.
        if (!new_inst->readySrcIdx(src_reg_idx)) {
            PhysRegIdPtr src_reg = new_inst->renamedSrcIdx(src_reg_idx);

            // Check the IQ's scoreboard to make sure the register
            // hasn't become ready while the instruction was in flight
            // between stages.  Only if it really isn't ready should
            // it be added to the dependency graph.
            if (src_reg->isAlwaysReady()) {
                continue;
            } else if (!regScoreboard[src_reg->flatIndex()]) {
                DPRINTF(IQ, "Instruction PC %s has src reg %i (%s) that "
                        "is being added to the dependency chain.\n",
                        new_inst->pcState(), src_reg->index(),
                        src_reg->className());

                dependGraph.insert(src_reg->flatIndex(), new_inst);

                // Change the return value to indicate that something
                // was added to the dependency graph.
                return_val = true;
            } else {
                DPRINTF(IQ, "Instruction PC %s has src reg %i (%s) that "
                        "became ready before it reached the IQ.\n",
                        new_inst->pcState(), src_reg->index(),
                        src_reg->className());
                // Mark a register ready within the instruction.
                new_inst->markSrcRegReady(src_reg_idx);
            }
        }
    }

    return return_val;
}

void
InstructionQueue::addToProducers(const DynInstPtr &new_inst)
{
    // Nothing really needs to be marked when an instruction becomes
    // the producer of a register's value, but for convenience a ptr
    // to the producing instruction will be placed in the head node of
    // the dependency links.
    int8_t total_dest_regs = new_inst->numDestRegs();

    for (int dest_reg_idx = 0;
         dest_reg_idx < total_dest_regs;
         dest_reg_idx++)
    {
        PhysRegIdPtr dest_reg = new_inst->renamedDestIdx(dest_reg_idx);

        // Some registers have fixed mapping, and there is no need to track
        // dependencies as these instructions must be executed at commit.
        if (dest_reg->isAlwaysReady()) {
            continue;
        }

        if (!dependGraph.empty(dest_reg->flatIndex())) {
            dependGraph.dump();
            panic("Dependency graph %i (%s) (flat: %i) not empty!",
                  dest_reg->index(), dest_reg->className(),
                  dest_reg->flatIndex());
        }

        dependGraph.setInst(dest_reg->flatIndex(), new_inst);

        // Mark the scoreboard to say it's not yet ready.
        regScoreboard[dest_reg->flatIndex()] = false;
    }
}

void
InstructionQueue::addIfReady(const DynInstPtr &inst)
{
    // If the instruction now has all of its source registers
    // available, then add it to the list of ready instructions.
    if (inst->readyToIssue()) {

        //Add the instruction to the proper ready list.
        if (inst->isMemRef()) {

            DPRINTF(IQ, "Checking if memory instruction can issue.\n");

            // Message to the mem dependence unit that this instruction has
            // its registers ready.
            memDepUnit[inst->threadNumber].regsReady(inst);

            return;
        }

        OpClass op_class = inst->opClass();

        assert(op_class < Num_OpClasses);
        assert(inst->iq);

        inst->iq->markReady(inst);

        if (useLocalIQPicker) {
            DPRINTF(IQ, "Instruction is locally ready to issue, "
                    "PC %s opclass:%i [sn:%llu].\n",
                    inst->pcState(), op_class, inst->seqNum);
            return;
        }

        DPRINTF(IQ, "Instruction is ready to issue, putting it onto "
                "the ready list, PC %s opclass:%i [sn:%llu].\n",
                inst->pcState(), op_class, inst->seqNum);

        readyInsts[op_class].push(inst);

        // Will need to reorder the list if either a queue is not on the list,
        // or it has an older instruction than last time.
        if (!queueOnList[op_class]) {
            addToOrderList(op_class);
        } else if (readyInsts[op_class].top()->seqNum  <
                   (*readyIt[op_class]).oldestInst) {
            listOrder.erase(readyIt[op_class]);
            addToOrderList(op_class);
        }
    }
}

void
InstructionQueue::dumpLists()
{
    for (int i = 0; i < Num_OpClasses; ++i) {
        cprintf("Ready list %i size: %i\n", i, readyInsts[i].size());

        cprintf("\n");
    }

    cprintf("Non speculative list size: %i\n", nonSpecInsts.size());

    NonSpecMapIt non_spec_it = nonSpecInsts.begin();
    NonSpecMapIt non_spec_end_it = nonSpecInsts.end();

    cprintf("Non speculative list: ");

    while (non_spec_it != non_spec_end_it) {
        cprintf("%s [sn:%llu]", (*non_spec_it).second->pcState(),
                (*non_spec_it).second->seqNum);
        ++non_spec_it;
    }

    cprintf("\n");

    ListOrderIt list_order_it = listOrder.begin();
    ListOrderIt list_order_end_it = listOrder.end();
    int i = 1;

    cprintf("List order: ");

    while (list_order_it != list_order_end_it) {
        cprintf("%i OpClass:%i [sn:%llu] ", i, (*list_order_it).queueType,
                (*list_order_it).oldestInst);

        ++list_order_it;
        ++i;
    }

    cprintf("\n");
}


void
InstructionQueue::dumpInsts()
{
    for (ThreadID tid = 0; tid < numThreads; ++tid) {
        int num = 0;
        int valid_num = 0;
        ListIt inst_list_it = instList[tid].begin();

        while (inst_list_it != instList[tid].end()) {
            cprintf("Instruction:%i\n", num);
            if (!(*inst_list_it)->isSquashed()) {
                if (!(*inst_list_it)->isIssued()) {
                    ++valid_num;
                    cprintf("Count:%i\n", valid_num);
                } else if ((*inst_list_it)->isMemRef() &&
                           !(*inst_list_it)->memOpDone()) {
                    // Loads that have not been marked as executed
                    // still count towards the total instructions.
                    ++valid_num;
                    cprintf("Count:%i\n", valid_num);
                }
            }

            cprintf("PC: %s\n[sn:%llu]\n[tid:%i]\n"
                    "Issued:%i\nSquashed:%i\n",
                    (*inst_list_it)->pcState(),
                    (*inst_list_it)->seqNum,
                    (*inst_list_it)->threadNumber,
                    (*inst_list_it)->isIssued(),
                    (*inst_list_it)->isSquashed());

            if ((*inst_list_it)->isMemRef()) {
                cprintf("MemOpDone:%i\n", (*inst_list_it)->memOpDone());
            }

            cprintf("\n");

            inst_list_it++;
            ++num;
        }
    }

    cprintf("Insts to Execute list:\n");

    int num = 0;
    int valid_num = 0;
    ListIt inst_list_it = instsToExecute.begin();

    while (inst_list_it != instsToExecute.end())
    {
        cprintf("Instruction:%i\n",
                num);
        if (!(*inst_list_it)->isSquashed()) {
            if (!(*inst_list_it)->isIssued()) {
                ++valid_num;
                cprintf("Count:%i\n", valid_num);
            } else if ((*inst_list_it)->isMemRef() &&
                       !(*inst_list_it)->memOpDone()) {
                // Loads that have not been marked as executed
                // still count towards the total instructions.
                ++valid_num;
                cprintf("Count:%i\n", valid_num);
            }
        }

        cprintf("PC: %s\n[sn:%llu]\n[tid:%i]\n"
                "Issued:%i\nSquashed:%i\n",
                (*inst_list_it)->pcState(),
                (*inst_list_it)->seqNum,
                (*inst_list_it)->threadNumber,
                (*inst_list_it)->isIssued(),
                (*inst_list_it)->isSquashed());

        if ((*inst_list_it)->isMemRef()) {
            cprintf("MemOpDone:%i\n", (*inst_list_it)->memOpDone());
        }

        cprintf("\n");

        inst_list_it++;
        ++num;
    }
}

} // namespace o3
} // namespace gem5
