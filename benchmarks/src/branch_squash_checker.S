#ifndef ITERATIONS
#define ITERATIONS 100000
#endif

#ifndef EXPECTED_CHECKSUM
#error "EXPECTED_CHECKSUM must be defined"
#endif

    .section .text
    .align  2

    .global _start
    .type   _start, %function

_start:
    /*
     * Statistics contain only the benchmark ROI.
     * No libc, crt startup, printf, or atomic runtime operations.
     */
    mov     x0, #0
    mov     x1, #0
    bl      m5_reset_stats

    ldr     x0, =ITERATIONS
    bl      branch_squash_run

    /*
     * Preserve the checksum across the m5_dump_stats call.
     */
    mov     x19, x0

    mov     x0, #0
    mov     x1, #0
    bl      m5_dump_stats

    ldr     x1, =EXPECTED_CHECKSUM
    cmp     x19, x1
    b.ne    .Lchecksum_fail

.Lsuccess:
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


    .align  2
    .global branch_squash_run
    .type   branch_squash_run, %function

/*
 * x0 = iteration count
 *
 * A xorshift64 state generates a difficult-to-predict branch direction.
 * The branch condition passes through UDIV so branch resolution is delayed,
 * allowing younger instructions from the predicted path to enter the OoO
 * machinery before a misprediction is discovered.
 */
branch_squash_run:
    ldr     x1, =0x9e3779b97f4a7c15
    mov     x2, #1

    mov     x3, #1
    mov     x4, #2
    mov     x5, #3
    mov     x6, #4
    mov     x7, #5
    mov     x8, #6
    mov     x9, #7
    mov     x10, #8

.Lloop:
    /*
     * xorshift64:
     * state ^= state << 13
     * state ^= state >> 7
     * state ^= state << 17
     */
    eor     x1, x1, x1, lsl #13
    eor     x1, x1, x1, lsr #7
    eor     x1, x1, x1, lsl #17

    and     x11, x1, #1

    /*
     * Artificially delay branch resolution.
     * Dividing 0 or 1 by 1 preserves the branch condition.
     */
    udiv    x11, x11, x2
    cbz     x11, .Lzero_path

.Lone_path:
    add     x3, x3, #3
    eor     x4, x4, x5
    add     x5, x5, #5
    eor     x6, x6, x7
    add     x7, x7, #7
    eor     x8, x8, x9
    add     x9, x9, #11
    eor     x10, x10, x3
    b       .Lmerge

.Lzero_path:
    add     x3, x3, #13
    eor     x4, x4, x6
    add     x5, x5, #17
    eor     x6, x6, x8
    add     x7, x7, #19
    eor     x8, x8, x10
    add     x9, x9, #23
    eor     x10, x10, x5

.Lmerge:
    subs    x0, x0, #1
    b.ne    .Lloop

    /*
     * Fold every architectural state register into one checksum.
     */
    eor     x13, x1, x3
    eor     x13, x13, x4
    eor     x13, x13, x5
    eor     x13, x13, x6
    eor     x13, x13, x7
    eor     x13, x13, x8
    eor     x13, x13, x9
    eor     x0, x13, x10
    ret

    .size branch_squash_run, .-branch_squash_run
