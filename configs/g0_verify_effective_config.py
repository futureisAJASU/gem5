#!/usr/bin/env python3
"""Fail-closed G0-A post-run evidence gate.

Requires actual gem5 config.ini AND opt-in post-construction C++ inventory.
The three reactive counters are mandatory for the instrumented shared-DIV
pool, never silently assumed zero. Does NOT assert a paper-ready ROI.
"""
from __future__ import annotations

import argparse
import configparser
import json
import re
from pathlib import Path

FU_LOG = re.compile(
    r"^G0_CXX_FU_POOL name=(\S+) physical_units=(\d+) "
    r"pair_rr=([01]) reactive=([01]) decode=([01]) raw=([01]) "
    r"latency=(\d+) threshold=(\d+)\s*$", re.MULTILINE
)
IQ3 = re.compile(r"(?:^|\.)instQueues(?:3|\[3\])$")
EXPECTED_DISABLED = {
    "reactivePowerGating": "false",
    "predictiveWakeEnabled": "false",
    "rawPredictiveWakeEnabled": "false",
    "powerWakeLatency": "0",
    "powerIdleThreshold": "8",
}
METRICS = (
    "reactiveSleepTransitions",
    "reactiveWakingSamples",
    "reactivePowerBlockedRequests",
)


def split_refs(value: str) -> list[str]:
    return [x for x in re.split(r"[,\s]+", value.strip()) if x]


def parse_config(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None, strict=True)
    cfg.optionxform = str
    with path.open(encoding="utf-8") as fh:
        cfg.read_file(fh)
    return cfg


