from dataclasses import replace
import hashlib
import json
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
import pytest
from scipy import ndimage

from galaxy import bridge
from galaxy.bridge import BridgeProfile, prepare_native_presentation
from galaxy.fitsio import FITSPlane, load_fits_plane


FIXTURES = Path(__file__).parent / "fixtures" / "reprojection_bridge"


def _plane(data: np.ndarray, valid: np.ndarray | None = None) -> FITSPlane:
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [10, 20]
    wcs.wcs.crpix = [34, 34]
    wcs.wcs.cdelt = [-0.00001, 0.00001]
    return FITSPlane("synthetic", data, wcs, {"native_unit": "MJy/sr"}, valid=valid)


def _bright_core() -> FITSPlane:
    yy, xx = np.indices((67, 68))
    data = (10 + np.where((yy + xx) % 2, 1, -1)).astype(np.float32)
    component = np.zeros_like(data, dtype=bool)
    component[32:34, 32:35] = True
    ring = ndimage.binary_dilation(component, structure=np.ones((3, 3)), iterations=2) & ~component
    data[ring] = np.arange(np.count_nonzero(ring), dtype=np.float32) + 100
    data[component] = np.nan
    return _plane(data)


def test_known_answer_constant_median_and_observation_preservation() -> None:
    plane = _bright_core()
    original = plane.data.copy()
    validity, coverage, mask = plane.valid.copy(), plane.coverage.copy(), plane.mask.copy()
    result = prepare_native_presentation(plane)
    assert result.diagnostics.accepted_clusters == 1
    assert result.diagnostics.estimated_samples == 6
    assert result.diagnostics.candidate_clusters == 1
    assert result.diagnostics.rejection_counts == {}
    # A 6 x 7 dilated box minus the 2 x 3 core gives 36 samples [100,135], median 117.5.
    np.testing.assert_array_equal(result.values[32:34, 32:35], np.full((2, 3), 117.5))
    np.testing.assert_array_equal(result.values[plane.valid], original[plane.valid])
    np.testing.assert_array_equal(plane.data, original)
    np.testing.assert_array_equal(plane.valid, validity)
    np.testing.assert_array_equal(plane.coverage, coverage)
    np.testing.assert_array_equal(plane.mask, mask)
    assert result.observation is plane
    assert not np.shares_memory(result.values, plane.data)
    assert not np.any(result.estimate_mask & plane.valid)
    np.testing.assert_array_equal(result.support, plane.valid | result.estimate_mask)
    assert result.diagnostics.identity == BridgeProfile().identity()


def test_real_pillars_six_nan_core_matches_flat_fill() -> None:
    fixture = FIXTURES / "pillars_f090w_core.fits"
    metadata = json.loads((FIXTURES / "pillars_f090w_core.json").read_text())
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == metadata["fixture_sha256"]
    with fits.open(fixture) as hdul:
        assert np.count_nonzero(hdul["WHT"].data[32:34, 32:35]) == 0
        assert np.count_nonzero(hdul["CON"].data[:, 32:34, 32:35]) == 0
    plane = load_fits_plane(fixture)
    original = plane.data.copy()
    assert not plane.valid[32:34, 32:35].any()
    result = prepare_native_presentation(plane)
    assert result.diagnostics.candidate_clusters == 1
    assert result.diagnostics.accepted_clusters == 1
    assert result.diagnostics.estimated_samples == 6
    np.testing.assert_allclose(result.values[32:34, 32:35], 489.00608825683594, rtol=0, atol=3e-5)
    assert result.support[32:34, 32:35].all()
    assert not plane.valid[32:34, 32:35].any()
    np.testing.assert_array_equal(plane.data, original)
    np.testing.assert_array_equal(result.values[plane.valid], original[plane.valid])


