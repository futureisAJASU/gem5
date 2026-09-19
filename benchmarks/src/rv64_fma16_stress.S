/*
 * Directed RV64 scalar-FMA stress for pair-shared FP validation.
 *
 * Per core:
 *   8192 iterations x 16 independent FMADD.D = 131072 FMAs
 * Two identical cores:
 *   262144 FMAs total
 *
 * All operands are +0.0. Sixteen independent accumulator chains hide the
 * modeled 5-cycle FloatMultAcc latency without changing the final value.
 * The final zero check makes the workload self-checking.
 */

    .section .text
    .globl _start
    .type _start, @function

_start:
    li      t0, 8192

    fmv.d.x f30, zero
    fmv.d.x f31, zero

    fmv.d.x f0, zero
    fmv.d.x f1, zero
    fmv.d.x f2, zero
    fmv.d.x f3, zero
    fmv.d.x f4, zero
    fmv.d.x f5, zero
    fmv.d.x f6, zero
    fmv.d.x f7, zero
    fmv.d.x f8, zero
    fmv.d.x f9, zero
    fmv.d.x f10, zero
    fmv.d.x f11, zero
    fmv.d.x f12, zero
    fmv.d.x f13, zero
    fmv.d.x f14, zero
    fmv.d.x f15, zero

1:
    fmadd.d f0,  f30, f31, f0
    fmadd.d f1,  f30, f31, f1
    fmadd.d f2,  f30, f31, f2
    fmadd.d f3,  f30, f31, f3
    fmadd.d f4,  f30, f31, f4
    fmadd.d f5,  f30, f31, f5
    fmadd.d f6,  f30, f31, f6
    fmadd.d f7,  f30, f31, f7
    fmadd.d f8,  f30, f31, f8
    fmadd.d f9,  f30, f31, f9
    fmadd.d f10, f30, f31, f10
    fmadd.d f11, f30, f31, f11
    fmadd.d f12, f30, f31, f12
    fmadd.d f13, f30, f31, f13
    fmadd.d f14, f30, f31, f14
    fmadd.d f15, f30, f31, f15

    addi    t0, t0, -1
    bnez    t0, 1b

    li      t1, 0
    fmv.x.d t2, f0
    or      t1, t1, t2
    fmv.x.d t2, f1
    or      t1, t1, t2
    fmv.x.d t2, f2
    or      t1, t1, t2
    fmv.x.d t2, f3
    or      t1, t1, t2
    fmv.x.d t2, f4
    or      t1, t1, t2
    fmv.x.d t2, f5
    or      t1, t1, t2
    fmv.x.d t2, f6
    or      t1, t1, t2
    fmv.x.d t2, f7
    or      t1, t1, t2
    fmv.x.d t2, f8
    or      t1, t1, t2
    fmv.x.d t2, f9
    or      t1, t1, t2
    fmv.x.d t2, f10
    or      t1, t1, t2
    fmv.x.d t2, f11
    or      t1, t1, t2
    fmv.x.d t2, f12
    or      t1, t1, t2
    fmv.x.d t2, f13
    or      t1, t1, t2
    fmv.x.d t2, f14
    or      t1, t1, t2
    fmv.x.d t2, f15
    or      t1, t1, t2

    snez    a0, t1
    li      a7, 93
    ecall

    .size _start, .-_start
