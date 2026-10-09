import json
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from galaxy.checkpoints import (
    CheckpointValidationError,
    build_producer_inputs,
    canonical_json_bytes,
    checkpoint_manifest_path,
    load_validated_checkpoint,
    producer_dependency_key,
    write_checkpoint_manifest,
)
from galaxy.planes import export_multiplane_fits, load_multiplane_records
from galaxy.processing_config import GalaxyConfig
from galaxy.reprojection import ReprojectedPlane


def _config() -> GalaxyConfig:
    return GalaxyConfig.model_validate({
        "target": {"name": "test", "region": {"kind": "circle", "radius_arcmin": 1.0}},
        "canvas": {
            "center": {"mode": "explicit", "ra_deg": 10.0, "dec_deg": 20.0},
            "projection": "TAN", "pixel_scale_arcsec": 1.0,
            "width": 4, "height": 4, "rotation_deg": 0.0,
            "flux_conserving": False,
        },
        "planes": {"enabled_filters": ["F200W"], "export_multiplane_fits": True},
        "mapping": {"planes": [{"plane": "plane-a", "rgb": {"red": 1.0}}]},
        "tone": {
            "stretch": {channel: {"kind": "gamma", "parameter": 1.0}
                        for channel in ("red", "green", "blue")},
            "percentiles": {"black": 0.0, "white": 100.0},
        },
    })


def _wcs() -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [2.0, 2.0]
    wcs.wcs.cdelt = [-1.0 / 3600.0, 1.0 / 3600.0]
    return wcs


def _plane(branch: str = "original") -> ReprojectedPlane:
    coverage = np.ones((4, 4), dtype=np.float32)
    coverage[3, 3] = 0.0
    valid = coverage > 0
    return ReprojectedPlane(
        "plane-a",
        np.arange(16, dtype=np.float32).reshape(4, 4),
        coverage,
        {"filter": "F200W", "native_unit": "MJy/sr", "artifact_branch": branch},
        wcs=_wcs(),
        valid=valid,
        branch=branch,
        source_ids=("source-a",),
        parent_ids=("native-a",),
    )


