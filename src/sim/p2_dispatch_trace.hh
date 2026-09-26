#ifndef __SIM_P2_DISPATCH_TRACE_HH__
#define __SIM_P2_DISPATCH_TRACE_HH__

#include <cstdlib>

#include "base/logging.hh"
#include "base/types.hh"

namespace gem5
{
namespace p2_dispatch_trace
{

inline bool roi_active = false;
inline bool roi_started = false;
inline bool roi_closed = false;

inline bool
configured()
{
    static const bool value = []() {
        const char *p = std::getenv("LITTLE_P2_DISPATCH_TRACE");
        return p && p[0] != '\0';
    }();
    return value;
}

inline bool
active()
{
    return configured() && roi_active;
}

inline void
begin(Tick tick)
{
    if (!configured())
        return;
    if (roi_active)
        fatal("P2 dispatch trace saw nested resetstats ROI begin\n");
    if (roi_closed)
        fatal("P2 dispatch trace saw a second ROI after the first ROI closed\n");
    roi_active = true;
    roi_started = true;
    inform("P2_DISPATCH_TRACE_ROI_BEGIN tick=%llu\n",
           static_cast<unsigned long long>(tick));
}

inline void
end(Tick tick)
{
    if (!configured())
        return;
    if (!roi_active || !roi_started)
        fatal("P2 dispatch trace saw dumpstats without active ROI\n");
    roi_active = false;
    roi_closed = true;
    inform("P2_DISPATCH_TRACE_ROI_END tick=%llu\n",
           static_cast<unsigned long long>(tick));
}

} // namespace p2_dispatch_trace
} // namespace gem5

#endif // __SIM_P2_DISPATCH_TRACE_HH__
