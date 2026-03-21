from __future__ import annotations

import argparse
from pathlib import Path
import sys

from galaxy.config import BoxRegion, CircleRegion, GalaxyConfig, load_config
from galaxy.mast import build_candidate_manifest, discover_candidates, selection_summary
from galaxy.pipeline import run_pipeline
from galaxy.selection import SelectionInputs, load_candidate_manifest, write_candidate_manifest
from galaxy.targeting import region_to_mast_shape, resolve_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="galaxy", description="JWST/HST presentation composite pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute the Galaxy pipeline")
    _add_common_config_args(run_parser)
    run_parser.add_argument("--mode", choices=["full", "download-only", "reproject-only", "compose-only"], default="full")
    run_parser.add_argument("--selection")
    _add_selection_args(run_parser)

    discover_parser = subparsers.add_parser("discover", help="Discover archive candidates without downloading")
    _add_common_config_args(discover_parser, require_workdir=False)
    discover_parser.add_argument("--out", required=True)
    _add_selection_args(discover_parser)

    reproduce_parser = subparsers.add_parser("reproduce", help="Re-run from a saved configuration")
    reproduce_parser.add_argument("--config", required=True)
    reproduce_parser.add_argument("--workdir", required=True)
    reproduce_parser.add_argument("--mode", choices=["full", "download-only", "reproject-only", "compose-only"], default="full")

    validate_parser = subparsers.add_parser("validate-config", help="Validate a Galaxy configuration file")
    validate_parser.add_argument("--config", required=True)
    return parser


def _add_common_config_args(parser: argparse.ArgumentParser, *, require_workdir: bool = True) -> None:
    parser.add_argument("--config", required=True)
    if require_workdir:
        parser.add_argument("--workdir", required=True)
    parser.add_argument("--target-name")
    parser.add_argument("--ra", type=float)
    parser.add_argument("--dec", type=float)
    parser.add_argument("--radius-arcmin", type=float)
    parser.add_argument("--box-arcmin", type=float, nargs=2, metavar=("WIDTH", "HEIGHT"))


def _add_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--include-filter", action="append", default=[])
    parser.add_argument("--include-instrument", action="append", default=[])
    parser.add_argument("--include-mission", action="append", default=[])
    parser.add_argument("--include-obsid", action="append", default=[])
    parser.add_argument("--exclude-obsid", action="append", default=[])
    parser.add_argument("--include-product", action="append", default=[])
    parser.add_argument("--exclude-product", action="append", default=[])
    strategy_group = parser.add_mutually_exclusive_group()
    strategy_group.add_argument("--latest-per-filter", action="store_true")
    strategy_group.add_argument("--deepest-per-filter", action="store_true")
    parser.add_argument("--max-per-filter", type=int)
    parser.add_argument("--max-total", type=int)
    parser.add_argument("--list-filters", action="store_true")
    parser.add_argument("--list-instruments", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        load_config(args.config)
        print(f"Configuration is valid: {args.config}")
        return 0

    if args.command == "reproduce":
        config = load_config(args.config)
        artifacts = run_pipeline(config, args.workdir, mode=args.mode, progress=lambda message: print(message), config_path=args.config)
        print(f"Artifacts written to {artifacts.workdir}")
        return 0

    config = load_config(args.config)
    config = _apply_cli_overrides(config, args)
    selection_inputs = _selection_inputs_from_args(args)

    if args.command == "discover":
        manifest = _discover_manifest(config, args.config, selection_inputs, progress=lambda message: print(message))
        write_candidate_manifest(manifest, args.out)
        _print_discovery_summary(manifest)
        print(f"Candidates written to {args.out}")
        return 0

    if args.selection:
        manifest = load_candidate_manifest(args.selection)
        if args.list_filters or args.list_instruments:
            _print_discovery_summary(manifest)
            return 0
        artifacts = run_pipeline(
            config,
            args.workdir,
            mode=args.mode,
            progress=lambda message: print(message),
            config_path=args.config,
            selection_manifest=manifest,
            selection_inputs=selection_inputs,
        )
    else:
        if args.list_filters or args.list_instruments:
            manifest = _discover_manifest(config, args.config, selection_inputs, progress=lambda message: print(message))
            _print_discovery_summary(manifest)
            return 0
        artifacts = run_pipeline(
            config,
            args.workdir,
            mode=args.mode,
            progress=lambda message: print(message),
            config_path=args.config,
            selection_inputs=selection_inputs,
        )
    print(f"Artifacts written to {artifacts.workdir}")
    return 0


def _discover_manifest(
    config: GalaxyConfig,
    config_path: str,
    selection_inputs: SelectionInputs,
    progress,
):
    resolved_target = resolve_target(config.target)
    shape_kind, shape_kwargs = region_to_mast_shape(config.target.region, resolved_target.coord)
    candidates = discover_candidates(shape_kind, shape_kwargs, config.search, progress=progress)
    return build_candidate_manifest(candidates, config.search, config_path=config_path, selection_inputs=selection_inputs)


def _selection_inputs_from_args(args: argparse.Namespace) -> SelectionInputs:
    strategy = None
    if getattr(args, "latest_per_filter", False):
        strategy = "latest_per_filter"
    elif getattr(args, "deepest_per_filter", False):
        strategy = "deepest_per_filter"
    return SelectionInputs(
        include_filters={str(item).upper() for item in getattr(args, "include_filter", [])},
        include_instruments={str(item).upper() for item in getattr(args, "include_instrument", [])},
        include_missions={str(item).upper() for item in getattr(args, "include_mission", [])},
        include_obsids={str(item) for item in getattr(args, "include_obsid", [])},
        exclude_obsids={str(item) for item in getattr(args, "exclude_obsid", [])},
        include_products={str(item).lower() for item in getattr(args, "include_product", [])},
        exclude_products={str(item).lower() for item in getattr(args, "exclude_product", [])},
        strategy=strategy,
        max_per_filter=getattr(args, "max_per_filter", None),
        max_total=getattr(args, "max_total", None),
    )


def _print_discovery_summary(manifest) -> None:
    summary = selection_summary(manifest.candidates)
    print(f"Candidate count: {summary['candidate_count']}")
    print(f"Auto-selected count: {summary['auto_selected_count']}")
    print(f"Final selected count: {summary['selected_count']}")
    if summary["filters"]:
        print(f"Filters: {', '.join(summary['filters'])}")
    if summary["instruments"]:
        print(f"Instruments: {', '.join(summary['instruments'])}")


def _apply_cli_overrides(config: GalaxyConfig, args: argparse.Namespace) -> GalaxyConfig:
    target = config.target.model_copy(deep=True)
    if args.target_name:
        target.name = args.target_name
        target.ra_deg = None
        target.dec_deg = None
        target.ra = None
        target.dec = None
    elif args.ra is not None and args.dec is not None:
        target.name = None
        target.ra_deg = args.ra
        target.dec_deg = args.dec
        target.ra = None
        target.dec = None
    if args.radius_arcmin is not None:
        target.region = CircleRegion(kind="circle", radius_arcmin=args.radius_arcmin)
    if args.box_arcmin is not None:
        target.region = BoxRegion(kind="box", width_arcmin=args.box_arcmin[0], height_arcmin=args.box_arcmin[1])
    return config.model_copy(update={"target": target})


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
