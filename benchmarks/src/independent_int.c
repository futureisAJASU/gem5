#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

volatile uint64_t sink;

int main(void)
{
    uint64_t a = 1;
    uint64_t b = 3;
    uint64_t c = 5;
    uint64_t d = 7;
    uint64_t e = 11;
    uint64_t f = 13;

    /*
     * Multiple independent arithmetic chains. The volatile sink prevents
     * the compiler from deleting the loop while keeping the hot loop simple.
     */
    for (uint64_t i = 0; i < 10000000ULL; ++i) {
        a = a + 0x9e3779b97f4a7c15ULL;
        b = b ^ (b << 7);
        c = c + (c >> 3) + 17;
        d = d * 5 + 1;
        e = (e << 11) | (e >> 53);
        f = f + i + 23;
    }

    sink = a ^ b ^ c ^ d ^ e ^ f;
    printf("%" PRIu64 "\n", sink);
    return 0;
}
