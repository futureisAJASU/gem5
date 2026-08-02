#ifndef ITERATIONS
#define ITERATIONS 200000
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
     * No libc, no crt startup, no printf, and no glibc atomic operations.
     * Only the benchmark loop and gem5 m5ops are executed.
     */

    mov     x0, #0
    mov     x1, #0
    bl      m5_reset_stats

    ldr     x0, =ITERATIONS
    bl      gap_sweep_run

    /*
     * x19 is callee-saved under AAPCS64, so retain the checksum while
     * m5_dump_stats executes.
     */
    mov     x19, x0

    mov     x0, #0
    mov     x1, #0
    bl      m5_dump_stats

    /*
     * GAP=4, ITERATIONS=200000 expected checksum:
     * 17101072228982024337 = 0xed5336963ec56891
     */
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
