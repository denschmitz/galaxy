"""Measure BRIDGE-MEDIAN-001 on an immutable source; emit a bounded JSON report."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import platform
from time import perf_counter
from typing import Any

import numpy as np

from galaxy.bridge import BridgeProfile, prepare_native_presentation
from galaxy.fitsio import load_fits_plane
from galaxy.reprojection import get_system_memory_bytes


def process_memory() -> dict[str, int]:
    if platform.system() == "Windows":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                )
            ]
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        counts = Counters()
        counts.cb = ctypes.sizeof(counts)
        if not query(current(), ctypes.byref(counts), counts.cb):
            raise ctypes.WinError()
        return {"peak_working_set_bytes": int(counts.PeakWorkingSetSize),
                "working_set_bytes": int(counts.WorkingSetSize),
                "peak_commit_bytes": int(counts.PeakPagefileUsage)}
    import resource
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return {"peak_working_set_bytes": peak if platform.system() == "Darwin" else peak * 1024}


def benchmark(source: Path, output: Path) -> dict[str, Any]:
    if source.resolve() == output.resolve():
        raise ValueError("benchmark output must not overwrite the immutable source FITS")
    before = process_memory()
    started = perf_counter()
    observation = load_fits_plane(source)
    load_seconds = perf_counter() - started
    after_load = process_memory()
    result = prepare_native_presentation(observation, profile=BridgeProfile())
    after = process_memory()
    core = result.values[6025:6027, 3726:3729] if observation.data.shape == (8582, 14340) else None
    report: dict[str, Any] = {
        "source": str(source.resolve()), "source_bytes": source.stat().st_size,
        "shape": list(observation.data.shape), "platform": platform.platform(),
        "processor": platform.processor(), "system_memory_bytes": get_system_memory_bytes(),
        "load_seconds": load_seconds, "before": before, "after_load": after_load,
        "after_bridge": after, "bridge": result.diagnostics.record(),
        "pillars_core_estimates": None if core is None else core.tolist(),
        "acceptance": {
            "elapsed_limit_seconds": 60,
            "peak_limit_bytes": 6 * 1024**3,
            "elapsed_pass": result.diagnostics.elapsed_seconds <= 60,
            "peak_pass": after["peak_working_set_bytes"] <= 6 * 1024**3,
            "peak_metric": "peak_working_set_bytes (resident); commit reported separately",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = benchmark(args.source, args.output)
    print(json.dumps({"report": str(args.output), "bridge": report["bridge"],
                      "after_bridge": report["after_bridge"], "acceptance": report["acceptance"]}, indent=2))
    if not all(report["acceptance"][key] for key in ("elapsed_pass", "peak_pass")):
        raise SystemExit("native bridge resource acceptance failed")


if __name__ == "__main__":
    main()
