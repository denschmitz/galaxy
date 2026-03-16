from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import requests


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, timeout: int = 120) -> dict[str, Any]:
    if destination.exists():
        return {
            "status": "cached",
            "local_path": str(destination),
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "checksum": sha256_file(destination),
            "file_size": destination.stat().st_size,
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return {
        "status": "downloaded",
        "local_path": str(destination),
        "download_timestamp": datetime.now(timezone.utc).isoformat(),
        "checksum": sha256_file(destination),
        "file_size": destination.stat().st_size,
    }


def write_manifest(entries: list[dict[str, Any]], path: str | Path) -> None:
    Path(path).write_text(json.dumps(entries, indent=2), encoding="utf-8")
