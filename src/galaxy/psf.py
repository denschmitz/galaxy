from __future__ import annotations

import numpy as np

from galaxy.config import PSFConfig


def apply_presentation_psf(planes: dict[str, np.ndarray], psf: PSFConfig) -> dict[str, np.ndarray]:
    if not psf.enabled:
        return planes
    return {name: np.asarray(image, dtype=np.float32) for name, image in planes.items()}
