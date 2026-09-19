import logging

from galaxy.logging_utils import configure_logging


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
