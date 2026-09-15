import argparse
from pathlib import Path

from m5.objects import ArmO3CPU, IQUnit, ArmExtension, L2XBar
from m5.objects.FUPool import FUPool
from m5.params import NULL
from m5.objects.FuncUnit import FUDesc, OpDesc

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_shared_l2_cache_hierarchy import (
    PrivateL1SharedL2CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.caches.l1icache import L1ICache
from gem5.components.cachehierarchies.classic.caches.l1dcache import L1DCache
from gem5.components.cachehierarchies.classic.caches.l2cache import L2Cache
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
    Explicit Little/LPE configuration hierarchy.

    Preserve the existing gem5 Classic private-L1/shared-L2
    topology while making memory-hierarchy proxy defaults
    explicit.

    These values are explicit Little/LPE configuration controls.
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
        l2_topology: str,
        l1d_mshrs: int,
        l2_mshrs: int,
        l1d_demand_mshr_reserve: int,
        l2_demand_mshr_reserve: int,
        l2_xbar_width: int,
        l2_xbar_header_latency: int,
        membus_width: int,
        l1d_tag_latency: int,
        l1d_data_latency: int,
        l2_tag_latency: int,
        l2_data_latency: int,
        l1d_data_banks: int,
        l1d_data_bank_service_cycles: int,
        l2_data_banks: int,
        l2_data_bank_service_cycles: int,
        prefetch_mode: str,
        prefetch_degree: int,
        prefetch_on_pf_hit: bool,
        prefetch_rate_limit: bool,
        prefetch_rate_bucket: int,
        prefetch_rate_refill_cycles: int,
    ) -> None:
        if l2_assoc <= 0:
            raise ValueError(
                "l2_assoc must be positive"
            )

        if membus_width <= 0:
            raise ValueError(
                "membus_width must be positive"
            )

        self._little_membus_width = membus_width

        super().__init__(
            l1d_size=l1d_size,
            l1i_size=l1i_size,
            l2_size=l2_size,
            l1d_assoc=l1d_assoc,
            l1i_assoc=l1i_assoc,
            l2_assoc=l2_assoc,
        )

        if l2_topology not in (
            "shared4",
            "pair2",
            "private4",
        ):
            raise ValueError(
                f"unsupported L2 topology: {l2_topology}"
            )

        if not l2_size.endswith("KiB"):
            raise ValueError(
                "l2_size must use an explicit KiB suffix"
            )

        try:
            l2_total_size_kib = int(l2_size[:-3])
        except ValueError as exc:
            raise ValueError(
                f"invalid l2_size: {l2_size}"
            ) from exc

        if l2_total_size_kib <= 0:
            raise ValueError(
                "l2 total capacity must be positive"
            )

        self._little_l2_topology = l2_topology
        self._little_l2_total_size_kib = l2_total_size_kib

        self._little_l1d_mshrs = l1d_mshrs
        self._little_l2_mshrs = l2_mshrs

        if l1d_demand_mshr_reserve < 0:
            raise ValueError(
                "l1d_demand_mshr_reserve must be non-negative"
            )

        if l2_demand_mshr_reserve < 0:
            raise ValueError(
                "l2_demand_mshr_reserve must be non-negative"
            )

        self._little_l1d_demand_mshr_reserve = (
            l1d_demand_mshr_reserve
        )

        self._little_l2_demand_mshr_reserve = (
            l2_demand_mshr_reserve
        )

        if l2_xbar_width <= 0:
            raise ValueError(
                "l2_xbar_width must be positive"
            )

        self._little_l2_xbar_width = l2_xbar_width

        if l2_xbar_header_latency <= 0:
            raise ValueError(
                "l2_xbar_header_latency must be positive"
            )

        self._little_l2_xbar_header_latency = (
            l2_xbar_header_latency
        )

        if l1d_tag_latency <= 0:
            raise ValueError(
                "l1d_tag_latency must be positive"
            )

        if l1d_data_latency <= 0:
            raise ValueError(
                "l1d_data_latency must be positive"
            )

        if l2_tag_latency <= 0:
            raise ValueError(
                "l2_tag_latency must be positive"
            )

        if l2_data_latency <= 0:
            raise ValueError(
                "l2_data_latency must be positive"
            )

        if l1d_data_banks < 0:
            raise ValueError(
                "l1d_data_banks must be non-negative"
            )

        if (
            l1d_data_banks != 0
            and (l1d_data_banks & (l1d_data_banks - 1)) != 0
        ):
            raise ValueError(
                "l1d_data_banks must be zero or a power of two"
            )

        if l1d_data_bank_service_cycles <= 0:
            raise ValueError(
                "l1d_data_bank_service_cycles must be positive"
            )

        self._little_l1d_tag_latency = l1d_tag_latency
        self._little_l1d_data_latency = l1d_data_latency

        self._little_l2_tag_latency = l2_tag_latency
        self._little_l2_data_latency = l2_data_latency

        self._little_l1d_data_banks = l1d_data_banks
        self._little_l1d_data_bank_service_cycles = (
            l1d_data_bank_service_cycles
        )

        if l2_data_banks < 0:
            raise ValueError(
                "l2_data_banks must be non-negative"
            )

        if (
            l2_data_banks != 0
            and (
                l2_data_banks
                & (l2_data_banks - 1)
            ) != 0
        ):
            raise ValueError(
                "l2_data_banks must be zero "
                "or a power of two"
            )

        if l2_data_bank_service_cycles <= 0:
            raise ValueError(
                "l2_data_bank_service_cycles "
                "must be positive"
            )

        self._little_l2_data_banks = (
            l2_data_banks
        )

        self._little_l2_data_bank_service_cycles = (
            l2_data_bank_service_cycles
        )

        if prefetch_mode not in (
            "stride",
            "off",
            "l1d",
            "l2",
        ):
            raise ValueError(
                f"unsupported cache prefetch mode: {prefetch_mode}"
            )

        self._little_prefetch_mode = prefetch_mode

        if prefetch_degree <= 0:
            raise ValueError(
                f"prefetch_degree must be positive, got {prefetch_degree}"
            )

        self._little_prefetch_degree = prefetch_degree
        self._little_prefetch_on_pf_hit = prefetch_on_pf_hit

        if prefetch_rate_bucket <= 0:
            raise ValueError(
                "prefetch_rate_bucket must be positive"
            )

        if prefetch_rate_refill_cycles <= 0:
            raise ValueError(
                "prefetch_rate_refill_cycles must be positive"
            )

        self._little_prefetch_rate_limit = (
            prefetch_rate_limit
        )

        self._little_prefetch_rate_bucket = (
            prefetch_rate_bucket
        )

        self._little_prefetch_rate_refill_cycles = (
            prefetch_rate_refill_cycles
        )

    def _configure_l1_caches(self) -> None:
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

            if self._little_prefetch_mode != "stride":
                cache.prefetcher = NULL

        # ----------------------------------------------------
        # L1D MSHR controls.
        # ----------------------------------------------------
        for cache in self.l1dcaches:
            cache.tag_latency = self._little_l1d_tag_latency
            cache.data_latency = self._little_l1d_data_latency
            cache.response_latency = 1

            cache.mshrs = self._little_l1d_mshrs
            cache.tgts_per_mshr = 20
            cache.demand_mshr_reserve = (
                self._little_l1d_demand_mshr_reserve
            )
            cache.write_buffers = 8

            cache.sequential_access = False
            cache.writeback_clean = False

            cache.data_array_banks = (
                self._little_l1d_data_banks
            )
            cache.data_array_bank_service_cycles = (
                self._little_l1d_data_bank_service_cycles
            )
            cache.data_array_bank_include_cache_origin = False

            if self._little_prefetch_mode not in (
                "stride",
                "l1d",
            ):
                cache.prefetcher = NULL
            else:
                cache.prefetcher.degree = (
                    self._little_prefetch_degree
                )
                cache.prefetcher.prefetch_on_pf_hit = (
                    self._little_prefetch_on_pf_hit
                )

                cache.prefetcher.rate_limit_enable = (
                    self._little_prefetch_rate_limit
                )
                cache.prefetcher.rate_limit_bucket_capacity = (
                    self._little_prefetch_rate_bucket
                )
                cache.prefetcher.rate_limit_refill_cycles = (
                    self._little_prefetch_rate_refill_cycles
                )

    def _configure_l2_caches(
        self,
        *,
        caches,
        mshrs_per_cache: int,
    ) -> None:
        for cache in caches:
            cache.tag_latency = self._little_l2_tag_latency
            cache.data_latency = self._little_l2_data_latency
            cache.response_latency = 1

            cache.mshrs = mshrs_per_cache
            cache.tgts_per_mshr = 12
            cache.demand_mshr_reserve = (
                self._little_l2_demand_mshr_reserve
            )
            cache.write_buffers = 8

            cache.sequential_access = False
            cache.writeback_clean = False
            cache.clusivity = "mostly_incl"

            cache.data_array_banks = (
                self._little_l2_data_banks
            )
            cache.data_array_bank_service_cycles = (
                self._little_l2_data_bank_service_cycles
            )

            # L2 requests normally originate in private L1s.
            cache.data_array_bank_include_cache_origin = True

            if self._little_prefetch_mode not in (
                "stride",
                "l2",
            ):
                cache.prefetcher = NULL
            else:
                cache.prefetcher.degree = (
                    self._little_prefetch_degree
                )
                cache.prefetcher.prefetch_on_pf_hit = (
                    self._little_prefetch_on_pf_hit
                )

    def _connect_walker_to_l2_bus(
        self,
        *,
        cpu_id: int,
        cpu,
        bus,
    ) -> None:
        walker_ports = (
            cpu.get_mmu().walkerPorts()
            if cpu.has_mmu()
            else []
        )

        if len(walker_ports) > 2:
            raise RuntimeError(
                "Unexpected number of walker ports "
                f"from CPU {cpu_id}: {len(walker_ports)}.\n"
                "Expected 0, 1, or 2"
            )

        if len(walker_ports) == 0:
            return

        cpu.connect_walker_ports(
            bus.cpu_side_ports,
            bus.cpu_side_ports,
        )

    def _incorporate_partitioned_l2(
        self,
        board,
        *,
        group_count: int,
        core_to_group,
    ) -> None:
        num_cores = board.get_processor().get_num_cores()

        if num_cores != 4:
            raise ValueError(
                f"{self._little_l2_topology} currently requires "
                f"exactly 4 cores, got {num_cores}"
            )

        if len(core_to_group) != num_cores:
            raise RuntimeError(
                "L2 topology core mapping length mismatch"
            )

        if (
            self._little_l2_total_size_kib
            % group_count
            != 0
        ):
            raise ValueError(
                "total L2 capacity must divide evenly "
                "across topology groups"
            )

        if self._little_l2_mshrs % group_count != 0:
            raise ValueError(
                "total L2 MSHR budget must divide evenly "
                "across topology groups"
            )

        # Physical L2 data-array banking is currently modeled only
        # for shared4. Partitioned topologies require banking disabled so
        # a single global bank-count budget is not duplicated per L2.
        if self._little_l2_data_banks != 0:
            raise ValueError(
                "physical L2 data-array banking is supported only "
                "for shared4; pair2/private4 require "
                "--l2-data-banks 0"
            )

        board.connect_system_port(
            self.membus.cpu_side_ports
        )

        for _, port in board.get_mem_ports():
            self.membus.mem_side_ports = port

        self.l1icaches = [
            L1ICache(
                size=self._l1i_size,
                assoc=self._l1i_assoc,
                writeback_clean=False,
            )
            for _ in range(num_cores)
        ]

        self.l1dcaches = [
            L1DCache(
                size=self._l1d_size,
                assoc=self._l1d_assoc,
            )
            for _ in range(num_cores)
        ]

        per_l2_kib = (
            self._little_l2_total_size_kib
            // group_count
        )

        self.l2buses = [
            L2XBar()
            for _ in range(group_count)
        ]

        self.l2caches = [
            L2Cache(
                size=f"{per_l2_kib}KiB",
                assoc=self._l2_assoc,
            )
            for _ in range(group_count)
        ]

        for group_id in range(group_count):
            self.l2buses[group_id].mem_side_ports = (
                self.l2caches[group_id].cpu_side
            )

            self.membus.cpu_side_ports = (
                self.l2caches[group_id].mem_side
            )

        for cpu_id, cpu in enumerate(
            board.get_processor().get_cores()
        ):
            group_id = core_to_group[cpu_id]
            bus = self.l2buses[group_id]

            cpu.connect_icache(
                self.l1icaches[cpu_id].cpu_side
            )
            cpu.connect_dcache(
                self.l1dcaches[cpu_id].cpu_side
            )

            self.l1icaches[cpu_id].mem_side = (
                bus.cpu_side_ports
            )
            self.l1dcaches[cpu_id].mem_side = (
                bus.cpu_side_ports
            )

            self._connect_walker_to_l2_bus(
                cpu_id=cpu_id,
                cpu=cpu,
                bus=bus,
            )

            if (
                board.get_processor().get_isa()
                == ISA.X86
            ):
                cpu.connect_interrupt(
                    self.membus.mem_side_ports,
                    self.membus.cpu_side_ports,
                )
            else:
                cpu.connect_interrupt()

        if board.has_coherent_io():
            self._setup_io_cache(board)

        mshrs_per_cache = (
            self._little_l2_mshrs
            // group_count
        )

        self._configure_l1_caches()

        self._configure_l2_caches(
            caches=self.l2caches,
            mshrs_per_cache=mshrs_per_cache,
        )

        for bus in self.l2buses:
            bus.width = self._little_l2_xbar_width
            bus.header_latency = (
                self._little_l2_xbar_header_latency
            )

        # Configure the common downstream memory-side interconnect.
        self.membus.width = self._little_membus_width

    def incorporate_cache(self, board) -> None:
        topology = self._little_l2_topology

        if topology == "shared4":
            # Historical shared4 path. Preserve upstream object
            # creation and port wiring exactly.
            super().incorporate_cache(board)

            self._configure_l1_caches()

            self._configure_l2_caches(
                caches=(self.l2cache,),
                mshrs_per_cache=self._little_l2_mshrs,
            )

            self.l2bus.width = self._little_l2_xbar_width
            self.l2bus.header_latency = (
                self._little_l2_xbar_header_latency
            )

            # Configure the common downstream memory-side interconnect.
            self.membus.width = self._little_membus_width
            return

        if topology == "pair2":
            self._incorporate_partitioned_l2(
                board,
                group_count=2,
                core_to_group=(0, 0, 1, 1),
            )
            return

        if topology == "private4":
            self._incorporate_partitioned_l2(
                board,
                group_count=4,
                core_to_group=(0, 1, 2, 3),
            )
            return

        raise RuntimeError(
            f"unreachable L2 topology: {topology}"
        )



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
        cache_load_ports: int,
        cache_store_ports: int,
        width: int = 3,
        fetch_width: int | None = None,
        decode_width: int | None = None,
        commit_width: int = 3,
        bp_local_size: int = 2048,
        bp_local_history_size: int = 2048,
        bp_global_size: int = 8192,
        bp_choice_size: int = 8192,
        btb_entries: int = 4096,
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
        if fetch_width is not None and fetch_width <= 0:
            raise ValueError(
                "fetch_width must be positive"
            )

        if decode_width is not None and decode_width <= 0:
            raise ValueError(
                "decode_width must be positive"
            )

        effective_fetch_width = (
            width
            if fetch_width is None
            else fetch_width
        )

        effective_decode_width = (
            width
            if decode_width is None
            else decode_width
        )

        predictor_sizes = {
            "bp_local_size": bp_local_size,
            "bp_local_history_size": bp_local_history_size,
            "bp_global_size": bp_global_size,
            "bp_choice_size": bp_choice_size,
            "btb_entries": btb_entries,
        }

        for name, value in predictor_sizes.items():
            if value <= 0:
                raise ValueError(
                    f"{name} must be positive"
                )

            if value & (value - 1):
                raise ValueError(
                    f"{name} must be a power of two"
                )

        cpu = ArmO3CPU()

        tournament = cpu.branchPred.conditionalBranchPred

        tournament.localPredictorSize = bp_local_size
        tournament.localHistoryTableSize = bp_local_history_size
        tournament.globalPredictorSize = bp_global_size
        tournament.choicePredictorSize = bp_choice_size

        cpu.branchPred.btb.numEntries = btb_entries

        cpu.fetchWidth = effective_fetch_width
        cpu.decodeWidth = effective_decode_width
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

        cpu.cacheLoadPorts = cache_load_ports
        cpu.cacheStorePorts = cache_store_ports

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
        cache_load_ports: int,
        cache_store_ports: int,
        width: int,
        fetch_width: int | None,
        decode_width: int | None,
        commit_width: int,
        bp_local_size: int,
        bp_local_history_size: int,
        bp_global_size: int,
        bp_choice_size: int,
        btb_entries: int,
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
                cache_load_ports=cache_load_ports,
                cache_store_ports=cache_store_ports,
                width=width,
                fetch_width=fetch_width,
                decode_width=decode_width,
                commit_width=commit_width,
                bp_local_size=bp_local_size,
                bp_local_history_size=bp_local_history_size,
                bp_global_size=bp_global_size,
                bp_choice_size=bp_choice_size,
                btb_entries=btb_entries,
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
        "--program-arg",
        action="append",
        default=[],
        metavar="ARG",
        help=(
            "Argument passed to the simulated single-core binary; "
            "repeat for multiple arguments"
        ),
    )
    parser.add_argument(
        "--core-binary",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Per-core AArch64 static ELF for multi-core SE; "
            "repeat exactly --cores times. "
            "If omitted, --binary is replicated to every core."
        ),
    )

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
        "--l1i-size-kib",
        type=int,
        choices=(32, 64),
        default=64,
        help=(
            "L1I capacity in KiB"
        ),
    )

    parser.add_argument(
        "--l1d-size-kib",
        type=int,
        choices=(32, 64),
        default=64,
        help=(
            "L1D capacity in KiB"
        ),
    )

    parser.add_argument(
        "--l1d-mshrs",
        type=int,
        default=16,
        help=(
            "L1D MSHR capacity"
        ),
    )
    parser.add_argument(
        "--l2-size-kib",
        type=int,
        choices=(
            1024,
            2048,
            2560,
            3072,
            3584,
            4096,
        ),
        default=1024,
        help=(
            "Total L2 capacity budget in KiB across "
            "the selected topology"
        ),
    )

    parser.add_argument(
        "--l2-assoc",
        type=int,
        default=8,
        help=(
            "L2 associativity; default 8 preserves "
            "historical cache geometry"
        ),
    )

    parser.add_argument(
        "--l2-topology",
        choices=(
            "shared4",
            "pair2",
            "private4",
        ),
        default="shared4",
        help=(
            "L2 capacity-sharing topology; "
            "shared4 preserves the historical default"
        ),
    )

    parser.add_argument(
        "--l2-mshrs",
        type=int,
        default=20,
        help=(
            "Total L2 MSHR budget across the selected topology"
        ),
    )
    parser.add_argument(
        "--l1d-demand-mshr-reserve",
        type=int,
        default=1,
        help=(
            "MSHR entries protected from new L1D prefetch admission; "
            "default 1 preserves historical behavior"
        ),
    )
    parser.add_argument(
        "--l2-demand-mshr-reserve",
        type=int,
        default=1,
        help=(
            "MSHR entries protected from new L2 prefetch admission; "
            "default 1 preserves historical behavior"
        ),
    )
    parser.add_argument(
        "--l2-xbar-width",
        type=int,
        default=32,
        help=(
            "L2-side crossbar datapath width in bytes per port; "
            "default 32 preserves historical L2XBar behavior"
        ),
    )

    parser.add_argument(
        "--l2-xbar-header-latency",
        type=int,
        default=1,
        help=(
            "L2-side crossbar header occupancy in cycles; "
            "default 1 preserves historical L2XBar behavior"
        ),
    )

    parser.add_argument(
        "--membus-width",
        type=int,
        default=64,
        help=(
            "Common downstream memory-side interconnect "
            "datapath width in bytes per port; "
            "default 64 preserves historical behavior"
        ),
    )

    parser.add_argument(
        "--cache-prefetch",
        choices=(
            "stride",
            "off",
            "l1d",
            "l2",
        ),
        default="stride",
        help=(
            "Cache-prefetch mode: "
            "stride preserves historical L1I+L1D+L2 "
            "StridePrefetcher defaults; off disables all; "
            "l1d and l2 enable only the selected data-cache level"
        ),
    )
    parser.add_argument(
        "--prefetch-degree",
        type=int,
        default=4,
        help=(
            "StridePrefetcher degree; "
            "default 4 preserves gem5 historical behavior"
        ),
    )
    parser.add_argument(
        "--prefetch-pf-hit",
        choices=("on", "off"),
        default="on",
        help=(
            "Control for "
            "StridePrefetcher.prefetch_on_pf_hit"
        ),
    )
    parser.add_argument(
        "--prefetch-rate-limit",
        choices=("on", "off"),
        default="off",
        help="Enable PF token-bucket admission control",
    )

    parser.add_argument(
        "--prefetch-rate-bucket",
        type=int,
        default=64,
        help="Prefetch token-bucket burst capacity",
    )

    parser.add_argument(
        "--prefetch-rate-refill-cycles",
        type=int,
        default=32,
        help="Cycles per replenished prefetch token",
    )

    parser.add_argument("--clock", default="1.4GHz")
    parser.add_argument("--width", type=int, default=3)

    parser.add_argument(
        "--fetch-width",
        type=int,
        default=None,
        help=(
            "Frontend fetch width; if omitted, inherit --width "
            "to preserve historical behavior"
        ),
    )

    parser.add_argument(
        "--decode-width",
        type=int,
        default=None,
        help=(
            "Frontend decode width; if omitted, inherit --width "
            "to preserve historical behavior"
        ),
    )

    parser.add_argument("--commit-width", type=int, default=3)

    parser.add_argument(
        "--bp-local-size",
        type=int,
        default=2048,
        help="TournamentBP local predictor entries",
    )

    parser.add_argument(
        "--bp-local-history-size",
        type=int,
        default=2048,
        help="TournamentBP local history table entries",
    )

    parser.add_argument(
        "--bp-global-size",
        type=int,
        default=8192,
        help="TournamentBP global predictor entries",
    )

    parser.add_argument(
        "--bp-choice-size",
        type=int,
        default=8192,
        help="TournamentBP choice predictor entries",
    )

    parser.add_argument(
        "--btb-entries",
        type=int,
        default=4096,
        help="SimpleBTB entry count",
    )

    parser.add_argument("--rob", type=int, default=80)
    parser.add_argument("--iq", type=int, default=40)
    parser.add_argument("--lq", type=int, default=12)
    parser.add_argument("--sq", type=int, default=16)

    parser.add_argument(
        "--cache-load-ports",
        type=int,
        default=200,
        help="Maximum L1D-bound load packets sent by the LSQ per cycle",
    )
    parser.add_argument(
        "--cache-store-ports",
        type=int,
        default=200,
        help="Maximum L1D-bound store packets sent by the LSQ per cycle",
    )

    parser.add_argument(
        "--l1d-tag-latency",
        type=int,
        default=1,
        help=(
            "L1D tag lookup latency in cache cycles; "
            "Explicit cache timing control"
        ),
    )

    parser.add_argument(
        "--l1d-data-latency",
        type=int,
        default=1,
        help=(
            "L1D data-array access latency in cache cycles; "
            "Explicit cache timing control"
        ),
    )

    parser.add_argument(
        "--l2-tag-latency",
        type=int,
        default=10,
        help=(
            "L2 tag lookup latency in cycles "
            "(default: 10)"
        ),
    )

    parser.add_argument(
        "--l2-data-latency",
        type=int,
        default=10,
        help=(
            "L2 data access latency in cycles "
            "(default: 10)"
        ),
    )

    parser.add_argument(
        "--l1d-data-banks",
        type=int,
        default=0,
        help=(
            "Physical L1D data-array banks; "
            "0 disables the physical L1D data-array bank model"
        ),
    )

    parser.add_argument(
        "--l1d-data-bank-service-cycles",
        type=int,
        default=1,
        help=(
            "Minimum service interval of one physical "
            "L1D data-array bank"
        ),
    )

    parser.add_argument(
        "--l2-data-banks",
        type=int,
        default=0,
        help=(
            "Physical L2 data-array banks for shared4; "
            "0 disables the model. pair2/private4 require 0"
        ),
    )

    parser.add_argument(
        "--l2-data-bank-service-cycles",
        type=int,
        default=1,
        help=(
            "Minimum service interval of one physical "
            "L2 data-array bank"
        ),
    )

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

    core_binary_paths = [
        Path(value).resolve()
        for value in args.core_binary
    ]

    if core_binary_paths:
        if args.cores == 1:
            raise ValueError(
                "--core-binary is a multi-core control; "
                "use --binary for a single core"
            )

        if len(core_binary_paths) != args.cores:
            raise ValueError(
                "--core-binary must be repeated exactly "
                f"{args.cores} times; got "
                f"{len(core_binary_paths)}"
            )

        for core_id, core_path in enumerate(
            core_binary_paths
        ):
            if not core_path.is_file():
                raise FileNotFoundError(
                    f"Core {core_id} binary not found: "
                    f"{core_path}"
                )

    processor = LittleV052ProxyProcessor(
        rob_entries=args.rob,
        iq_entries=args.iq,
        lq_entries=args.lq,
        sq_entries=args.sq,
        cache_load_ports=args.cache_load_ports,
        cache_store_ports=args.cache_store_ports,
        width=args.width,
        fetch_width=args.fetch_width,
        decode_width=args.decode_width,
        commit_width=args.commit_width,
        bp_local_size=args.bp_local_size,
        bp_local_history_size=args.bp_local_history_size,
        bp_global_size=args.bp_global_size,
        bp_choice_size=args.bp_choice_size,
        btb_entries=args.btb_entries,
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

    # Explicit cache hierarchy controls.
    #
    # shared4 preserves PrivateL1SharedL2CacheHierarchy.
    # pair2/private4 use explicit partitioned L2 wiring.
    # Historical implicit gem5 defaults are made explicit so each
    # memory-hierarchy variable can be configured independently.
    cache_hierarchy = LittleExplicitCacheHierarchy(
        l1d_size=f"{args.l1d_size_kib}KiB",
        l1i_size=f"{args.l1i_size_kib}KiB",
        l2_size=f"{args.l2_size_kib}KiB",
        l2_topology=args.l2_topology,
        l1d_assoc=4,
        l1i_assoc=4,
        l2_assoc=args.l2_assoc,
        l1d_mshrs=args.l1d_mshrs,
        l2_mshrs=args.l2_mshrs,
        l1d_demand_mshr_reserve=(
            args.l1d_demand_mshr_reserve
        ),
        l2_demand_mshr_reserve=(
            args.l2_demand_mshr_reserve
        ),
        l2_xbar_width=args.l2_xbar_width,
        l2_xbar_header_latency=(
            args.l2_xbar_header_latency
        ),
        membus_width=args.membus_width,
        l1d_tag_latency=args.l1d_tag_latency,
        l1d_data_latency=args.l1d_data_latency,
        l2_tag_latency=args.l2_tag_latency,
        l2_data_latency=args.l2_data_latency,
        l1d_data_banks=args.l1d_data_banks,
        l1d_data_bank_service_cycles=(
            args.l1d_data_bank_service_cycles
        ),
        l2_data_banks=args.l2_data_banks,
        l2_data_bank_service_cycles=(
            args.l2_data_bank_service_cycles
        ),
        prefetch_mode=args.cache_prefetch,
        prefetch_degree=args.prefetch_degree,
        prefetch_on_pf_hit=(args.prefetch_pf_hit == "on"),
        prefetch_rate_limit=(args.prefetch_rate_limit == "on"),
        prefetch_rate_bucket=args.prefetch_rate_bucket,
        prefetch_rate_refill_cycles=(
            args.prefetch_rate_refill_cycles
        ),
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
            ),
            arguments=args.program_arg,
        )
    else:
        multi_binary_paths = (
            core_binary_paths
            if core_binary_paths
            else [
                binary_path
                for _ in range(args.cores)
            ]
        )

        board.set_se_multi_binary_workload(
            [
                BinaryResource(
                    local_path=str(core_path),
                    architecture=ISA.ARM,
                )
                for core_path in multi_binary_paths
            ]
        )

    print(
        "Little v0.52 proxy:",
        f"clock={args.clock}",
        f"cores={args.cores}",
        (
            "fetch-width="
            f"{args.fetch_width if args.fetch_width is not None else args.width}"
        ),
        (
            "decode-width="
            f"{args.decode_width if args.decode_width is not None else args.width}"
        ),
        f"bp-local-size={args.bp_local_size}",
        f"bp-local-history-size={args.bp_local_history_size}",
        f"bp-global-size={args.bp_global_size}",
        f"bp-choice-size={args.bp_choice_size}",
        f"btb-entries={args.btb_entries}",
        f"pair-shared-div={args.pair_shared_div}",
        f"pair-shared-fpsimd={args.pair_shared_fpsimd}",
        f"cache-prefetch={args.cache_prefetch}",
        f"prefetch-degree={args.prefetch_degree}",
        f"prefetch-pf-hit={args.prefetch_pf_hit}",
        f"l1d-mshrs={args.l1d_mshrs}",
        f"l2-topology={args.l2_topology}",
        f"l2-assoc={args.l2_assoc}",
        f"l2-xbar-width={args.l2_xbar_width}B",
        (
            "l2-xbar-header-latency="
            f"{args.l2_xbar_header_latency}cy"
        ),
        f"membus-width={args.membus_width}B",
        f"l2-mshrs={args.l2_mshrs}",
        (
            "l1d-demand-mshr-reserve="
            f"{args.l1d_demand_mshr_reserve}"
        ),
        (
            "l2-demand-mshr-reserve="
            f"{args.l2_demand_mshr_reserve}"
        ),
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
