/*
 * G0-only RV64 gem5 pseudo-operation stubs.
 * Exact instruction encoding from frozen util/m5/src/abi/riscv/m5op.S:
 * .long 0x0000007b | (M5OP_WORK_BEGIN/END << 25)
 * M5OP_WORK_BEGIN = 0x5a, M5OP_WORK_END = 0x5b.
 * Arguments: a0 workid 0x4730, a1 threadid 0.
 * Host validates REAL tc->getCpuPtr()->cpuId() rather than guest IDs.
 */
.text
.p2align 2
.globl g0_pair_roi_begin
.type g0_pair_roi_begin, @function
g0_pair_roi_begin:
    li a0, 0x4730
    li a1, 0
    .4byte 0xb400007b
    ret
.size g0_pair_roi_begin, .-g0_pair_roi_begin

.p2align 2
.globl g0_pair_roi_end
.type g0_pair_roi_end, @function
g0_pair_roi_end:
    li a0, 0x4730
    li a1, 0
    .4byte 0xb600007b
    ret
.size g0_pair_roi_end, .-g0_pair_roi_end

.section .note.GNU-stack,"",@progbits
