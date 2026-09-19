/*
 * RV64 pair-shared FMA burst-density characterization.
 *
 * Historical AArch64 validation swept nominal VMAC/SIMD densities
 * 25%, 37.5%, and 43.75% with burst persistence from 16 to 8192.
 * The original generator was not preserved in-tree, so this is an
 * explicit RV64 reconstruction with those same experiment dimensions.
 *
 * Density is defined over payload periods:
 *   active period = BURST scalar FMADD.D operations
 *   idle   period = BURST serialized integer operations
 *
 * Patterns:
 *   25.00% : A I I I
 *   37.50% : A I A I I A I I
 *   43.75% : A I A I A I A I A I A I A I I I
 *
 * No active periods are adjacent, so every FMA pressure episode has
 * exactly BURST FMAs. TOTAL_FMA_PER_CORE is chosen so all historical
 * density ratios and every power-of-two BURST in [16,8192] divide
 * exactly. Every configuration therefore executes exactly 172032 FMAs
 * per core while varying only nominal density and burst persistence.
 *
 * The integer period is deliberately dependency-serialized.  The
 * f15 -> integer -> f30 bridge prevents the next FMA burst from issuing
 * through the gap, so each pressure episode can drain before the next
 * one. Results must still be interpreted using measured runtime and
 * FU statistics, not as a literal hardware activity percentage.
 */

#ifndef BURST
#error "BURST must be defined"
#endif

#ifndef DENSITY_BP
#error "DENSITY_BP must be defined (2500, 3750, or 4375)"
#endif

#define TOTAL_FMA_PER_CORE 172032

#if BURST < 16
#error "BURST must be at least 16"
#endif

#if (BURST % 16) != 0
#error "BURST must be a multiple of 16"
#endif

#if DENSITY_BP == 2500
#define ACTIVE_PER_PATTERN 1
#define PATTERN_REPS (TOTAL_FMA_PER_CORE / (BURST * ACTIVE_PER_PATTERN))
#elif DENSITY_BP == 3750
#define ACTIVE_PER_PATTERN 3
#define PATTERN_REPS (TOTAL_FMA_PER_CORE / (BURST * ACTIVE_PER_PATTERN))
#elif DENSITY_BP == 4375
#define ACTIVE_PER_PATTERN 7
#define PATTERN_REPS (TOTAL_FMA_PER_CORE / (BURST * ACTIVE_PER_PATTERN))
#else
#error "unsupported DENSITY_BP"
#endif

#if (TOTAL_FMA_PER_CORE % (BURST * ACTIVE_PER_PATTERN)) != 0
#error "TOTAL_FMA_PER_CORE must divide exactly by BURST*ACTIVE_PER_PATTERN"
#endif

    .section .text
    .globl _start
    .type _start, @function

    .macro FMA_BURST
        li      t2, (BURST / 16)
.Lfma_loop_\@:
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
        addi    t2, t2, -1
        bnez    t2, .Lfma_loop_\@
    .endm

    .macro IDLE_BURST
        /*
         * Wait on the tail accumulator, then create a serialized
         * integer gap.  The final fmv.d.x feeds the multiplicand used
         * by the next active period and blocks cross-gap FMA issue.
         */
        fmv.x.d t1, f15
        li      t2, (BURST / 16)
.Lidle_loop_\@:
        .rept 16
        xor     t1, t1, zero
        .endr
        addi    t2, t2, -1
        bnez    t2, .Lidle_loop_\@
        fmv.d.x f30, t1
    .endm

_start:
    li      t0, PATTERN_REPS

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

.Lpattern:
#if DENSITY_BP == 2500
    FMA_BURST
    IDLE_BURST
    IDLE_BURST
    IDLE_BURST
#elif DENSITY_BP == 3750
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    IDLE_BURST
#elif DENSITY_BP == 4375
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    FMA_BURST
    IDLE_BURST
    IDLE_BURST
    IDLE_BURST
#endif

    addi    t0, t0, -1
    bnez    t0, .Lpattern

    /*
     * All arithmetic starts from +0.0 and every integer gap preserves
     * zero, so any non-zero accumulator indicates a broken workload.
     */
    li      t3, 0
    fmv.x.d t4, f0
    or      t3, t3, t4
    fmv.x.d t4, f1
    or      t3, t3, t4
    fmv.x.d t4, f2
    or      t3, t3, t4
    fmv.x.d t4, f3
    or      t3, t3, t4
    fmv.x.d t4, f4
    or      t3, t3, t4
    fmv.x.d t4, f5
    or      t3, t3, t4
    fmv.x.d t4, f6
    or      t3, t3, t4
    fmv.x.d t4, f7
    or      t3, t3, t4
    fmv.x.d t4, f8
    or      t3, t3, t4
    fmv.x.d t4, f9
    or      t3, t3, t4
    fmv.x.d t4, f10
    or      t3, t3, t4
    fmv.x.d t4, f11
    or      t3, t3, t4
    fmv.x.d t4, f12
    or      t3, t3, t4
    fmv.x.d t4, f13
    or      t3, t3, t4
    fmv.x.d t4, f14
    or      t3, t3, t4
    fmv.x.d t4, f15
    or      t3, t3, t4

    snez    a0, t3
    li      a7, 93
    ecall

    .size _start, .-_start
