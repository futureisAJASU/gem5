#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

#ifndef GAP
#define GAP 0
#endif

extern uint64_t gap_sweep_run(uint64_t iterations);

int
main(void)
{
    const uint64_t iterations = UINT64_C(200000);
    const uint64_t checksum = gap_sweep_run(iterations);

    printf(
        "gap=%d iterations=%" PRIu64 " checksum=%" PRIu64 "\n",
        GAP,
        iterations,
        checksum
    );

    return 0;
}
