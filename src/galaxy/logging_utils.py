from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Callable

DEFAULT_LOG_FILE_NAME = "galaxy.log"
_MANAGED_HANDLER_ATTR = "_galaxy_managed"


def configure_logging(
    *,
    log_path: str | Path | None = None,
    debug_to_console: bool = False,
    debug_to_file: bool = True,
) -> Path | None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in list(root_logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            root_logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if debug_to_console else logging.INFO)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _MANAGED_HANDLER_ATTR, True)
    root_logger.addHandler(console_handler)

    resolved_log_path: Path | None = None
    if log_path is not None:
        resolved_log_path = Path(log_path)
        resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(resolved_log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG if debug_to_file else logging.INFO)
        file_handler.setFormatter(formatter)
        setattr(file_handler, _MANAGED_HANDLER_ATTR, True)
        root_logger.addHandler(file_handler)

    return resolved_log_path


def emit_log(
    logger: logging.Logger,
    level: int,
    message: str,
    progress: Callable[[str], None] | None = None,
) -> None:
    logger.log(level, message)
    if progress is not None:
        progress(message)
