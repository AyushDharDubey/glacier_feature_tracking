"""Image enhancement and ROI cropping.

The paper improves image quality with adaptive histogram equalisation
(Sect 3.2; MATLAB `adapthisteq`). OpenCV's CLAHE is the same algorithm
(contrast-limited AHE with bilinear blending between tiles); the clip limit is
parameterised differently, so we convert:

  MATLAB: clip = ceil(N/bins) + round(c_m * (N - ceil(N/bins)))
  OpenCV: clip = max(1, c_cv * N / bins)
  =>      c_cv = 1 + c_m * (bins - 1)         (N = pixels per tile)

With the MATLAB defaults (c_m = 0.01, 256 bins, 8x8 tiles) this gives c_cv ~ 3.55.
"""
from __future__ import annotations

import cv2
import numpy as np


def matlab_clip_to_opencv(clip_limit_matlab: float, n_bins: int = 256) -> float:
    return 1.0 + float(clip_limit_matlab) * (n_bins - 1)


def make_enhancer(cfg_enh: dict):
    method = str(cfg_enh.get("method", "clahe")).lower()
    if method in ("clahe", "adapthisteq"):
        tiles = cfg_enh.get("tiles", [8, 8])
        if "clip_limit_opencv" in cfg_enh:
            clip = float(cfg_enh["clip_limit_opencv"])
        else:
            clip = matlab_clip_to_opencv(cfg_enh.get("clip_limit_matlab", 0.01), cfg_enh.get("n_bins", 256))
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(int(tiles[0]), int(tiles[1])))

        def enhance(gray: np.ndarray) -> np.ndarray:
            return clahe.apply(gray)

        return enhance
    if method in ("none", "nofilter"):
        return lambda gray: gray
    if method == "canny":
        low = float(cfg_enh.get("canny_low", 50)); high = float(cfg_enh.get("canny_high", 150))

        def enhance(gray: np.ndarray) -> np.ndarray:
            edges = cv2.Canny(gray, low, high)
            return np.where(edges > 0, gray, 0).astype(np.uint8)

        return enhance
    raise ValueError(f"unknown enhancement method {method}")


def padded_rect(rect, pad: int, width: int, height: int) -> tuple[int, int, int, int]:
    """Expand [x, y, w, h] by `pad` on all sides, clipped to the image."""
    x, y, w, h = rect
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(width, x + w + pad), min(height, y + h + pad)
    return x0, y0, x1 - x0, y1 - y0


def crop(img: np.ndarray, rect) -> np.ndarray:
    x, y, w, h = rect
    return img[y:y + h, x:x + w]
