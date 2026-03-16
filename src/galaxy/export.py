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
