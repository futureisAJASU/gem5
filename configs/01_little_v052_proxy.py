import argparse
from pathlib import Path

from m5.objects import ArmO3CPU, IQUnit, ArmExtension
from m5.objects.FUPool import FUPool
from m5.params import NULL
from m5.objects.FuncUnit import FUDesc, OpDesc

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



class LittleExplicitCacheHierarchy(
    PrivateL1SharedL2CacheHierarchy
):
    """
    Stage 2M validation hierarchy.

    Preserve the existing gem5 Classic private-L1/shared-L2
    topology while making all memory-validation-sensitive
    proxy defaults explicit.

    These values are CONTROL BASELINE values only.
    They are not frozen Little/LPE architectural choices.
    """

    def __init__(
        self,
        *,
        l1d_size: str,
        l1i_size: str,
        l2_size: str,
        l1d_assoc: int,
        l1i_assoc: int,
        l2_assoc: int,
        prefetch_enabled: bool,
    ) -> None:
        super().__init__(
            l1d_size=l1d_size,
            l1i_size=l1i_size,
            l2_size=l2_size,
            l1d_assoc=l1d_assoc,
            l1i_assoc=l1i_assoc,
            l2_assoc=l2_assoc,
        )

        self._little_prefetch_enabled = prefetch_enabled

    def incorporate_cache(self, board) -> None:
        # Keep upstream topology and port wiring exactly intact.
        super().incorporate_cache(board)

        # ----------------------------------------------------
        # L1I — current proxy defaults, explicitly stated.
        # ----------------------------------------------------
        for cache in self.l1icaches:
            cache.tag_latency = 1
            cache.data_latency = 1
            cache.response_latency = 1

            cache.mshrs = 16
            cache.tgts_per_mshr = 20
            cache.demand_mshr_reserve = 1
            cache.write_buffers = 8

            cache.sequential_access = False
            cache.writeback_clean = False

            if not self._little_prefetch_enabled:
                cache.prefetcher = NULL

        # ----------------------------------------------------
        # L1D — current proxy defaults, explicitly stated.
        # ----------------------------------------------------
        for cache in self.l1dcaches:
            cache.tag_latency = 1
            cache.data_latency = 1
            cache.response_latency = 1

            cache.mshrs = 16
            cache.tgts_per_mshr = 20
            cache.demand_mshr_reserve = 1
            cache.write_buffers = 8

            cache.sequential_access = False
            cache.writeback_clean = False

            if not self._little_prefetch_enabled:
                cache.prefetcher = NULL

        # ----------------------------------------------------
        # Shared L2 — current proxy defaults.
        # ----------------------------------------------------
        cache = self.l2cache

        cache.tag_latency = 10
        cache.data_latency = 10
        cache.response_latency = 1

        cache.mshrs = 20
        cache.tgts_per_mshr = 12
        cache.demand_mshr_reserve = 1
        cache.write_buffers = 8

        cache.sequential_access = False
        cache.writeback_clean = False
        cache.clusivity = "mostly_incl"

        if not self._little_prefetch_enabled:
            cache.prefetcher = NULL

        # ----------------------------------------------------
        # Interconnect widths.
        #
        # gem5 BaseXBar.width is BYTES per port, not bits.
        #
        # L2XBar default  : 32 B
        # Current hierarchy membus: SystemXBar(width=64)
        #
        # These are explicitly preserved proxy values.
        # ----------------------------------------------------
        self.l2bus.width = 32
        self.membus.width = 64


#
# Provisional distributed scheduler topology.
#
# FU counts intentionally retain roughly the stock DefaultFUPool execution
# capacity for this structural stage. Queue sizing, steering, N-SKIP policy,
# and final Little-core FU counts are validated separately later.
#

class LittleInt0AluFU(FUDesc):
    opList = [OpDesc(opClass="IntAlu", opLat=1)]
    count = 3


class LittleInt0MulFU(FUDesc):
    opList = [OpDesc(opClass="IntMult", opLat=3)]
    count = 2


class LittleSystemFU(FUDesc):
    opList = [OpDesc(opClass="System", opLat=1)]
    count = 1


class LittleInt0Pool(FUPool):
    FUList = [
        LittleInt0AluFU(),
        LittleInt0MulFU(),
        LittleSystemFU(),
    ]


class LittleInt1AluFU(FUDesc):
    opList = [OpDesc(opClass="IntAlu", opLat=1)]
    count = 3


