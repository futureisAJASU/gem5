/* BPU-7 C3 P3; acceptance-only G1 veto. NOT real frontend M1. */
#ifndef __CPU_PRED_LITTLE_C3_STRONG5_VETO_HH__
#define __CPU_PRED_LITTLE_C3_STRONG5_VETO_HH__
namespace gem5 { namespace branch_prediction {
inline bool
c3G1Strong5Veto(bool enabled, bool proposed, bool providerStrong,
                unsigned providerStrength)
{
    return enabled && proposed && providerStrong && providerStrength == 5;
}
} }
#endif
