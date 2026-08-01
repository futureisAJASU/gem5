#ifndef GAP
#define GAP 0
#endif

    .text
    .align  2
    .global gap_sweep_run
    .type   gap_sweep_run, %function

gap_sweep_run:
    stp     x29, x30, [sp, #-16]!
    mov     x29, sp
    stp     x19, x20, [sp, #-16]!
    stp     x21, x22, [sp, #-16]!
    stp     x23, x24, [sp, #-16]!
    stp     x25, x26, [sp, #-16]!
    stp     x27, x28, [sp, #-16]!

    mov     x19, x0
    ldr     x20, =0x123456789abcdef0
    mov     x21, #3

    mov     x22, #11
    mov     x23, #13
    mov     x24, #17
    mov     x25, #19
    mov     x26, #23
    mov     x27, #29

    ldr     x28, =0x9e3779b97f4a7c15

    cbz     x19, .Ldone

    .align  4
.Lloop:
    /*
     * Long-latency producer. Because x20 feeds the next iteration,
     * producer execution is serial across loop iterations.
     */
    udiv    x20, x20, x21

    /*
     * GAP blocked consumers. Every instruction below depends directly
     * on the unresolved divide result.
     */
#if GAP >= 1
    add     x9,  x20, #1
#endif
#if GAP >= 2
    add     x10, x20, #2
#endif
#if GAP >= 3
    add     x11, x20, #3
#endif
#if GAP >= 4
    add     x12, x20, #4
#endif
#if GAP >= 5
    add     x13, x20, #5
#endif
#if GAP >= 6
    add     x14, x20, #6
#endif
#if GAP >= 7
    add     x15, x20, #7
#endif
#if GAP >= 8
    add     x16, x20, #8
#endif

    /*
     * Younger independent work. N-SKIP may expose these while UDIV and
     * its blocked consumers are still waiting.
     */
    add     x22, x22, #1
    add     x23, x23, #3
    add     x24, x24, #5
    add     x25, x25, #7
    add     x26, x26, #9
    add     x27, x27, #11

    /*
     * Keep the serial producer state nonzero and varying.
     */
    add     x20, x20, x28

    subs    x19, x19, #1
    b.ne    .Lloop

.Ldone:
    eor     x0, x20, x22
    eor     x0, x0,  x23
    eor     x0, x0,  x24
    eor     x0, x0,  x25
    eor     x0, x0,  x26
    eor     x0, x0,  x27

    ldp     x27, x28, [sp], #16
    ldp     x25, x26, [sp], #16
    ldp     x23, x24, [sp], #16
    ldp     x21, x22, [sp], #16
    ldp     x19, x20, [sp], #16
    ldp     x29, x30, [sp], #16
    ret

    .size gap_sweep_run, .-gap_sweep_run
    .section .note.GNU-stack,"",%progbits
