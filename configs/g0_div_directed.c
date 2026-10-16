/*
 * Little v0.52 G0-A directed DIV workload.
 * Compile twice: -DG0_DIV_EVERY=1 (sustained), or =16 (sparse).
 * No global m5 reset/dump: both SE cores must not reset each other's ROI.
 * Every completed process prints a deterministic, comparable checksum.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#ifndef G0_DIV_EVERY
#define G0_DIV_EVERY 1
#endif
#ifndef G0_ITERATIONS
#define G0_ITERATIONS 3072
#endif
#if G0_DIV_EVERY <= 0
#error G0_DIV_EVERY must be positive
#endif
static volatile uint64_t initial_value = UINT64_C(0x123456789abcdef1);
int main(void)
{
    uint64_t x = initial_value;
    uint64_t checksum = UINT64_C(0x97f4a7c159e3779b);
    uint64_t div_ops = 0;
    for (unsigned i = 0; i < G0_ITERATIONS; ++i) {
        x ^= (x << 7);
        x ^= (x >> 9);
        x += UINT64_C(0x9e3779b97f4a7c15) + i;
        if (i % G0_DIV_EVERY == 0) {
            uint64_t numerator = x | (UINT64_C(1) << 55);
            uint64_t denominator = ((x >> 17) & 0x7fffU) | 1U;
            uint64_t quotient = numerator / denominator;
            uint64_t remainder = numerator % denominator;
            checksum ^= quotient + (remainder << 1) + i;
            checksum = (checksum << 11) | (checksum >> 53);
            div_ops += 2; /* dynamic DIVU and REMU expected; inspect objdump */
        } else {
            checksum ^= (x * UINT64_C(0x100000001b3)) + i;
            checksum = (checksum << 11) | (checksum >> 53);
        }
    }
    printf("G0_RESULT every=%d iterations=%d div_ops_expected=%" PRIu64
           " checksum=%016" PRIx64 "\n",
           G0_DIV_EVERY, G0_ITERATIONS, div_ops, checksum);
    fflush(stdout);
    return 0;
}
