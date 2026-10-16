"""Little v0.52 G0 constructed-FU audit (source-level SimObjects only).

Must run before gem5 instantiation. This is distinct from runtime config.ini
and C++ FU inventory verification. Never equate class names to real silicon PPA.
"""
from __future__ import annotations

import json


def _bool(value, label):
    s = str(value).strip().lower()
    if s not in ("true", "false", "0", "1"):
        raise RuntimeError(f"G0 ambiguous effective bool {label}={value!r}")
    return s in ("true", "1")


def _int(value, label):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"G0 ambiguous integer {label}={value!r}") from exc


def _effective_wake(pool, label):
    keys = (
        "reactivePowerGating",
        "predictiveWakeEnabled",
        "rawPredictiveWakeEnabled",
        "powerWakeLatency",
        "powerIdleThreshold",
    )
    result = {}
    for key in keys:
        raw = getattr(pool, key)
        if key in keys[:3]:
            result[key] = _bool(raw, label + "." + key)
        else:
            result[key] = _int(raw, label + "." + key)
    return result


def verify_g0_constructed(cores, mode, expect_fp_shared=False):
    if mode not in ("private2", "shared1") or len(cores) != 2:
        raise RuntimeError("G0 construction audit requires exactly two cores")
    fu_sources = []
    div_pools, fp_pools = [], []
    all_pools = []
    for core_id, core in enumerate(cores):
        iqs = core.get_simobject().instQueues
        if len(iqs) != 5:
            raise RuntimeError(f"G0 expected five private IQs/core, got {len(iqs)}")
        div_pools.append(iqs[3].fuPool)
        fp_pools.append(iqs[4].fuPool)
        for iq_idx, iq in enumerate(iqs):
            pool = iq.fuPool
            label = f"core{core_id}.iq{iq_idx}"
            wake = _effective_wake(pool, label)
            if wake != {
                "reactivePowerGating": False,
                "predictiveWakeEnabled": False,
                "rawPredictiveWakeEnabled": False,
                "powerWakeLatency": 0,
                "powerIdleThreshold": 8,
            }:
                raise RuntimeError(f"G0 disabled-state contract violated: {label}: {wake}")
            all_pools.append({"core": core_id, "iq": iq_idx, "wake": wake})
    shared_expected = mode == "shared1"
    if (div_pools[0] is div_pools[1]) != shared_expected:
        raise RuntimeError("G0 pair-shared DIV Python SimObject ownership mismatch")
    if (fp_pools[0] is fp_pools[1]) != expect_fp_shared:
        raise RuntimeError("G0 FP/SIMD ownership differs from explicit selector")
    for pool in div_pools:
        if len(pool.FUList) != 1 or _int(pool.FUList[0].count, "DIV.count") != 1:
            raise RuntimeError("G0 DIV effective count must be one per pool")
        ops = pool.FUList[0].opList
        if len(ops) != 1 or not str(ops[0].opClass).endswith("IntDiv"):
            raise RuntimeError("G0 divider operation class differs")
        if _int(ops[0].opLat, "DIV.latency") != 20 or _bool(
            ops[0].pipelined, "DIV.pipelined"
        ):
            raise RuntimeError("G0 DIV must be non-pipelined latency20 II20")
        if _bool(pool.pairRrArb, "DIV.pairRrArb") != shared_expected:
            raise RuntimeError("G0 DIV pair arbitration mismatch")
    physical_total = 1 if shared_expected else 2

    # Unique pools by Python identity, with explicit core ownership.  The
    # FUDesc class's capability list records coupling across OpClasses.
    unique = {}
    for core_id, core in enumerate(cores):
        for iq_index, iq in enumerate(core.get_simobject().instQueues):
            pool = iq.fuPool
            key = id(pool)
            if key not in unique:
                unique[key] = {"pool": pool, "owners": [], "iq_index": iq_index}
            unique[key]["owners"].append(core_id)
    for item in unique.values():
        pool = item["pool"]
        owners = item["owners"]
        shared = len(owners) > 1
        for desc in pool.FUList:
            number = _int(desc.count, "FU count")
            ops = [str(op.opClass) for op in desc.opList]
            if number <= 0 or not ops:
                raise RuntimeError("G0 invalid FU descriptor count/ops")
            for op in desc.opList:
                latency = _int(op.opLat, "FU opLat")
                pipelined = _bool(op.pipelined, "FU pipelined")
                fu_sources.append({
                    "opClass": str(op.opClass),
                    "supported_operations": ops,
                    "fu_class": type(desc).__name__,
                    "fu_count_per_core": None if shared else number,
                    "fu_count_per_pair": number if shared else number * 2,
                    "latency_cycles": latency,
                    "initiation_interval_cycles": 1 if pipelined else latency,
                    "pipelined": pipelined,
                    "physical_ownership": ("pair" if shared else f"core{owners[0]}"),
                    "shared_fu_domain": type(desc).__name__ if shared else None,
                    "cross_op_resource_coupling": ops,
                    "arbitration_policy": (
                        "pair-round-robin" if _bool(pool.pairRrArb, "RR") else
                        "private-no-pair-RR"
                    ),
                    "dynamic_executed_op_count": None,
                    "dynamic_count_status": "OPEN_REQUIRES_RUNTIME_STATS",
                })
    manifest = {
        "contract": "G0-A constructed-FU audit v2",
        "mode": mode,
        "construction_only": True,
        "runtime_config_ini_and_cpp_instances_verified": False,
        "wake_controls_effective": all_pools,
        "div_pair_physical_count_expected": physical_total,
        "div_python_shared_pool": shared_expected,
        "fp_python_shared_pool": expect_fp_shared,
        "fpu_domain_scope": (
            "FULL_PAIR_SHARED_FP_SIMD" if expect_fp_shared
            else "PRIVATE_FP_SIMD_NOT_FMA_ONLY"
        ),
        "fpu_capability_manifest": [
            row for row in fu_sources
            if row["opClass"].startswith(("Float", "Bf16", "Simd", "Matrix"))
        ],
    }
    print("G0_CONSTRUCTED_MANIFEST_JSON=" + json.dumps(manifest, sort_keys=True))
    print(
        f"G0_DIV_STRUCTURE_ASSERT: mode={mode} "
        f"pair_physical_divs_expected={physical_total} "
        f"shared_pool={shared_expected} latency=20 II=20 "
        "pipelined=False reactivePowerGating=False "
        "predictiveWakeEnabled=False rawPredictiveWakeEnabled=False "
        "powerWakeLatency=0"
    )
    return manifest
