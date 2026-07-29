import argparse
from pathlib import Path

from m5.objects import ArmO3CPU, IQUnit

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.memory.single_channel import SingleChannelDDR4_2400
from gem5.components.processors.base_cpu_core import BaseCPUCore
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor
from gem5.isas import ISA
from gem5.resources.resource import BinaryResource
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires


class LittleV052ProxyCore(BaseCPUCore):
    """Stock gem5 O3 proxy for the v0.52 parameter baseline.

    This is deliberately NOT the custom distributed-queue scheduler.
    It uses gem5's conventional central O3 instruction queue.
    """

    def __init__(
        self,
        rob_entries: int,
        iq_entries: int,
        lq_entries: int,
        sq_entries: int,
        width: int = 3,
        commit_width: int = 3,
        int_regs: int = 112,
        fp_regs: int = 96,
    ) -> None:
        cpu = ArmO3CPU()

        cpu.fetchWidth = width
        cpu.decodeWidth = width
        cpu.renameWidth = width
        cpu.dispatchWidth = width
        cpu.issueWidth = width
        cpu.wbWidth = width
        cpu.commitWidth = commit_width

        cpu.numROBEntries = rob_entries
        cpu.instQueues = [IQUnit(numEntries=iq_entries)]
        cpu.LQEntries = lq_entries
        cpu.SQEntries = sq_entries

        cpu.numPhysIntRegs = int_regs
        cpu.numPhysFloatRegs = fp_regs

        super().__init__(core=cpu, isa=ISA.ARM)


class LittleV052ProxyProcessor(BaseCPUProcessor):
    def __init__(
        self,
        rob_entries: int,
        iq_entries: int,
        lq_entries: int,
        sq_entries: int,
        width: int,
        commit_width: int,
    ) -> None:
        cores = [
            LittleV052ProxyCore(
                rob_entries=rob_entries,
                iq_entries=iq_entries,
                lq_entries=lq_entries,
                sq_entries=sq_entries,
                width=width,
                commit_width=commit_width,
            )
        ]
        super().__init__(cores=cores)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Little Core v0.52 stock-O3 proxy"
    )
    parser.add_argument("--binary", required=True, help="AArch64 static ELF path")
    parser.add_argument("--clock", default="1.4GHz")
    parser.add_argument("--width", type=int, default=3)
    parser.add_argument("--commit-width", type=int, default=3)
    parser.add_argument("--rob", type=int, default=80)
    parser.add_argument("--iq", type=int, default=40)
    parser.add_argument("--lq", type=int, default=12)
    parser.add_argument("--sq", type=int, default=16)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requires(isa_required=ISA.ARM)

    binary_path = Path(args.binary).resolve()
    if not binary_path.is_file():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    processor = LittleV052ProxyProcessor(
        rob_entries=args.rob,
        iq_entries=args.iq,
        lq_entries=args.lq,
        sq_entries=args.sq,
        width=args.width,
        commit_width=args.commit_width,
    )

    # First proxy pass: sizes and associativity only.
    # Exact L1/L2 latency, banking, and MSHR policy require a custom hierarchy.
    cache_hierarchy = PrivateL1SharedL2CacheHierarchy(
        l1d_size="64KiB",
        l1i_size="64KiB",
        l2_size="1MiB",
        l1d_assoc=4,
        l1i_assoc=4,
        l2_assoc=8,
    )

    memory = SingleChannelDDR4_2400(size="512MiB")

    board = SimpleBoard(
        clk_freq=args.clock,
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
    )

    board.set_se_binary_workload(
        BinaryResource(
            local_path=str(binary_path),
            architecture=ISA.ARM,
        )
    )

    print(
        "Little v0.52 proxy:",
        f"clock={args.clock}",
        f"width={args.width}",
        f"commit={args.commit_width}",
        f"ROB={args.rob}",
        f"IQ={args.iq}",
        f"LQ={args.lq}",
        f"SQ={args.sq}",
        sep="\n  ",
    )

    simulator = Simulator(board=board)
    simulator.run()


if __name__ in ("__main__", "__m5_main__"):
    main()