def _checkpoint(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    source = tmp_path / "source.fits"
    source.write_bytes(b"source-content")
    fits_path = export_multiplane_fits([_plane()], tmp_path / "aligned.fits")
    producer_inputs = build_producer_inputs(
        _config(), [source], "original", resolved_center_deg=(10.0, 20.0)
    )
    manifest_path = write_checkpoint_manifest(
        [_plane()], fits_path, producer_inputs, "original",
        resolved_settings={"width": 4, "height": 4},
    )
    return fits_path, manifest_path, producer_inputs


def test_canonical_dependency_key_excludes_downstream_mapping_and_tone(tmp_path: Path) -> None:
    source = tmp_path / "source.fits"
    source.write_bytes(b"source-content")
    first = _config()
    second_data = first.model_dump(mode="json")
    second_data["mapping"]["planes"][0]["rgb"] = {"red": 0.0, "green": 1.0, "blue": 0.0}
    second_data["tone"]["percentiles"] = {"black": 5.0, "white": 95.0}
    second = GalaxyConfig.model_validate(second_data)

    first_inputs = build_producer_inputs(first, [source], "original", resolved_center_deg=(10.0, 20.0))
    second_inputs = build_producer_inputs(second, [source], "original", resolved_center_deg=(10.0, 20.0))

    assert canonical_json_bytes(first_inputs) == canonical_json_bytes(second_inputs)
    assert producer_dependency_key(first_inputs) == producer_dependency_key(second_inputs)


def test_checkpoint_round_trip_preserves_validity_lineage_and_allows_renamed_pair(tmp_path: Path) -> None:
    fits_path, manifest_path, producer_inputs = _checkpoint(tmp_path)
    renamed_fits = tmp_path / "renamed-stack.fits"
    renamed_manifest = tmp_path / "renamed-manifest.json"
    fits_path.rename(renamed_fits)
    manifest_path.rename(renamed_manifest)

    manifest, planes = load_validated_checkpoint(
        renamed_fits, renamed_manifest, producer_inputs, "original"
    )

    assert manifest.output.byte_count == renamed_fits.stat().st_size
    assert planes[0].source_ids == ("source-a",)
    assert planes[0].parent_ids == ("native-a",)
    assert planes[0].valid[3, 3] == np.bool_(False)
    assert planes[0].branch == "original"


def test_checkpoint_rejects_changed_source_canvas_and_branch(tmp_path: Path) -> None:
    fits_path, manifest_path, producer_inputs = _checkpoint(tmp_path)
    source = tmp_path / "changed-source.fits"
    source.write_bytes(b"changed-source-content")
    changed_source = build_producer_inputs(
        _config(), [source], "original", resolved_center_deg=(10.0, 20.0)
    )
    changed_canvas_config = _config().model_copy(deep=True)
    changed_canvas_config.canvas.width = 5
    changed_canvas = build_producer_inputs(
        changed_canvas_config, [tmp_path / "source.fits"], "original",
        resolved_center_deg=(10.0, 20.0),
    )

    for requested, branch in (
        (changed_source, "original"),
        (changed_canvas, "original"),
        (producer_inputs, "deconvolved"),
    ):
        with pytest.raises(CheckpointValidationError):
            load_validated_checkpoint(fits_path, manifest_path, requested, branch)


def test_checkpoint_key_changes_with_validity_algorithm_and_kernel_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.fits"
    source.write_bytes(b"source-content")
    kernel = tmp_path / "kernel.fits"
    kernel.write_bytes(b"kernel-one")
    data = _config().model_dump(mode="json")
    data["psf"] = {
        "enabled": True,
        "per_plane": {
            "plane-a": {
                "enabled": True,
                "kernel_path": str(kernel),
                "max_iterations": 5,
                "regularization": 0.1,
            }
        },
    }
    config = GalaxyConfig.model_validate(data)
    first = build_producer_inputs(
        config, [source], "deconvolved", resolved_center_deg=(10.0, 20.0)
    )
    changed_validity = json.loads(json.dumps(first))
    changed_validity["native_validity"]["algorithm_version"] = "fits-validity-v2"
    kernel.write_bytes(b"kernel-two")
    changed_kernel = build_producer_inputs(
        config, [source], "deconvolved", resolved_center_deg=(10.0, 20.0)
    )

    assert producer_dependency_key(changed_validity) != producer_dependency_key(first)
    assert producer_dependency_key(changed_kernel) != producer_dependency_key(first)


def test_checkpoint_rejects_corrupt_output_and_self_inconsistent_key(tmp_path: Path) -> None:
    fits_path, manifest_path, producer_inputs = _checkpoint(tmp_path)
    original_bytes = fits_path.read_bytes()
    fits_path.write_bytes(original_bytes[:-1] + bytes([original_bytes[-1] ^ 0xFF]))

    with pytest.raises(CheckpointValidationError, match="integrity digest"):
        load_validated_checkpoint(fits_path, manifest_path, producer_inputs, "original")

    fits_path.write_bytes(original_bytes)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["producer_inputs"]["enabled_filters"] = ["F444W"]
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CheckpointValidationError, match="self-inconsistent"):
        load_validated_checkpoint(fits_path, manifest_path, producer_inputs, "original")


def test_checkpoint_rejects_plane_summary_mismatch(tmp_path: Path) -> None:
    fits_path, manifest_path, producer_inputs = _checkpoint(tmp_path)
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["planes"][0]["valid_count"] -= 1
    manifest_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CheckpointValidationError, match="summary mismatch"):
        load_validated_checkpoint(fits_path, manifest_path, producer_inputs, "original")


def test_checkpoint_publication_rejects_incompatible_plane_grids(tmp_path: Path) -> None:
    source = tmp_path / "source.fits"
    source.write_bytes(b"source-content")
    first = _plane()
    shifted_wcs = _wcs()
    shifted_wcs.wcs.crval = [11.0, 20.0]
    second = ReprojectedPlane(
        "plane-b",
        np.ones((4, 4), dtype=np.float32),
        np.ones((4, 4), dtype=np.float32),
        {"filter": "F444W", "artifact_branch": "original"},
        wcs=shifted_wcs,
        source_ids=("source-b",),
        parent_ids=("native-b",),
    )
    fits_path = export_multiplane_fits([first, second], tmp_path / "mixed-grid.fits")
    producer_inputs = build_producer_inputs(
        _config(), [source], "original", resolved_center_deg=(10.0, 20.0)
    )

    with pytest.raises(ValueError, match="share one grid"):
        write_checkpoint_manifest(
            [first, second], fits_path, producer_inputs, "original",
            resolved_settings={"width": 4, "height": 4},
        )


def test_legacy_fits_is_inspectable_but_not_certified_for_reuse(tmp_path: Path) -> None:
    fits_path = export_multiplane_fits([_plane()], tmp_path / "legacy.fits")
    assert load_multiplane_records(fits_path)[0].plane_id == "plane-a"
    assert not checkpoint_manifest_path(fits_path).exists()

    with pytest.raises(CheckpointValidationError, match="missing checkpoint manifest"):
        load_validated_checkpoint(fits_path, checkpoint_manifest_path(fits_path), {}, "original")
