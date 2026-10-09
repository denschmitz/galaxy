"""Measure full native input preparation and each real resampling kernel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from benchmark_native_bridge import process_memory
from galaxy.bridge import prepare_native_presentation
from galaxy.fitsio import load_fits_plane
from galaxy.reprojection import reproject_plane


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adaptive", action="store_true")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError("benchmark output must not overwrite its immutable source")
    baseline = process_memory()
    source = load_fits_plane(args.source)
    wcs = source.wcs.deepcopy()
    # Center a 512-square output on the native Pillars six-pixel specimen.
    wcs.wcs.crpix += [256 - 3727.5, 256 - 6026]
    started = perf_counter()
    native = prepare_native_presentation(source)
    result = reproject_plane(source, wcs, (512, 512), args.adaptive, presentation=native)
    elapsed = perf_counter() - started
    memory = process_memory()
    report = {"source": str(args.source), "native_shape": list(source.data.shape),
        "output_shape": [512, 512], "adaptive": args.adaptive, "elapsed_seconds": elapsed,
        "before": baseline, "after": memory, "native": native.diagnostics.record(),
        "observed_outputs": int(result.valid.sum()),
        "presentation_outputs": int(result.presentation_valid.sum()),
        "influenced_outputs": int(result.estimate_influence.sum()),
        "limits": {"seconds": 120, "peak_resident_bytes": 16 * 1024**3}}
    report["passed"] = elapsed <= 120 and memory["peak_working_set_bytes"] <= 16 * 1024**3
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit("integrated resource budget failed")


if __name__ == "__main__":
    main()
