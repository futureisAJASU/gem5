.text
.align 2
.globl main
.type main, @function
main:
    li      t0, 1234567
    li      t1, 37

    div     t2, t0, t1
    divu    t3, t0, t1
    rem     t4, t0, t1
    remu    t5, t0, t1

    divw    t2, t0, t1
    divuw   t3, t0, t1
    remw    t4, t0, t1
    remuw   t5, t0, t1

    # Near-neighbor M-extension / integer operations must not hint IntDiv.
    mul     t6, t0, t1
    sll     t6, t0, t1
    srl     t6, t0, t1
    sra     t6, t0, t1

    li      a0, 0
    ret
.size main, .-main
