import json
from pathlib import Path

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.io import fits
from astropy.wcs import WCS

from galaxy.config import ExecutionConfig, GalaxyConfig
from galaxy.fitsio import FITSPlane
from galaxy.pipeline import _load_or_build_reprojected, run_pipeline
from galaxy.reprojection import REPROJECT_METHOD_INTERPOLATION, ReprojectedPlane, estimate_workspace_peak_bytes
from galaxy.selection import CandidateRecord, load_candidate_manifest


def _base_config() -> GalaxyConfig:
    return GalaxyConfig.model_validate(
        {
            "target": {"ra_deg": 10.0, "dec_deg": 20.0, "region": {"kind": "circle", "radius_arcmin": 1.0}},
            "search": {"missions": ["JWST"], "observation_selection": "latest_per_filter"},
            "canvas": {
                "center": {"mode": "resolved_target"},
                "pixel_scale_arcsec": 0.2,
                "width": 32,
                "height": 32,
                "flux_conserving": False,
            },
            "mapping": {
                "channels": {
                    "red": [{"plane": "plane_a", "weight": 1.0}],
                    "green": [{"plane": "plane_a", "weight": 1.0}],
                    "blue": [{"plane": "plane_a", "weight": 1.0}],
                }
            },
            "tone": {
                "stretch": {
                    "red": {"kind": "asinh", "parameter": 4.0},
                    "green": {"kind": "asinh", "parameter": 4.0},
                    "blue": {"kind": "asinh", "parameter": 4.0},
                },
                "percentiles": {"black": 0.0, "white": 100.0},
            },
        }
    )


def _candidate(selected: bool = True) -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand-1",
        obsid="1",
        obs_id="OBS1",
        product_filename="plane_a.fits",
        data_uri="mast:plane_a",
        mission="JWST",
        instrument="NIRCAM",
        detector="DET",
        filter_name="F200W",
        product_type="SCIENCE",
        product_version="v1",
        observation_date_start="1.0",
        observation_date_end="2.0",
        exposure_time=123.0,
        file_size=456,
        proposal_id="P1",
        proposal_title="Title",
        target_name="Target",
        selection_rank=[0, 0, [0], "plane_a.fits"],
        auto_selected=selected,
        auto_selection_reason="selected:latest_per_filter" if selected else "dropped:not_auto_selected",
        selected=selected,
        selected_reason="selected:latest_per_filter" if selected else "dropped:not_auto_selected",
    )


def _write_exported_planes(path: Path) -> None:
    header = fits.Header()
    header["PLANEID"] = "plane_a"
    header["FILTER"] = "F200W"
    header["MISSION"] = "JWST"
    header["INSTRUME"] = "NIRCAM"
    header["EXPTIME"] = 123.0
    data = np.arange(64, dtype=np.float32).reshape(8, 8)
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data=data, header=header, name="PLANEA")]).writeto(path)


def _simple_wcs() -> WCS:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10.0, 20.0]
    wcs.wcs.crpix = [2.0, 2.0]
    wcs.wcs.cdelt = [-0.0002777778, 0.0002777778]
    return wcs


def test_run_pipeline_download_only_writes_manifest_candidates_and_provenance(monkeypatch, tmp_path) -> None:
    config = _base_config()

    monkeypatch.setattr("galaxy.pipeline.discover_candidates", lambda *args, **kwargs: [_candidate(selected=True)])

    def fake_download_selected(candidates, cache_dir, progress=None):
        destination = cache_dir / "plane_a.fits"
        fits.PrimaryHDU(data=np.ones((4, 4), dtype=np.float32)).writeto(destination)
        return (
            [
                {
                    "candidate_id": candidates[0].candidate_id,
                    "product_identifier": "OBS1",
                    "stable_product_identifier": "plane_a.fits",
                    "product_filename": "plane_a.fits",
                    "filter": "F200W",
                    "product_type": "SCIENCE",
                    "product_version": "v1",
                    "selection_rank": [0, 0, [0], "plane_a.fits"],
                    "selected_reason": "selected:latest_per_filter",
                    "url": "mast:plane_a",
                    "local_path": str(destination),
                    "file_size": destination.stat().st_size,
                    "checksum": "abc123",
                    "download_timestamp": None,
                    "status": "complete",
                }
            ],
            [],
        )

    monkeypatch.setattr("galaxy.pipeline.download_selected", fake_download_selected)

    artifacts = run_pipeline(config, tmp_path, mode="download-only", config_path="config.yaml")

    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    provenance = json.loads(artifacts.provenance_path.read_text(encoding="utf-8"))
    candidates = load_candidate_manifest(tmp_path / "candidates.json")

    assert artifacts.config_path.exists()
    assert manifest[0]["candidate_id"] == "cand-1"
    assert candidates.candidates[0].selected is True
    assert provenance["selection"]["source"] == "raw_config_discovery"
    assert provenance["selection"]["policy"] == "latest_per_filter"
    assert provenance["selection"]["final_selected_candidate_ids"] == ["cand-1"]