def test_strict_off_bypasses_detector_and_uses_original_support(monkeypatch: pytest.MonkeyPatch) -> None:
    plane = _bright_core()
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Off must not invoke detection")
    monkeypatch.setattr(bridge.ndimage, "label", fail)
    result = prepare_native_presentation(plane, enabled=False)
    assert result.values is plane.data
    assert result.support is plane.valid
    assert not result.estimate_mask.any()
    assert result.diagnostics.candidate_clusters == 0
    assert result.diagnostics.enabled is False
    assert not np.isfinite(result.values[32:34, 32:35]).any()


@pytest.mark.parametrize("all_invalid", [False, True])
def test_all_valid_or_invalid_has_no_estimates(all_invalid: bool) -> None:
    data = np.full((35, 35), np.nan if all_invalid else -3, dtype=np.float32)
    plane = _plane(data)
    result = prepare_native_presentation(plane)
    np.testing.assert_array_equal(result.values, data)
    np.testing.assert_array_equal(result.support, plane.valid)
    assert not result.estimate_mask.any()
    assert result.diagnostics.accepted_clusters == 0
    assert result.diagnostics.rejection_counts == ({"exterior": 1} if all_invalid else {})


def test_valid_zero_negative_and_finite_invalid_samples_are_distinct() -> None:
    plane = _bright_core()
    data = plane.data.copy()
    data[5, 5:7] = [0, -7]
    valid = np.isfinite(data)
    data[32:34, 32:35] = 0
    result = prepare_native_presentation(_plane(data, valid))
    assert result.diagnostics.estimated_samples == 6
    np.testing.assert_array_equal(result.values[5, 5:7], [0, -7])
    assert result.support[5, 5:7].all()
    assert not result.estimate_mask[5, 5:7].any()
    assert (result.values[32:34, 32:35] == 117.5).all()


def test_diagonal_invalid_path_to_border_is_exterior() -> None:
    plane = _bright_core()
    idx = np.arange(33)
    plane.data[idx, idx] = np.nan
    # Reconstruct validity after introducing the diagonal path.
    plane = _plane(plane.data)
    result = prepare_native_presentation(plane)
    assert result.diagnostics.rejection_counts == {"exterior": 1}
    assert not result.estimate_mask.any()
    assert not result.support[32:34, 32:35].any()


@pytest.mark.parametrize("kind,reason", [("large", "area"), ("long", "extent"), ("edge", "edge_patch")])
def test_shape_and_edge_rejection(kind: str, reason: str) -> None:
    data = _bright_core().data.copy()
    data[32:34, 32:35] = 100
    if kind == "large":
        data[30:35, 30:35] = np.nan
    elif kind == "long":
        data[32, 28:37] = np.nan
    else:
        data[5:7, 5:8] = np.nan
    result = prepare_native_presentation(_plane(data))
    assert result.diagnostics.rejection_counts == {reason: 1}
    assert not result.estimate_mask.any()


@pytest.mark.parametrize("mode,reason", [
    ("ring", "ring_support"), ("annulus", "annulus_support"),
    ("noise", "degenerate_noise"), ("dark", "brightness"), ("ridge", "sectors"),
])
def test_insufficient_support_or_stellar_evidence_rejects(mode: str, reason: str) -> None:
    plane = _bright_core()
    yy, xx = np.indices(plane.data.shape)
    distance = np.maximum.reduce((32-yy, yy-33, 32-xx, xx-34, np.zeros_like(yy)))
    annulus = (distance >= 8) & (distance <= 16)
    component = np.isnan(plane.data)
    ring = ndimage.binary_dilation(component, structure=np.ones((3, 3)), iterations=2) & ~component
    data = plane.data.copy()
    valid = plane.valid.copy()
    profile = BridgeProfile()
    if mode == "ring":
        # Support threshold rejection without connecting the core to other invalids.
        profile = replace(profile, min_ring_samples=37)
    elif mode == "annulus":
        profile = replace(profile, min_annulus_samples=int(np.count_nonzero(annulus)) + 1)
    elif mode == "noise":
        data[annulus] = 10
    elif mode == "dark":
        data[ring] = 10
    else:
        # Broad ridge: global annulus median remains low, but three sectors do not decline.
        sectors = np.floor(((np.arctan2(yy-32.5, xx-33) + np.pi/8) % (2*np.pi))/(np.pi/4)).astype(int)
        # Three bright exterior sectors leave the global background/noise finite
        # and the global brightness test passing, but only five sectors decline.
        data[ring] = 300
        raised = annulus & (sectors < 3)
        data[raised] = 350 + np.where((yy[raised] + xx[raised]) % 2, 1, -1)
    result = prepare_native_presentation(_plane(data, valid), profile=profile)
    assert result.diagnostics.rejection_counts == {reason: 1}
    assert not result.estimate_mask.any()