class LittleInt1Pool(FUPool):
    FUList = [LittleInt1AluFU()]


class LittleDivFU(FUDesc):
    opList = [
        OpDesc(
            opClass="IntDiv",
            opLat=20,
            pipelined=False,
        )
    ]
    count = 2


class LittleDivPool(FUPool):
    FUList = [LittleDivFU()]


class LittlePairSharedDivFU(FUDesc):
    """One physical non-pipelined divider shared by a two-core pair."""

    opList = [
        OpDesc(
            opClass="IntDiv",
            opLat=20,
            pipelined=False,
        )
    ]
    count = 1


class LittlePairSharedDivPool(FUPool):
    FUList = [LittlePairSharedDivFU()]
    pairRrArb = True


class LittleMemFU(FUDesc):
    opList = [
        OpDesc(opClass="MemRead"),
        OpDesc(opClass="MemWrite"),
        OpDesc(opClass="FloatMemRead"),
        OpDesc(opClass="FloatMemWrite"),
        OpDesc(opClass="InstPrefetch"),
        OpDesc(opClass="SimdUnitStrideLoad"),
        OpDesc(opClass="SimdUnitStrideStore"),
        OpDesc(opClass="SimdUnitStrideMaskLoad"),
        OpDesc(opClass="SimdUnitStrideMaskStore"),
        OpDesc(opClass="SimdStridedLoad"),
        OpDesc(opClass="SimdStridedStore"),
        OpDesc(opClass="SimdIndexedLoad"),
        OpDesc(opClass="SimdIndexedStore"),
        OpDesc(opClass="SimdWholeRegisterLoad"),
        OpDesc(opClass="SimdWholeRegisterStore"),
        OpDesc(opClass="SimdUnitStrideFaultOnlyFirstLoad"),
        OpDesc(opClass="SimdUnitStrideSegmentedLoad"),
        OpDesc(opClass="SimdUnitStrideSegmentedStore"),
        OpDesc(opClass="SimdUnitStrideSegmentedFaultOnlyFirstLoad"),
        OpDesc(opClass="SimdStrideSegmentedLoad"),
        OpDesc(opClass="SimdStrideSegmentedStore"),
    ]
    count = 4


class LittleMemPool(FUPool):
    FUList = [LittleMemFU()]


class LittleFpAluFU(FUDesc):
    opList = [
        OpDesc(opClass="FloatAdd", opLat=2),
        OpDesc(opClass="FloatCmp", opLat=2),
        OpDesc(opClass="FloatCvt", opLat=2),
        OpDesc(opClass="Bf16Cvt", opLat=2),
    ]
    count = 4


class LittleFpMultDivFU(FUDesc):
    opList = [
        OpDesc(opClass="FloatMult", opLat=4),
        OpDesc(opClass="FloatMultAcc", opLat=5),
        OpDesc(opClass="FloatMisc", opLat=3),
        OpDesc(
            opClass="FloatDiv",
            opLat=12,
            pipelined=False,
        ),
        OpDesc(
            opClass="FloatSqrt",
            opLat=24,
            pipelined=False,
        ),
    ]
    count = 2