def test_run_pipeline_compose_only_uses_exported_planes(tmp_path) -> None:
    config = _base_config()
    _write_exported_planes(tmp_path / "exported_planes.fits")

    artifacts = run_pipeline(config, tmp_path, mode="compose-only", config_path="config.yaml")
    provenance = json.loads(artifacts.provenance_path.read_text(encoding="utf-8"))

    assert artifacts.png_path is not None and artifacts.png_path.exists()
    assert artifacts.tiff_path is not None and artifacts.tiff_path.exists()
    assert provenance["reprojection"]["mode"] == "compose_only_export"


def test_run_pipeline_raises_when_no_selected_candidates(monkeypatch, tmp_path) -> None:
    config = _base_config()
    monkeypatch.setattr("galaxy.pipeline.discover_candidates", lambda *args, **kwargs: [])

    with pytest.raises(RuntimeError, match="no selected candidates"):
        run_pipeline(config, tmp_path, mode="download-only", config_path="config.yaml")


def test_load_or_build_reprojected_continues_past_bad_files_when_fail_fast_disabled(monkeypatch, tmp_path) -> None:
    config = _base_config().model_copy(update={"execution": ExecutionConfig(fail_fast=False)})
    good = tmp_path / "good.fits"
    bad = tmp_path / "bad.fits"
    good.write_text("good", encoding="utf-8")
    bad.write_text("bad", encoding="utf-8")

    def fake_load_fits_plane(path: Path) -> FITSPlane:
        if path.name == "bad.fits":
            raise ValueError("corrupt")
        return FITSPlane("good", np.ones((4, 4), dtype=np.float32), _simple_wcs(), {"filter": "F200W"})

    monkeypatch.setattr("galaxy.pipeline.load_fits_plane", fake_load_fits_plane)
    monkeypatch.setattr(
        "galaxy.pipeline.reproject_all",
        lambda planes, output_wcs, shape_out, flux_conserving, progress=None: [
            ReprojectedPlane("good", np.ones((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32), {"filter": "F200W"})
        ],
    )
    monkeypatch.setattr("galaxy.pipeline.save_reprojected_plane", lambda *args, **kwargs: None)

    result = _load_or_build_reprojected(
        config,
        SkyCoord(10 * u.deg, 20 * u.deg),
        [good, bad],
        tmp_path,
        tmp_path / "reprojected",
        "full",
        progress=None,
    )

    assert len(result.planes) == 1
    assert result.diagnostics["load_failed"] == 1
    assert result.diagnostics["first_failure"] == "bad.fits: corrupt"
    assert result.diagnostics["mode"] == "configured_canvas"
    assert result.diagnostics["width"] == config.canvas.width
    assert result.diagnostics["height"] == config.canvas.height


def test_load_or_build_reprojected_raises_when_fail_fast_enabled(monkeypatch, tmp_path) -> None:
    config = _base_config().model_copy(update={"execution": ExecutionConfig(fail_fast=True)})
    source = tmp_path / "bad.fits"
    source.write_text("bad", encoding="utf-8")

    def always_fail(path):
        raise ValueError("corrupt")

    monkeypatch.setattr("galaxy.pipeline.load_fits_plane", always_fail)

    with pytest.raises(ValueError, match="corrupt"):
        _load_or_build_reprojected(
            config,
            SkyCoord(10 * u.deg, 20 * u.deg),
            [source],
            tmp_path,
            tmp_path / "reprojected",
            "full",
            progress=None,
        )


def test_load_or_build_reprojected_warns_when_estimate_exceeds_80_percent_ram(monkeypatch, tmp_path) -> None:
    config = _base_config().model_copy(update={
        "canvas": _base_config().canvas.model_copy(update={"width": 4000, "height": 4000}),
        "execution": ExecutionConfig(fail_fast=False),
    })
    source = tmp_path / "good.fits"
    source.write_text("good", encoding="utf-8")
    messages: list[str] = []

    monkeypatch.setattr(
        "galaxy.pipeline.load_fits_plane",
        lambda path: FITSPlane("good", np.ones((4, 4), dtype=np.float32), _simple_wcs(), {"filter": "F200W"}),
    )
    monkeypatch.setattr("galaxy.pipeline.get_system_memory_bytes", lambda: 100_000_000)
    monkeypatch.setattr(
        "galaxy.pipeline.reproject_all",
        lambda planes, output_wcs, shape_out, flux_conserving, progress=None: [
            ReprojectedPlane("good", np.ones((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32), {"filter": "F200W"})
        ],
    )
    monkeypatch.setattr("galaxy.pipeline.save_reprojected_plane", lambda *args, **kwargs: None)

    result = _load_or_build_reprojected(
        config,
        SkyCoord(10 * u.deg, 20 * u.deg),
        [source],
        tmp_path,
        tmp_path / "reprojected",
        "full",
        progress=messages.append,
    )

    assert result.diagnostics["estimated_peak_bytes"] > result.diagnostics["system_memory_bytes"] * 0.8
    assert any("80% of system RAM" in message for message in messages)


def test_estimate_workspace_peak_bytes_is_deterministic_for_identical_inputs() -> None:
    estimate_a = estimate_workspace_peak_bytes(100, 3, 8, REPROJECT_METHOD_INTERPOLATION)
    estimate_b = estimate_workspace_peak_bytes(100, 3, 8, REPROJECT_METHOD_INTERPOLATION)

    assert estimate_a == estimate_b


def test_load_or_build_reprojected_logs_warning_without_progress_callback(monkeypatch, tmp_path, caplog) -> None:
    config = _base_config().model_copy(update={
        "canvas": _base_config().canvas.model_copy(update={"width": 4000, "height": 4000}),
        "execution": ExecutionConfig(fail_fast=False),
    })
    source = tmp_path / "good.fits"
    source.write_text("good", encoding="utf-8")

    monkeypatch.setattr(
        "galaxy.pipeline.load_fits_plane",
        lambda path: FITSPlane("good", np.ones((4, 4), dtype=np.float32), _simple_wcs(), {"filter": "F200W"}),
    )
    monkeypatch.setattr("galaxy.pipeline.get_system_memory_bytes", lambda: 100_000_000)
    monkeypatch.setattr(
        "galaxy.pipeline.reproject_all",
        lambda planes, output_wcs, shape_out, flux_conserving, progress=None: [
            ReprojectedPlane("good", np.ones((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32), {"filter": "F200W"})
        ],
    )
    monkeypatch.setattr("galaxy.pipeline.save_reprojected_plane", lambda *args, **kwargs: None)

    with caplog.at_level("WARNING"):
        _load_or_build_reprojected(
            config,
            SkyCoord(10 * u.deg, 20 * u.deg),
            [source],
            tmp_path,
            tmp_path / "reprojected",
            "full",
            progress=None,
        )

    assert any("80% of system RAM" in record.message for record in caplog.records)


def test_load_or_build_reprojected_records_full_configured_canvas_provenance(monkeypatch, tmp_path) -> None:
    config = _base_config().model_copy(update={
        "canvas": _base_config().canvas.model_copy(update={
            "projection": "TAN",
            "rotation_deg": 12.5,
            "flux_conserving": False,
        })
    })
    good = tmp_path / "good.fits"
    good.write_text("good", encoding="utf-8")

    monkeypatch.setattr(
        "galaxy.pipeline.load_fits_plane",
        lambda path: FITSPlane("good", np.ones((4, 4), dtype=np.float32), _simple_wcs(), {"filter": "F200W"}),
    )
    monkeypatch.setattr(
        "galaxy.pipeline.reproject_all",
        lambda planes, output_wcs, shape_out, flux_conserving, progress=None: [
            ReprojectedPlane("good", np.ones((4, 4), dtype=np.float32), np.ones((4, 4), dtype=np.float32), {"filter": "F200W"})
        ],
    )
    monkeypatch.setattr("galaxy.pipeline.save_reprojected_plane", lambda *args, **kwargs: None)

    result = _load_or_build_reprojected(
        config,
        SkyCoord(10 * u.deg, 20 * u.deg),
        [good],
        tmp_path,
        tmp_path / "reprojected",
        "full",
        progress=None,
    )

    assert result.diagnostics["projection"] == config.canvas.projection
    assert result.diagnostics["rotation_deg"] == config.canvas.rotation_deg
    assert result.diagnostics["center_mode"] == config.canvas.center.mode
    assert result.diagnostics["flux_conserving"] == config.canvas.flux_conserving
    assert result.diagnostics["reprojection_method"] == REPROJECT_METHOD_INTERPOLATION
    assert result.diagnostics["reprojection_bytes_per_pixel"] == 8
