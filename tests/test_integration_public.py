import os

import pytest

from galaxy.config import GalaxyConfig
from galaxy.pipeline import run_pipeline


@pytest.mark.skipif(os.environ.get("GALAXY_RUN_LIVE_TESTS") != "1", reason="live archive test is opt-in")
def test_public_pipeline_download_and_compose(tmp_path) -> None:
    config = GalaxyConfig.model_validate(
        {
            "target": {"name": "Orion Nebula", "region": {"kind": "circle", "radius_arcmin": 0.3}},
            "search": {
                "missions": ["HST"],
                "filters": ["F656N", "F658N", "F814W"],
                "product_types": ["SCIENCE", "DRZ", "DRC"],
            },
            "canvas": {
                "center": {"mode": "resolved_target"},
                "pixel_scale_arcsec": 0.2,
                "width": 256,
                "height": 256,
                "flux_conserving": False,
            },
            "tone": {
                "stretch": {
                    "red": {"kind": "asinh", "parameter": 4.0},
                    "green": {"kind": "asinh", "parameter": 4.0},
                    "blue": {"kind": "asinh", "parameter": 4.0},
                },
                "percentiles": {"black": 1.0, "white": 99.5},
            },
        }
    )

    artifacts = run_pipeline(config, tmp_path, mode="full")
    assert artifacts.manifest_path.exists()
    assert artifacts.png_path is not None and artifacts.png_path.exists()
    assert artifacts.tiff_path is not None and artifacts.tiff_path.exists()
    assert artifacts.provenance_path.exists()