def audit_run(root: Path, mode: str) -> dict:
    if mode not in ("private2", "shared1"):
        raise ValueError("mode must be private2 or shared1")
    cfg = parse_config(root / "config.ini")
    log = (root / "simulator.log").read_text(encoding="utf-8", errors="replace")
    stats = (root / "stats.txt").read_text(encoding="utf-8", errors="replace")

    iq3_names = sorted(x for x in cfg.sections() if IQ3.search(x))
    if len(iq3_names) != 2:
        raise RuntimeError(
            f"expected exactly two private core DIV IQs, got {iq3_names}"
        )
    pool_refs = []
    for iq in iq3_names:
        if not cfg.has_option(iq, "fuPool"):
            raise RuntimeError(f"DIV IQ has no fuPool: {iq}")
        name = cfg.get(iq, "fuPool")
        if not cfg.has_section(name):
            raise RuntimeError(f"referenced pool missing from config.ini: {name}")
        pool_refs.append(name)

    if (pool_refs[0] == pool_refs[1]) != (mode == "shared1"):
        raise RuntimeError(f"G0-DIV pool aliases do not match mode: {pool_refs}")

    # All FU pools, including FP/SIMD, must have power control disabled.
    every_pool = [s for s in cfg.sections() if cfg.get(s, "type", fallback="") == "FUPool"]
    if len(every_pool) < 1:
        raise RuntimeError("no generated FUPool sections in config.ini")
    wake_proof = []
    for name in every_pool:
        for flag, wanted in EXPECTED_DISABLED.items():
            actual = cfg.get(name, flag, fallback=None)
            if actual is None or actual.lower() != wanted:
                raise RuntimeError(
                    f"G0 effective gating FAIL: pool={name} {flag}={actual}; expected={wanted}"
                )
        wake_proof.append(name)

    cpp = {}
    for m in FU_LOG.finditer(log):
        name = m.group(1)
        if name in cpp:
            raise RuntimeError(f"duplicate opt-in C++ FU inventory: {name}")
        cpp[name] = {
            "physical_units": int(m.group(2)),
            "pair_rr": int(m.group(3)),
            "reactive": int(m.group(4)),
            "decode": int(m.group(5)),
            "raw": int(m.group(6)),
            "latency": int(m.group(7)),
            "threshold": int(m.group(8)),
        }
    if not cpp:
        raise RuntimeError("C++ post-construction G0_CXX_FU_POOL inventory absent; rebuild and export env")

    descs = []
    for name in set(pool_refs):
        if name not in cpp:
            raise RuntimeError(f"DIV pool missing C++ inventory: {name}")
        data = cpp[name]
        if (data["physical_units"], data["pair_rr"],
            data["reactive"], data["decode"], data["raw"],
            data["latency"], data["threshold"]) != (
                1, int(mode == "shared1"), 0, 0, 0, 0, 8
            ):
            raise RuntimeError(f"actual C++ DIV FU count/policy mismatch: {name} {data}")
        refs = split_refs(cfg.get(name, "FUList", fallback=""))
        if len(refs) != 1:
            raise RuntimeError(f"DIV FUList not exactly one descriptor: {name} {refs}")
        desc = refs[0]
        if not cfg.has_section(desc) or cfg.get(desc, "count", fallback="") != "1":
            raise RuntimeError(f"DIV descriptor count != 1: {desc}")
        ops = split_refs(cfg.get(desc, "opList", fallback=""))
        if len(ops) != 1 or not cfg.has_section(ops[0]):
            raise RuntimeError(f"DIV descriptor opList invalid: {desc}")
        op = ops[0]
        if (
            cfg.get(op, "opClass", fallback="") != "IntDiv"
            or cfg.get(op, "opLat", fallback="") != "20"
            or cfg.get(op, "pipelined", fallback="").lower() != "false"
        ):
            raise RuntimeError(f"DIV actual capability or latency mismatch: {op}")
        descs.append({"pool": name, "fu_desc": desc, "op": op, **data})

    # The shared instrumentation must actually export all three counters.
    counter_coverage = {}
    for name in set(pool_refs):
        per_pool = {}
        for metric in METRICS:
            key = name + "." + metric
            hits = re.findall(
                r"^" + re.escape(key) + r"\s+(\S+)", stats, flags=re.MULTILINE
            )
            if len(hits) > 1:
                raise RuntimeError(f"ambiguous stat {key}: {hits}")
            if mode == "shared1":
                if len(hits) != 1:
                    raise RuntimeError(f"shared pool wake counter UNOBSERVED: {key}")
                try:
                    value = float(hits[0])
                except ValueError as e:
                    raise RuntimeError(f"nonnumeric counter {key}: {hits}") from e
                if value != 0:
                    raise RuntimeError(f"G0 shared wake counter nonzero: {key}={value}")
                per_pool[metric] = value
            else:
                per_pool[metric] = (
                    "UNOBSERVED" if not hits else hits[0]
                )
        counter_coverage[name] = per_pool

    manifest_rows = re.findall(
        r"^G0_CONSTRUCTED_MANIFEST_JSON=(\{.*\})$", log, re.MULTILINE
    )
    if len(manifest_rows) != 1:
        raise RuntimeError("constructed capability manifest missing/duplicated")
    construction = json.loads(manifest_rows[0])
    if construction.get("mode") != mode:
        raise RuntimeError("constructed manifest mode differs")
    if construction.get("runtime_config_ini_and_cpp_instances_verified") is not False:
        raise RuntimeError("constructed manifest must not self-certify runtime")
    if len(construction.get("fpu_capability_manifest", [])) == 0:
        raise RuntimeError("FP/SIMD capability manifest is empty")
    output = {
        "status": "G0_A_CONFIG_AND_POWER_DISABLED_VERIFIED_NOT_PERFORMANCE",
        "mode": mode,
        "div_core_iq_names": iq3_names,
        "div_pools": pool_refs,
        "pair_div_physical_units": len(set(pool_refs)),
        "constructed_cpp_div_inventories": descs,
        "all_pool_wake_disabled": wake_proof,
        "wake_counter_coverage": counter_coverage,
        "fp_simd_manifest": construction["fpu_capability_manifest"],
        "dynamic_fu_operation_counters": "OPEN",
        "common_roi_pair_makespan": "OPEN",
        "performance_measurement_acceptance": "OPEN",
    }
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--mode", choices=("private2", "shared1"), required=True)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    obj = audit_run(args.run_dir, args.mode)
    if args.json.exists():
        raise RuntimeError(f"refusing to overwrite existing evidence {args.json}")
    args.json.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    print(f"G0_EFFECTIVE_CONFIG_GATE_PASS mode={args.mode} evidence={args.json}")
    print("G0_SAME_WORK_PERFORMANCE=OPEN")


if __name__ == "__main__":
    main()
