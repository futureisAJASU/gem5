/*
 * Canonical seeded randomized dependency-DAG stress benchmark.
 *
 * Generator seed:        0x5eed052
 * Iterations:            20000
 * Operations/iteration:  101
 *
 * Operation mix:
 *   add   33
 *   eor   25
 *   mul   21
 *   sub   19
 *   udiv   3
 *
 * Reference checksum:
 *   0x949582daedcf9f3e
 *
 * The generated stream also contains explicit GAP=1, GAP=2, and GAP=4
 * dependency motifs to exercise bounded N-SKIP visibility.
 *
 * Validation matrix:
 *   stock, N=0, N=1, N=2, N=4
 *
 * All configurations must preserve architectural execution while every
 * enabled N-SKIP configuration must issue only within Head..Head+N.
 */

#ifndef ITERATIONS
#define ITERATIONS 20000
#endif

#ifndef EXPECTED_CHECKSUM
#error "EXPECTED_CHECKSUM must be defined"
#endif

    .section .text
    .align 2

    .global _start
    .type _start, %function

_start:
    mov     x0, #0
    mov     x1, #0
    bl      m5_reset_stats

    ldr     x0, =ITERATIONS
    bl      random_dag_run

    mov     x19, x0

    mov     x0, #0
    mov     x1, #0
    bl      m5_dump_stats

    ldr     x1, =EXPECTED_CHECKSUM
    cmp     x19, x1
    b.ne    .Lchecksum_fail

    mov     x0, #0
    bl      m5_exit

.Lhalt:
    wfe
    b       .Lhalt

.Lchecksum_fail:
    mov     x0, #0
    mov     x1, #1
    bl      m5_fail
    b       .Lhalt

    .size _start, .-_start


    .align 2
    .global random_dag_run
    .type random_dag_run, %function

random_dag_run:
    mov     x15, #3

    ldr     x2, =0x0123456789abcdef
    ldr     x3, =0xfedcba9876543210
    ldr     x4, =0x0f0f0f0f0f0f0f0f
    ldr     x5, =0xf0f0f0f0f0f0f0f0
    ldr     x6, =0x13579bdf2468ace0
    ldr     x7, =0xcafebabedeadbeef
    ldr     x8, =0x1122334455667788
    ldr     x9, =0x8877665544332211
    ldr     x10, =0x3141592653589793
    ldr     x11, =0x2718281828459045

.Ldag_loop:
    udiv    x2, x2, x15
    add     x3, x2, x4
    add     x8, x8, x7
    add     x5, x11, x2
    sub     x4, x8, x9
    add     x7, x5, x11
    eor     x10, x3, x11
    mul     x11, x8, x10
    eor     x8, x6, x4
    sub     x3, x11, x10
    sub     x9, x11, x11
    eor     x10, x9, x10
    mul     x6, x8, x6
    sub     x5, x3, x9
    eor     x7, x5, x3
    add     x3, x6, x5
    add     x3, x5, x6
    add     x4, x4, x6
    eor     x2, x11, x4
    mul     x6, x4, x6
    mul     x8, x6, x7
    add     x6, x7, x10
    eor     x2, x5, x10
    sub     x10, x9, x5
    eor     x7, x7, x9
    add     x8, x11, x2
    mul     x4, x11, x9
    udiv    x5, x5, x15
    add     x2, x5, x3
    eor     x4, x5, x6
    add     x10, x10, x9
    add     x10, x3, x7
    mul     x6, x5, x8
    sub     x5, x11, x7
    add     x9, x3, x7
    add     x2, x2, x4
    add     x10, x6, x8
    add     x9, x2, x3
    add     x2, x10, x9
    mul     x6, x6, x10
    mul     x5, x4, x7
    add     x9, x10, x11
    eor     x7, x11, x9
    add     x10, x10, x3
    eor     x8, x6, x11
    eor     x9, x8, x2
    add     x9, x8, x8
    mul     x3, x4, x5
    add     x3, x2, x6
    add     x9, x4, x6
    sub     x7, x10, x9
    sub     x5, x3, x3
    sub     x11, x8, x7
    eor     x3, x10, x3
    sub     x10, x9, x11
    mul     x7, x7, x2
    add     x3, x3, x2
    eor     x5, x7, x9
    mul     x11, x6, x4
    udiv    x2, x2, x15
    add     x3, x2, x4
    eor     x5, x2, x6
    add     x7, x2, x8
    eor     x9, x2, x10
    add     x11, x11, x9
    mul     x3, x10, x9
    sub     x11, x7, x4
    sub     x9, x7, x9
    eor     x10, x5, x10
    eor     x11, x9, x3
    add     x5, x11, x4
    mul     x3, x8, x9
    sub     x7, x5, x11
    add     x10, x5, x9
    eor     x2, x3, x3
    sub     x6, x8, x6
    sub     x11, x8, x7
    mul     x9, x5, x10
    add     x4, x10, x2
    eor     x10, x8, x6
    sub     x6, x3, x7
    eor     x7, x7, x8
    mul     x2, x11, x2
    sub     x6, x8, x9
    eor     x5, x6, x6
    eor     x3, x6, x7
    mul     x6, x11, x6
    mul     x5, x2, x4
    mul     x9, x6, x10
    mul     x9, x8, x4
    mul     x4, x4, x2
    add     x11, x8, x3
    eor     x4, x4, x7
    eor     x2, x5, x6
    sub     x6, x7, x8
    add     x4, x7, x2
    add     x2, x3, x10
    add     x9, x10, x5
    sub     x5, x5, x6
    mul     x3, x10, x10
    eor     x10, x7, x8

    subs    x0, x0, #1
    b.ne    .Ldag_loop

    mov     x12, x2
    eor     x12, x12, x3
    eor     x12, x12, x4
    eor     x12, x12, x5
    eor     x12, x12, x6
    eor     x12, x12, x7
    eor     x12, x12, x8
    eor     x12, x12, x9
    eor     x12, x12, x10
    eor     x12, x12, x11
    mov     x0, x12
    ret

    .size random_dag_run, .-random_dag_run