def test_bright_outlier_does_not_choose_plateau_or_modify_ring() -> None:
    plane = _bright_core()
    plane.data[30, 30] = 1e6
    result = prepare_native_presentation(plane)
    assert result.diagnostics.estimated_samples == 6
    assert result.values[32, 32] < 140
    assert result.values[30, 30] == 1e6


def test_repeat_is_deterministic_and_rejected_components_cannot_seed_fills() -> None:
    plane = _bright_core()
    plane.data[10:12, 10:13] = np.nan
    plane = _plane(plane.data)
    first = prepare_native_presentation(plane)
    second = prepare_native_presentation(plane)
    np.testing.assert_array_equal(first.values, second.values)
    np.testing.assert_array_equal(first.estimate_mask, second.estimate_mask)
    assert first.diagnostics.candidate_clusters == 2
    assert first.diagnostics.rejection_counts == {"edge_patch": 1}
    assert first.diagnostics.accepted_clusters == 1


@pytest.mark.parametrize("field,value", [
    ("max_area", 0), ("max_extent", True), ("ring_radius", 0), ("bright_sigma", np.nan),
    ("bright_sigma", True), ("sector_sigma", -1), ("min_ring_fraction", 1.1),
    ("min_annulus_fraction", 0), ("min_declining_sectors", 9), ("annulus_inner", 1),
    ("annulus_outer", 7), ("min_ring_samples", 1.5),
])
def test_invalid_profile_fails_loudly(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        BridgeProfile(**{field: value})


def test_detector_failure_identifies_source_and_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise ArithmeticError("injected component failure")
    monkeypatch.setattr(bridge.ndimage, "label", fail)
    plane = _bright_core()
    original = plane.data.copy()
    with pytest.raises(RuntimeError, match="synthetic.*injected component failure"):
        prepare_native_presentation(plane)
    np.testing.assert_array_equal(plane.data, original)


@pytest.mark.parametrize("enabled", [0, 1, None, "On"])
def test_enabled_requires_boolean(enabled: object) -> None:
    with pytest.raises(ValueError, match="boolean"):
        prepare_native_presentation(_bright_core(), enabled=enabled)


def test_memory_accounting_includes_labels_copies_and_component_metadata() -> None:
    assert bridge.estimate_bridge_peak_bytes(100, 3) == 2400 + 1024 + 1024**2
    with pytest.raises(ValueError):
        bridge.estimate_bridge_peak_bytes(-1, 3)


def test_neighbor_estimates_never_enter_another_components_boundary_statistic() -> None:
    yy, xx = np.indices((67, 68))
    data = (10 + np.where((yy + xx) % 2, 1, -1)).astype(np.float32)
    cores = []
    for start in (32, 35):
        core = np.zeros(data.shape, dtype=bool)
        core[start:start+2, 32:35] = True
        cores.append(core)
        ring = ndimage.binary_dilation(core, structure=np.ones((3, 3)), iterations=2) & ~core
        data[ring] = 200 if start == 32 else 400
    for core in cores:
        data[core] = np.nan
    plane = _plane(data)
    result = prepare_native_presentation(plane)
    assert result.diagnostics.accepted_clusters == 2
    for core in cores:
        ring = ndimage.binary_dilation(core, structure=np.ones((3, 3)), iterations=2) & ~core
        expected = np.median(data[ring & plane.valid].astype(np.float64))
        np.testing.assert_array_equal(result.values[core], np.full(6, expected))


def test_actual_missing_ring_and_annulus_fractions_reject_before_fill() -> None:
    plane = _bright_core()
    valid = plane.valid.copy()
    # Independent invalids in the ring disconnect from the core by one observed
    # row; raising the required fraction demonstrates original support handling.
    valid[30, 30:37] = False
    result = prepare_native_presentation(_plane(plane.data, valid), profile=replace(BridgeProfile(), min_ring_fraction=1))
    assert result.diagnostics.accepted_clusters == 0
    assert result.diagnostics.rejection_counts.get("ring_support", 0) >= 1


@pytest.mark.parametrize("flux_conserving", [False, True])
def test_real_native_bridge_prevents_strict_resampler_from_enlarging_core(flux_conserving: bool) -> None:
    from galaxy import reprojection
    plane = load_fits_plane(FIXTURES / "pillars_f090w_core.fits")
    result = prepare_native_presentation(plane)
    output_wcs = plane.wcs.deepcopy()
    output_wcs.wcs.crpix += 0.5
    strict = reprojection.reproject_plane(plane, output_wcs, plane.data.shape, flux_conserving)
    # Direct installed-resampler experiment. This does not relabel observations or
    # claim production support transport: it verifies the actual numerical defect.
    input_values = np.where(result.support, result.values, np.nan)
    if flux_conserving:
        values, support = reprojection._reproject_adaptive_2d(
            input_values.astype(np.float64), plane.wcs, output_wcs, plane.data.shape,
            conserve_flux=True,
        )
    else:
        values, support = reprojection._reproject_full(
            input_values, plane.wcs, output_wcs, plane.data.shape,
        )
    hole = strict.footprint[28:39, 28:40] == 0
    assert np.count_nonzero(hole) > 6  # strict resampling expands the six native NaNs
    assert (strict.data[28:39, 28:40][hole] == 0).all()
    assert np.isfinite(values[28:39, 28:40][hole]).all()
    assert (support[28:39, 28:40][hole] > 0).all()
    assert not plane.valid[32:34, 32:35].any()


def test_signed_boundary_can_produce_signed_estimate_without_clipping() -> None:
    plane = _bright_core()
    plane = _plane(plane.data - 200)
    result = prepare_native_presentation(plane)
    assert result.diagnostics.estimated_samples == 6
    np.testing.assert_array_equal(result.values[32:34, 32:35], np.full((2, 3), -82.5))
    np.testing.assert_array_equal(result.values[plane.valid], plane.data[plane.valid])


@pytest.mark.parametrize("missing", [np.nan, np.inf, -np.inf])
def test_nonfinite_sci_is_a_candidate(missing: float) -> None:
    plane = _bright_core()
    plane.data[32:34, 32:35] = missing
    result = prepare_native_presentation(_plane(plane.data))
    assert result.diagnostics.estimated_samples == 6
    assert np.isfinite(result.values).all()


def test_unexpected_fill_failure_is_not_eligibility_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise ArithmeticError("injected estimate failure")
    monkeypatch.setattr(bridge, "_fill_component", fail)
    plane = _bright_core()
    original = plane.data.copy()
    with pytest.raises(RuntimeError, match="synthetic.*injected estimate failure"):
        prepare_native_presentation(plane)
    np.testing.assert_array_equal(plane.data, original)


def test_benchmark_rejects_source_as_report_destination(tmp_path: Path) -> None:
    import importlib.util
    script = Path(__file__).parents[1] / "scripts" / "benchmark_native_bridge.py"
    spec = importlib.util.spec_from_file_location("native_bridge_benchmark", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source.fits"
    source.write_bytes(b"immutable source sentinel")
    with pytest.raises(ValueError, match="must not overwrite"):
        module.benchmark(source, source)
    assert source.read_bytes() == b"immutable source sentinel"
