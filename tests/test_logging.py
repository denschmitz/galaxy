import logging

import pytest

from galaxy.config import GalaxyProjectValidationError, load_config
from galaxy.logging_utils import configure_logging


def test_load_config_logs_field_specific_validation_failure(tmp_path, caplog) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(
        """
format_revision: 1
target:
  name: Orion
  region:
    kind: circle
    radius_arcmin: 5.0
canvas:
  center:
    mode: resolved_target
  pixel_scale_arcsec: 0.1
  width: 128
  height: 128
  bogus: true
tone:
  stretch:
    red: {kind: asinh, parameter: 4.0}
    green: {kind: asinh, parameter: 4.0}
    blue: {kind: asinh, parameter: 4.0}
  percentiles:
    black: 1.0
    white: 99.0
""".strip(),
        encoding="utf-8",
    )
    configure_logging(log_path=tmp_path / "galaxy.log")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(GalaxyProjectValidationError):
            load_config(path)

    assert any("canvas.bogus" in record.message for record in caplog.records)
    assert any("unknown_field" in record.message for record in caplog.records)


def test_configure_logging_supports_debug_file_without_debug_console(tmp_path, capsys) -> None:
    log_path = tmp_path / "galaxy.log"
    configure_logging(log_path=log_path, debug_to_console=False, debug_to_file=True)
    logger = logging.getLogger("galaxy.test")

    logger.debug("debug-visible-in-file")
    logger.info("info-visible-everywhere")

    console = capsys.readouterr().err
    file_text = log_path.read_text(encoding="utf-8")

    assert "info-visible-everywhere" in console
    assert "debug-visible-in-file" not in console
    assert "info-visible-everywhere" in file_text
    assert "debug-visible-in-file" in file_text
