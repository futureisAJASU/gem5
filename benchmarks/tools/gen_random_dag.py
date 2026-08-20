#!/usr/bin/env python3

import argparse
import random
from pathlib import Path

MASK = (1 << 64) - 1

REGS = [f"x{i}" for i in range(2, 12)]

INITIAL = {
    "x2":  0x0123456789ABCDEF,
    "x3":  0xFEDCBA9876543210,
    "x4":  0x0F0F0F0F0F0F0F0F,
    "x5":  0xF0F0F0F0F0F0F0F0,
    "x6":  0x13579BDF2468ACE0,
    "x7":  0xCAFEBABEDEADBEEF,
    "x8":  0x1122334455667788,
    "x9":  0x8877665544332211,
    "x10": 0x3141592653589793,
    "x11": 0x2718281828459045,
}


def build_ops(seed: int):
    rng = random.Random(seed)
    ops = []

    def add_op(kind, dst, src1, src2=None):
        ops.append((kind, dst, src1, src2))

    def gap_motif(producer, gap, independent):
        add_op("udiv3", producer, producer)

        candidates = [
            r for r in REGS
            if r not in (producer, independent)
        ]

        for i in range(gap):
            dst = candidates[(i * 2) % len(candidates)]
            other = candidates[(i * 2 + 1) % len(candidates)]

            if i & 1:
                add_op("eor", dst, producer, other)
            else:
                add_op("add", dst, producer, other)

        other = rng.choice([
            r for r in REGS
            if r != independent
        ])

        add_op("add", independent, independent, other)

    gap_motif("x2", 1, "x8")

    for _ in range(24):
        add_op(
            rng.choice(("add", "eor", "sub", "mul")),
            rng.choice(REGS),
            rng.choice(REGS),
            rng.choice(REGS),
        )

    gap_motif("x5", 2, "x10")

    for _ in range(28):
        add_op(
            rng.choice(("add", "eor", "sub", "mul")),
            rng.choice(REGS),
            rng.choice(REGS),
            rng.choice(REGS),
        )

    gap_motif("x2", 4, "x11")

    for _ in range(36):
        add_op(
            rng.choice(("add", "eor", "sub", "mul")),
            rng.choice(REGS),
            rng.choice(REGS),
            rng.choice(REGS),
        )

    return ops


def compute_checksum(ops, iterations):
    state = dict(INITIAL)

    for _ in range(iterations):
        for kind, dst, src1, src2 in ops:
            a = state[src1]

            if kind == "udiv3":
                state[dst] = a // 3
                continue

            b = state[src2]

            if kind == "add":
                state[dst] = (a + b) & MASK
            elif kind == "eor":
                state[dst] = (a ^ b) & MASK
            elif kind == "sub":
                state[dst] = (a - b) & MASK
            elif kind == "mul":
                state[dst] = (a * b) & MASK
            else:
                raise RuntimeError(kind)

    checksum = 0

    for reg in REGS:
        checksum ^= state[reg]

    return checksum & MASK


def emit_assembly(ops, iterations, checksum, seed):
    init_lines = [
        f"    ldr     {reg}, =0x{INITIAL[reg]:016x}"
        for reg in REGS
    ]

    body = []

    for kind, dst, src1, src2 in ops:
        if kind == "udiv3":
            body.append(
                f"    udiv    {dst}, {src1}, x15"
            )
        else:
            body.append(
                f"    {kind:<7} {dst}, {src1}, {src2}"
            )

    fold = ["    mov     x12, x2"]

    for reg in REGS[1:]:
        fold.append(
            f"    eor     x12, x12, {reg}"
        )

    fold.append("    mov     x0, x12")

    return f"""\
/*
 * Generated randomized dependency DAG.
 *
 * seed:       0x{seed:x}
 * iterations: {iterations}
 * ops/iter:   {len(ops)}
 * checksum:   0x{checksum:016x}
 */

    .section .text
    .align 2

    .global _start
    .type _start, %function

_start:
    mov     x0, #0
    mov     x1, #0
    bl      m5_reset_stats

    ldr     x0, ={iterations}
    bl      random_dag_run

    mov     x19, x0

    mov     x0, #0
    mov     x1, #0
    bl      m5_dump_stats

    ldr     x1, =0x{checksum:016x}
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

{chr(10).join(init_lines)}

.Lloop:
{chr(10).join(body)}

    subs    x0, x0, #1
    b.ne    .Lloop

{chr(10).join(fold)}
    ret

    .size random_dag_run, .-random_dag_run
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    ops = build_ops(args.seed)
    checksum = compute_checksum(ops, args.iterations)

    args.output.write_text(
        emit_assembly(
            ops,
            args.iterations,
            checksum,
            args.seed,
        )
    )

    print(
        f"seed=0x{args.seed:x} "
        f"iterations={args.iterations} "
        f"ops={len(ops)} "
        f"checksum=0x{checksum:016x}"
    )


if __name__ == "__main__":
    main()