class LittleSimdFU(FUDesc):
    opList = [
        OpDesc(opClass="SimdAdd"),
        OpDesc(opClass="SimdAddAcc"),
        OpDesc(opClass="SimdAlu"),
        OpDesc(opClass="SimdCmp"),
        OpDesc(opClass="SimdCvt"),
        OpDesc(opClass="SimdMisc"),
        OpDesc(opClass="SimdMult"),
        OpDesc(opClass="SimdMultAcc"),
        OpDesc(opClass="SimdMatMultAcc"),
        OpDesc(opClass="SimdShift"),
        OpDesc(opClass="SimdShiftAcc"),
        OpDesc(opClass="SimdDiv"),
        OpDesc(opClass="SimdSqrt"),
        OpDesc(opClass="SimdFloatAdd"),
        OpDesc(opClass="SimdFloatAlu"),
        OpDesc(opClass="SimdFloatCmp"),
        OpDesc(opClass="SimdFloatCvt"),
        OpDesc(opClass="SimdFloatDiv"),
        OpDesc(opClass="SimdFloatMisc"),
        OpDesc(opClass="SimdFloatMult"),
        OpDesc(opClass="SimdFloatMultAcc"),
        OpDesc(opClass="SimdFloatMatMultAcc"),
        OpDesc(opClass="SimdFloatSqrt"),
        OpDesc(opClass="SimdReduceAdd"),
        OpDesc(opClass="SimdReduceAlu"),
        OpDesc(opClass="SimdReduceCmp"),
        OpDesc(opClass="SimdFloatReduceAdd"),
        OpDesc(opClass="SimdFloatReduceCmp"),
        OpDesc(opClass="SimdAes"),
        OpDesc(opClass="SimdAesMix"),
        OpDesc(opClass="SimdSha1Hash"),
        OpDesc(opClass="SimdSha1Hash2"),
        OpDesc(opClass="SimdSha256Hash"),
        OpDesc(opClass="SimdSha256Hash2"),
        OpDesc(opClass="SimdShaSigma2"),
        OpDesc(opClass="SimdShaSigma3"),
        OpDesc(opClass="SimdSha3"),
        OpDesc(opClass="SimdSm4e"),
        OpDesc(opClass="SimdCrc"),
        OpDesc(opClass="SimdPredAlu"),
        OpDesc(opClass="SimdDotProd"),
        OpDesc(opClass="SimdExt"),
        OpDesc(opClass="SimdFloatExt"),
        OpDesc(opClass="SimdConfig"),
        OpDesc(opClass="SimdBf16Add"),
        OpDesc(opClass="SimdBf16Cmp"),
        OpDesc(opClass="SimdBf16Cvt"),
        OpDesc(opClass="SimdBf16DotProd"),
        OpDesc(opClass="SimdBf16MatMultAcc"),
        OpDesc(opClass="SimdBf16Mult"),
        OpDesc(opClass="SimdBf16MultAcc"),
    ]
    count = 4


class LittleMatrixFU(FUDesc):
    opList = [
        OpDesc(opClass="Matrix"),
        OpDesc(opClass="MatrixMov"),
        OpDesc(opClass="MatrixOP"),
    ]
    count = 1


class LittleFpSimdPool(FUPool):
    FUList = [
        LittleFpAluFU(),
        LittleFpMultDivFU(),
        LittleSimdFU(),
        LittleMatrixFU(),
    ]


# Pair-shared FP/SIMD execution backend.
#
# Scalar physical domains:
#   FP-Simple    x2 / pair
#   FP-MulFMA    x2 / pair
#   FP-DivSqrt   x2 / pair
#
# SIMD x4 and Matrix x1 remain provisional.
# Physical Vec rename registers remain private per CPU.
class LittlePairSharedFpSimpleFU(FUDesc):
    opList = [
        OpDesc(opClass="FloatAdd", opLat=2),
        OpDesc(opClass="FloatCmp", opLat=2),
        OpDesc(opClass="FloatCvt", opLat=2),
        OpDesc(opClass="Bf16Cvt", opLat=2),
    ]
    count = 2


class LittlePairSharedFpMulFmaFU(FUDesc):
    opList = [
        OpDesc(opClass="FloatMult", opLat=4),
        OpDesc(opClass="FloatMultAcc", opLat=5),
        OpDesc(opClass="FloatMisc", opLat=3),
    ]
    count = 2


class LittlePairSharedFpDivSqrtFU(FUDesc):
    opList = [
        OpDesc(
            opClass="FloatDiv",
            opLat=12,
            pipelined=False,
        ),
        OpDesc(
            opClass="FloatSqrt",
            opLat=24,
            pipelined=False,
        ),
    ]
    count = 2


class LittlePairSharedFpSimdPool(FUPool):
    FUList = [
        LittlePairSharedFpSimpleFU(),
        LittlePairSharedFpMulFmaFU(),
        LittlePairSharedFpDivSqrtFU(),
        LittleSimdFU(),
        LittleMatrixFU(),
    ]
    pairRrArb = True


