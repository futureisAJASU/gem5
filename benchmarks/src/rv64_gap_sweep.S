#ifndef GAP
#define GAP 0
#endif

    .section .text
    .align 4
    .globl _start
    .type _start, @function

_start:
    li      s0, 200000
    li      s1, 0x123456789abcdef0
    li      s2, 3

    li      s3, 11
    li      s4, 13
    li      s5, 17
    li      s6, 19
    li      s7, 23
    li      s8, 29

    li      s9, 0x9e3779b97f4a7c15

    .align 4
1:
    /*
     * Long-latency serial producer. DIVU maps to IntDivOp in gem5.
     * s1 feeds the next iteration, preserving a serial divider chain.
     */
    divu    s1, s1, s2

    /*
     * GAP younger consumers blocked on the unresolved divide result.
     */
#if GAP >= 1
    addi    t0, s1, 1
#endif
#if GAP >= 2
    addi    t1, s1, 2
#endif
#if GAP >= 3
    addi    t2, s1, 3
#endif
#if GAP >= 4
    addi    t3, s1, 4
#endif
#if GAP >= 5
    addi    t4, s1, 5
#endif
#if GAP >= 6
    addi    t5, s1, 6
#endif
#if GAP >= 7
    addi    t6, s1, 7
#endif
#if GAP >= 8
    addi    a1, s1, 8
#endif

    /*
     * Younger independent work. Bounded N-SKIP may expose these while
     * the divide and its dependent consumers remain unresolved.
     */
    addi    s3, s3, 1
    addi    s4, s4, 3
    addi    s5, s5, 5
    addi    s6, s6, 7
    addi    s7, s7, 9
    addi    s8, s8, 11

    add     s1, s1, s9

    addi    s0, s0, -1
    bnez    s0, 1b

    /*
     * Architectural self-check. All N-SKIP policies must preserve this
     * exact result; a mismatch exits with status 1.
     */
    xor     a0, s1, s3
    xor     a0, a0, s4
    xor     a0, a0, s5
    xor     a0, a0, s6
    xor     a0, a0, s7
    xor     a0, a0, s8

    li      t0, 0xed5336963ec56891
    bne     a0, t0, 2f

    li      a0, 0
    j       3f

2:
    li      a0, 1

3:
    li      a7, 93
    ecall

    .size _start, .-_start
