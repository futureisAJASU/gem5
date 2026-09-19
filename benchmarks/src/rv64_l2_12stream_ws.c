#include <stdint.h>

#ifndef WS_LINES
#define WS_LINES 1024
#endif

#if (WS_LINES != 128) && (WS_LINES != 1024) && (WS_LINES != 2048)
#error "WS_LINES must be one of 128, 1024, 2048"
#endif

#define STREAMS 12
#define LINE_WORDS 8
#define STEPS 131072u

/*
 * Directed cache-working-set stressor for R5.
 * Each stream contributes one 64-byte line per logical index.
 *
 * Approximate active footprint:
 *   WS_LINES=128  -> 12 * 128  * 64 B =   96 KiB
 *   WS_LINES=1024 -> 12 * 1024 * 64 B =  768 KiB
 *   WS_LINES=2048 -> 12 * 2048 * 64 B = 1536 KiB
 *
 * The array is BSS-backed and deliberately volatile. All variants execute
 * the same STEPS x STREAMS demand-load body; only the address working set
 * changes. No source-level stores are used in the measured body.
 */
static volatile uint64_t arena[STREAMS][WS_LINES][LINE_WORDS]
    __attribute__((aligned(64)));

int
main(void)
{
    uint64_t sum = 0;

    for (uint32_t t = 0; t < STEPS; ++t) {
        const uint32_t idx = (t * 17u) & (WS_LINES - 1u);

        for (uint32_t s = 0; s < STREAMS; ++s) {
            sum += arena[s][idx][0];
        }
    }

    __asm__ __volatile__("" : "+r"(sum) :: "memory");

    /* BSS is zero-filled; non-zero indicates corrupted architectural state. */
    return sum != 0;
}
