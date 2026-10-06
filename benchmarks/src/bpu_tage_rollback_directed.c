#include <gem5/m5ops.h>
#include <stdint.h>

static volatile uint64_t sink = 1;

__attribute__((noinline, noclone))
static uint64_t
branch_kernel(uint64_t seed, uint64_t iters)
{
    uint64_t x = seed | 1ULL;
    uint64_t acc = 0x9e3779b97f4a7c15ULL;

    for (uint64_t i = 0; i < iters; ++i) {
        // xorshift-like state: deterministic but difficult enough to create
        // repeated direction changes and mispredictions.
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;

        if (x & 1ULL) {
            acc += x ^ i;
        } else {
            acc ^= x + i;
        }

        if ((((x >> 5) ^ i) & 3ULL) == 0) {
            acc += (x >> 11);
        } else {
            acc -= (i | 1ULL);
        }

        if ((i & 7ULL) == 3ULL) {
            acc ^= (x << 1);
        }

        if (((x >> 17) & 7ULL) < ((i >> 2) & 7ULL)) {
            acc += 0x100000001b3ULL;
        } else {
            acc ^= 0xcbf29ce484222325ULL;
        }

        // Cross-correlated condition uses state produced by prior branches.
        if (((acc ^ x ^ (i << 3)) & 0x20ULL) != 0) {
            x += 0x27d4eb2f165667c5ULL;
        } else {
            x ^= 0x94d049bb133111ebULL;
        }
    }

    sink ^= acc ^ x;
    return acc ^ x;
}

int
main(void)
{
    // Warm the process/runtime before the measured interval.
    branch_kernel(0x123456789abcdefULL, 2000);

    m5_reset_stats(0, 0);
    uint64_t result = branch_kernel(0x3141592653589793ULL, 120000);
    m5_dump_stats(0, 0);

    sink ^= result;
    return (sink == 0xdeadbeefULL) ? 1 : 0;
}
