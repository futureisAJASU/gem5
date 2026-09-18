.section .text
.align 2
.globl _start
.type _start, @function
_start:
    li      t0, 123456789
    li      t1, 37
    li      s0, 32768

1:
    div     t2, t0, t1
    addi    s0, s0, -1
    bnez    s0, 1b

    li      a0, 0
    li      a7, 93
    ecall
.size _start, .-_start
