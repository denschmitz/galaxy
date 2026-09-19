from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from galaxy.app_config import ApplicationConfigError, load_application_settings
from galaxy.logging_utils import DEFAULT_LOG_FILE_NAME, configure_logging
from galaxy.mast import build_candidate_manifest, discover_candidates, selection_summary
from galaxy.processing_config import SearchConfig
from galaxy.scene_card import load_scene
from galaxy.scene_pipeline import run_scene_pipeline
from galaxy.scene_readiness import readiness
from galaxy.selection import CandidateManifest, SelectionInputs, load_candidate_manifest, write_candidate_manifest
from galaxy.targeting import region_to_mast_shape, resolve_target


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="galaxy", description="JWST/HST presentation composite pipeline")
    parser.add_argument("--scene-dir", help="Override the scene library directory for this invocation")
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="Execute exact products and settings from a JSON scene card")
    _add_scene_run_args(run_parser)
    reproduce = commands.add_parser("reproduce", help="Re-run a JSON scene card")
    _add_scene_run_args(reproduce)

    discover = commands.add_parser("discover", help="Discover archive candidates from scene search inputs")
    discover.add_argument("--scene", required=True)
    discover.add_argument("--out", required=True)
    _add_selection_args(discover)

    validate = commands.add_parser("validate-scene", help="Validate a JSON scene card")
    validate.add_argument("--scene", required=True)
    for command in (run_parser, reproduce, discover, validate):
        command.add_argument("--scene-dir", default=argparse.SUPPRESS,
                             help="Override the scene library directory for this invocation")
    return parser


def _add_scene_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scene", required=True)
    parser.add_argument("--workdir", help="Dedicated child directory of the scene-card directory")
    parser.add_argument("--mode", choices=["full", "download-only", "reproject-only", "compose-only"], default="full")
    parser.add_argument("--selection", help="Optional manifest whose selected IDs must match the scene pins")


def _add_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--include-filter", action="append", default=[])
    parser.add_argument("--include-instrument", action="append", default=[])
    parser.add_argument("--include-mission", action="append", default=[])
    parser.add_argument("--include-obsid", action="append", default=[])
    parser.add_argument("--exclude-obsid", action="append", default=[])
    parser.add_argument("--include-product", action="append", default=[])
    parser.add_argument("--exclude-product", action="append", default=[])
    strategy = parser.add_mutually_exclusive_group()
    strategy.add_argument("--latest-per-filter", action="store_true")
    strategy.add_argument("--deepest-per-filter", action="store_true")
    parser.add_argument("--max-per-filter", type=int)
    parser.add_argument("--max-total", type=int)
    parser.add_argument("--list-filters", action="store_true")
    parser.add_argument("--list-instruments", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.application_settings = load_application_settings(args.scene_dir)
    except ApplicationConfigError as exc:
        parser.error(str(exc))
    _configure_initial_logging(args)

    card = load_scene(args.scene)
    if args.command == "validate-scene":
        logger.info("Scene card is structurally valid: %s", args.scene)
        print(f"Scene card is structurally valid: {args.scene}")
        return 0

    if args.command == "discover":
        problems = readiness(card, "discovery")
        if problems:
            parser.error("\n".join(f"{item.path}: [{item.code}] {item.message}" for item in problems))
        if card.target is None or card.target.region is None:
            parser.error("discovery requires target coordinates and a region")
        target = resolve_target(card.target)
        shape_kind, shape_kwargs = region_to_mast_shape(card.target.region, target.coord)
        search = SearchConfig.model_validate({
            "missions": [], "instruments": [], "detectors": [], "filters": [], "product_types": [],
            "observation_selection": "all", "max_observations_per_filter": 1,
            **(card.search.model_dump(mode="json", exclude_unset=True) if card.search else {}),
        })
        candidates = discover_candidates(shape_kind, shape_kwargs, search)
        manifest = build_candidate_manifest(
            candidates, search, config_path=str(Path(args.scene).resolve()),
            selection_inputs=_selection_inputs_from_args(args),
        )
        write_candidate_manifest(manifest, args.out)
        _print_discovery_summary(manifest)
        print(f"Candidates written to {args.out}")
        return 0

    if args.selection:
        _verify_selection_manifest(card, load_candidate_manifest(args.selection), parser)
    result = run_scene_pipeline(args.scene, args.workdir, mode=args.mode)
    logger.info("Artifacts written to %s", result.artifacts.workdir)
    print(f"Artifacts written to {result.artifacts.workdir}")
    return 0


def _configure_initial_logging(args: argparse.Namespace) -> None:
    if args.command == "discover":
        log_dir = Path(args.out).parent
    elif args.command in ("run", "reproduce") and args.workdir:
        log_dir = Path(args.workdir)
    else:
        log_dir = Path(args.scene).parent
    configure_logging(log_path=log_dir / DEFAULT_LOG_FILE_NAME)


def _selection_inputs_from_args(args: argparse.Namespace) -> SelectionInputs:
    strategy = "latest_per_filter" if args.latest_per_filter else "deepest_per_filter" if args.deepest_per_filter else None
    return SelectionInputs(
        include_filters={str(item).upper() for item in args.include_filter},
        include_instruments={str(item).upper() for item in args.include_instrument},
        include_missions={str(item).upper() for item in args.include_mission},
        include_obsids={str(item) for item in args.include_obsid},
        exclude_obsids={str(item) for item in args.exclude_obsid},
        include_products={str(item).lower() for item in args.include_product},
        exclude_products={str(item).lower() for item in args.exclude_product},
        strategy=strategy,
        max_per_filter=args.max_per_filter,
        max_total=args.max_total,
    )


def _verify_selection_manifest(card, manifest: CandidateManifest, parser: argparse.ArgumentParser) -> None:
    selected = {candidate.candidate_id for candidate in manifest.candidates if candidate.selected}
    pinned = set(card.selection.selected_product_ids if card.selection else [])
    if selected != pinned:
        parser.error(
            "selection manifest differs from exact scene-card pins; update and save the scene card before execution"
        )


def _print_discovery_summary(manifest: CandidateManifest) -> None:
    summary = selection_summary(manifest.candidates)
    print(f"Candidate count: {summary['candidate_count']}")
    print(f"Auto-selected count: {summary['auto_selected_count']}")
    print(f"Final selected count: {summary['selected_count']}")
    if summary["filters"]:
        print(f"Filters: {', '.join(summary['filters'])}")
    if summary["instruments"]:
        print(f"Instruments: {', '.join(summary['instruments'])}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