def make_little_distributed_iqs(
    n_skip: int,
    int0_entries: int = 10,
    int1_entries: int = 6,
    mem_entries: int = 12,
    div_entries: int = 4,
    fpsimd_entries: int = 6,
    div_pool=None,
    fpsimd_pool=None,
    pair_requester_id: int = -1,
):
    sizes = {
        "INT0": int0_entries,
        "INT1": int1_entries,
        "MEM": mem_entries,
        "DIV": div_entries,
        "FP/SIMD": fpsimd_entries,
    }

    for name, entries in sizes.items():
        if entries <= 0:
            raise ValueError(
                f"{name} IQ size must be positive, got {entries}"
            )

    iqs = [
        IQUnit(
            numEntries=int0_entries,
            fuPool=LittleInt0Pool(),
        ),
        IQUnit(
            numEntries=int1_entries,
            fuPool=LittleInt1Pool(),
        ),
        IQUnit(
            numEntries=mem_entries,
            fuPool=LittleMemPool(),
        ),
        IQUnit(
            numEntries=div_entries,
            fuPool=(
                div_pool
                if div_pool is not None
                else LittleDivPool()
            ),
            fuRequesterId=(
                pair_requester_id
                if div_pool is not None
                else -1
            ),
        ),
        IQUnit(
            numEntries=fpsimd_entries,
            fuPool=(
                fpsimd_pool
                if fpsimd_pool is not None
                else LittleFpSimdPool()
            ),
            fuRequesterId=(
                pair_requester_id
                if fpsimd_pool is not None
                else -1
            ),
        ),
    ]

    if n_skip >= 0:
        for iq in iqs:
            iq.enableNSkip = True
            iq.nSkip = n_skip

    return iqs


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
        n_skip: int = -1,
        checker: bool = False,
        distributed_iq: bool = False,
        int_steering: str = "first-fit",
        local_iq_picker: bool = False,
        dist_int0_entries: int = 10,
        dist_int1_entries: int = 6,
        dist_mem_entries: int = 12,
        dist_div_entries: int = 4,
        dist_fpsimd_entries: int = 6,
        shared_div_pool=None,
        shared_fpsimd_pool=None,
        pair_requester_id: int = -1,
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

        steering_codes = {
            "first-fit": 0,
            "least-used": 1,
            "round-robin": 2,
            "int1-first": 3,
        }

        cpu.iqSteeringPolicy = steering_codes[int_steering]
        cpu.useLocalIQPicker = local_iq_picker

        if local_iq_picker and not distributed_iq:
            raise ValueError(
                "local_iq_picker requires distributed_iq"
            )

        if distributed_iq:
            cpu.instQueues = make_little_distributed_iqs(
                n_skip=n_skip,
                int0_entries=dist_int0_entries,
                int1_entries=dist_int1_entries,
                mem_entries=dist_mem_entries,
                div_entries=dist_div_entries,
                fpsimd_entries=dist_fpsimd_entries,
                div_pool=shared_div_pool,
                fpsimd_pool=shared_fpsimd_pool,
                pair_requester_id=pair_requester_id,
            )
        else:
            iq = IQUnit(numEntries=iq_entries)
            if n_skip >= 0:
                iq.enableNSkip = True
                iq.nSkip = n_skip
            cpu.instQueues = [iq]

        cpu.LQEntries = lq_entries
        cpu.SQEntries = sq_entries

        cpu.numPhysIntRegs = int_regs
        cpu.numPhysFloatRegs = fp_regs

        # AArch64 scalar FP/NEON architectural state is carried by the
        # vector register class.  Keep the historical fp_regs argument
        # for compatibility, but apply the intended FP/vector physical
        # rename budget to VecRegClass as well.
        cpu.numPhysVecRegs = fp_regs

        self._checker_enabled = checker

        if checker:
            cpu.addCheckerCpu()
            cpu.checker.exitOnError = True
            cpu.checker.updateOnError = False
            cpu.checker.warnOnlyOnLoadError = False

        super().__init__(core=cpu, isa=ISA.ARM)

        if checker:
            # gem5 v25.1 ARM SE enables TME by default. ArmISA::startup()
            # consequently installs an HTM checkpoint, but CheckerThreadContext
            # does not implement setHtmCheckpointPtr(). This benchmark does not
            # exercise transactional memory, so disable TME symmetrically on
            # the main and checker ISAs for strict CheckerCPU validation.
            for isa in cpu.isa:
                isa.release_se.remove(ArmExtension("TME"))

            for isa in cpu.checker.isa:
                isa.release_se.remove(ArmExtension("TME"))

    def set_workload(self, process) -> None:
        super().set_workload(process)

        if self._checker_enabled:
            self.core.checker.workload = process

    def connect_walker_ports(self, port1, port2) -> None:
        super().connect_walker_ports(port1, port2)

        if self._checker_enabled:
            self.core.checker.mmu.connectWalkerPorts(port1, port2)


