    .section .text
    .align 4
    .globl _start
    .type _start, @function

_start:
    li      s0, 64
    li      s2, 0x123456789abcdef0
    li      s3, 3
    li      s4, 5
    li      s5, 7
    li      s6, 11
    li      s7, 13
    li      s8, 17
    li      s9, 19
    li      s10, 23

    .align 4
1:
    /*
     * A 20-cycle IntDiv producer makes seven younger IntMult operations
     * simultaneously ready after they have accumulated in INT0.  INT0 has
     * seven valid/unissued operations when the dependency resolves, while N4
     * exposes only the first five in round zero.  With two multiplier units,
     * the first successful issue must cause the source-model picker to
     * re-evaluate and expose the previous sixth position in round one.
     */
    divu    s1, s2, s3

    mul     t0, s1, s4
    mul     t1, s1, s5
    mul     t2, s1, s6
    mul     t3, s1, s7
    mul     t4, s1, s8
    mul     t5, s1, s9
    mul     t6, s1, s10

    /* Keep all multiply results architecturally live and seed next round. */
    xor     s2, t0, t1
    xor     s2, s2, t2
    xor     s2, s2, t3
    xor     s2, s2, t4
    xor     s2, s2, t5
    xor     s2, s2, t6
    ori     s2, s2, 1

    addi    s0, s0, -1
    bnez    s0, 1b

    li      a0, 0
    li      a7, 93
    ecall

    .size _start, .-_start
