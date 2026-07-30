#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

volatile uint64_t sink;

__attribute__((noinline))
static uint64_t
dependency_chain(uint64_t x, uint64_t iterations)
{
    for (uint64_t i = 0; i < iterations; ++i) {
        /*
         * Every operation depends on the preceding result.
         * The compiler barrier prevents algebraic collapsing or
         * recurrence substitution across loop iterations.
         */
        x += UINT64_C(0x9e3779b97f4a7c15);
        x ^= x >> 17;
        x = (x << 13) | (x >> 51);
        x *= UINT64_C(0xbf58476d1ce4e5b9);

        __asm__ volatile("" : "+r"(x));
    }

    return x;
}

int
main(void)
{
    sink = dependency_chain(UINT64_C(0x123456789abcdef0), 5000000ULL);
    printf("%" PRIu64 "\n", sink);
    return 0;
}
