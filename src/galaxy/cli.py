from __future__ import annotations

import argparse
import sys

from galaxy.config import BoxRegion, CircleRegion, GalaxyConfig, load_config
from galaxy.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="galaxy", description="JWST/HST presentation composite pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute the Galaxy pipeline")
    _add_common_config_args(run_parser)
    run_parser.add_argument("--mode", choices=["full", "download-only", "reproject-only", "compose-only"], default="full")

    reproduce_parser = subparsers.add_parser("reproduce", help="Re-run from a saved configuration")
    reproduce_parser.add_argument("--config", required=True)
    reproduce_parser.add_argument("--workdir", required=True)
    reproduce_parser.add_argument("--mode", choices=["full", "download-only", "reproject-only", "compose-only"], default="full")

    validate_parser = subparsers.add_parser("validate-config", help="Validate a Galaxy configuration file")
    validate_parser.add_argument("--config", required=True)
    return parser


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--target-name")
    parser.add_argument("--ra", type=float)
    parser.add_argument("--dec", type=float)
    parser.add_argument("--radius-arcmin", type=float)
    parser.add_argument("--box-arcmin", type=float, nargs=2, metavar=("WIDTH", "HEIGHT"))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        load_config(args.config)
        print(f"Configuration is valid: {args.config}")
        return 0

    if args.command == "reproduce":
        config = load_config(args.config)
        artifacts = run_pipeline(config, args.workdir, mode=args.mode, progress=lambda message: print(message))
        print(f"Artifacts written to {artifacts.workdir}")
        return 0

    config = load_config(args.config)
    config = _apply_cli_overrides(config, args)
    artifacts = run_pipeline(config, args.workdir, mode=args.mode, progress=lambda message: print(message))
    print(f"Artifacts written to {artifacts.workdir}")
    return 0


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
