from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
import tifffile


def export_png(rgb: np.ndarray, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    png_data = np.clip(rgb / 257.0, 0, 255).astype("uint8")
    Image.fromarray(png_data, mode="RGB").save(destination)
    return destination


def export_tiff(rgb: np.ndarray, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(destination, np.clip(rgb, 0, 65535).astype("uint16"), photometric="rgb")
    return destination


def export_footprint_overlay(footprint_masks: list[np.ndarray], path: str | Path) -> Path:
    if not footprint_masks:
        raise ValueError("footprint overlay requires at least one footprint mask")

    combined = np.zeros_like(np.asarray(footprint_masks[0], dtype=bool), dtype=bool)
    for footprint in footprint_masks:
        combined |= np.asarray(footprint, dtype=np.float32) > 0.0

    up = np.roll(combined, 1, axis=0)
    down = np.roll(combined, -1, axis=0)
    left = np.roll(combined, 1, axis=1)
    right = np.roll(combined, -1, axis=1)
    interior = combined & up & down & left & right
    boundary = combined & ~interior

    boundary[[0, -1], :] &= combined[[0, -1], :]
    boundary[:, [0, -1]] &= combined[:, [0, -1]]

    overlay = np.zeros(combined.shape, dtype=np.uint8)
    overlay[boundary] = 255

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(overlay, mode="L").save(destination)
    return destination