class LittleV052ProxyProcessor(BaseCPUProcessor):
    def __init__(
        self,
        rob_entries: int,
        iq_entries: int,
        lq_entries: int,
        sq_entries: int,
        width: int,
        commit_width: int,
        n_skip: int,
        checker: bool,
        distributed_iq: bool,
        int_steering: str,
        local_iq_picker: bool,
        dist_int0_entries: int,
        dist_int1_entries: int,
        dist_mem_entries: int,
        dist_div_entries: int,
        dist_fpsimd_entries: int,
        num_cores: int,
        pair_shared_div: bool,
        pair_shared_fpsimd: bool = False,
    ) -> None:
        if num_cores <= 0:
            raise ValueError(
                f"num_cores must be positive, got {num_cores}"
            )

        if pair_shared_div:
            if num_cores != 2:
                raise ValueError(
                    "pair-shared DIV is currently validated only "
                    "for exactly two cores"
                )
            if not distributed_iq:
                raise ValueError(
                    "pair-shared DIV requires --distributed-iq"
                )
            if not local_iq_picker:
                raise ValueError(
                    "pair-shared DIV currently requires "
                    "--local-iq-picker"
                )

        if pair_shared_fpsimd:
            if num_cores != 2:
                raise ValueError(
                    "pair-shared FP/SIMD is currently validated "
                    "only for exactly two cores"
                )
            if not distributed_iq:
                raise ValueError(
                    "pair-shared FP/SIMD requires --distributed-iq"
                )
            if not local_iq_picker:
                raise ValueError(
                    "pair-shared FP/SIMD requires "
                    "--local-iq-picker"
                )

        shared_div_pool = (
            LittlePairSharedDivPool()
            if pair_shared_div
            else None
        )

        shared_fpsimd_pool = (
            LittlePairSharedFpSimdPool()
            if pair_shared_fpsimd
            else None
        )

        cores = [
            LittleV052ProxyCore(
                rob_entries=rob_entries,
                iq_entries=iq_entries,
                lq_entries=lq_entries,
                sq_entries=sq_entries,
                width=width,
                commit_width=commit_width,
                n_skip=n_skip,
                checker=checker,
                distributed_iq=distributed_iq,
                int_steering=int_steering,
                local_iq_picker=local_iq_picker,
                dist_int0_entries=dist_int0_entries,
                dist_int1_entries=dist_int1_entries,
                dist_mem_entries=dist_mem_entries,
                dist_div_entries=dist_div_entries,
                dist_fpsimd_entries=dist_fpsimd_entries,
                shared_div_pool=shared_div_pool,
                shared_fpsimd_pool=shared_fpsimd_pool,
                pair_requester_id=core_idx,
            )
            for core_idx in range(num_cores)
        ]
        super().__init__(cores=cores)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Little Core v0.52 stock-O3 proxy"
    )
    parser.add_argument("--binary", required=True, help="AArch64 static ELF path")
    parser.add_argument(
        "--cores",
        type=int,
        default=1,
        help="Number of O3 cores; default preserves the single-core proxy",
    )
    parser.add_argument(
        "--pair-shared-div",
        action="store_true",
        help=(
            "For a two-core distributed-IQ configuration, make both private "
            "DIV IQs reference one physical 20-cycle non-pipelined divider"
        ),
    )
    parser.add_argument(
        "--pair-shared-fpsimd",
        action="store_true",
        help=(
            "For a two-core distributed-IQ configuration, "
            "share one FP/SIMD execution backend"
        ),
    )
    parser.add_argument(
        "--cache-prefetch",
        choices=("stride", "off"),
        default="stride",
        help=(
            "Stage 2M cache control: preserve historical "
            "StridePrefetcher defaults or disable cache prefetching"
        ),
    )
    parser.add_argument("--clock", default="1.4GHz")
    parser.add_argument("--width", type=int, default=3)
    parser.add_argument("--commit-width", type=int, default=3)
    parser.add_argument("--rob", type=int, default=80)
    parser.add_argument("--iq", type=int, default=40)
    parser.add_argument("--lq", type=int, default=12)
    parser.add_argument("--sq", type=int, default=16)
    parser.add_argument(
        "--n-skip",
        type=int,
        default=-1,
        help="-1 disables N-SKIP; 0 is head-only; N exposes Head..Head+N",
    )
    parser.add_argument(
        "--checker",
        action="store_true",
        help="Enable strict Arm O3 CheckerCPU validation",
    )
    parser.add_argument(
        "--distributed-iq",
        action="store_true",
        help=(
            "Use the provisional five-bank Little scheduler. "
            "Default sizes are INT0 Q10, INT1 Q6, MEM Q12, "
            "DIV Q4, FP/SIMD Q6."
        ),
    )

    parser.add_argument(
        "--dist-int0",
        type=int,
        default=10,
        metavar="N",
        help="Distributed INT0 IQ entries (default: 10)",
    )
    parser.add_argument(
        "--dist-int1",
        type=int,
        default=6,
        metavar="N",
        help="Distributed INT1 IQ entries (default: 6)",
    )
    parser.add_argument(
        "--dist-mem",
        type=int,
        default=12,
        metavar="N",
        help="Distributed MEM IQ entries (default: 12)",
    )
    parser.add_argument(
        "--dist-div",
        type=int,
        default=4,
        metavar="N",
        help="Distributed DIV IQ entries (default: 4)",
    )
    parser.add_argument(
        "--dist-fpsimd",
        type=int,
        default=6,
        metavar="N",
        help="Distributed FP/SIMD IQ entries (default: 6)",
    )
    parser.add_argument(
        "--int-steering",
        choices=[
            "first-fit",
            "least-used",
            "round-robin",
            "int1-first",
        ],
        default="first-fit",
        help=(
            "IntAlu steering between compatible distributed IQs. "
            "Default preserves legacy first-fit behavior."
        ),
    )

    parser.add_argument(
        "--local-iq-picker",
        action="store_true",
        help=(
            "Use true per-IQ bounded ready candidates with "
            "global age arbitration. Requires --distributed-iq."
        ),
    )

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
        n_skip=args.n_skip,
        checker=args.checker,
        distributed_iq=args.distributed_iq,
        int_steering=args.int_steering,
        local_iq_picker=args.local_iq_picker,
        dist_int0_entries=args.dist_int0,
        dist_int1_entries=args.dist_int1,
        dist_mem_entries=args.dist_mem,
        dist_div_entries=args.dist_div,
        dist_fpsimd_entries=args.dist_fpsimd,
        num_cores=args.cores,
        pair_shared_div=args.pair_shared_div,
        pair_shared_fpsimd=args.pair_shared_fpsimd,
    )

    # Stage 2M control hierarchy.
    #
    # The topology is unchanged from PrivateL1SharedL2CacheHierarchy.
    # Historical implicit gem5 defaults are made explicit so each
    # memory-hierarchy variable can later be changed independently.
    #
    # None of these timing/MSHR/interconnect values are architecturally
    # frozen yet.
    cache_hierarchy = LittleExplicitCacheHierarchy(
        l1d_size="64KiB",
        l1i_size="64KiB",
        l2_size="1MiB",
        l1d_assoc=4,
        l1i_assoc=4,
        l2_assoc=8,
        prefetch_enabled=(args.cache_prefetch == "stride"),
    )

    memory = SingleChannelDDR4_2400(size="512MiB")

    board = SimpleBoard(
        clk_freq=args.clock,
        processor=processor,
        memory=memory,
        cache_hierarchy=cache_hierarchy,
    )

    if args.cores == 1:
        board.set_se_binary_workload(
            BinaryResource(
                local_path=str(binary_path),
                architecture=ISA.ARM,
            )
        )
    else:
        board.set_se_multi_binary_workload(
            [
                BinaryResource(
                    local_path=str(binary_path),
                    architecture=ISA.ARM,
                )
                for _ in range(args.cores)
            ]
        )

    print(
        "Little v0.52 proxy:",
        f"clock={args.clock}",
        f"cores={args.cores}",
        f"pair-shared-div={args.pair_shared_div}",
        f"pair-shared-fpsimd={args.pair_shared_fpsimd}",
        f"cache-prefetch={args.cache_prefetch}",
        f"width={args.width}",
        f"commit={args.commit_width}",
        f"ROB={args.rob}",
        f"IQ={args.iq}",
        f"LQ={args.lq}",
        f"SQ={args.sq}",
        f"N-SKIP={'stock' if args.n_skip < 0 else args.n_skip}",
        f"Checker={args.checker}",
        sep="\n  ",
    )

    simulator = Simulator(board=board)
    simulator.run()

    print(
        f"SIMULATION_EXIT_CAUSE={simulator.get_last_exit_event_cause()}"
    )
    print(
        f"SIMULATION_EXIT_CODE={simulator.get_last_exit_event_code()}"
    )


if __name__ in ("__main__", "__m5_main__"):
    main()
