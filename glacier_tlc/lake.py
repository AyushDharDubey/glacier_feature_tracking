"""Optional stage: proglacial lake state from the TLC images (paper Sect. 4.2).

The paper documents the lake's transition ice-covered -> clear -> turbid ->
clear by visual inspection of TLC and PlanetScope images. Here a rectangular
lake window is summarised per usable image with simple colour indices that
make those transitions quantitative:

  brightness  : mean V (HSV) of the window            (ice/snow cover: high)
  saturation  : mean S (HSV)                          (ice: low, water: higher)
  hue_deg     : circular mean hue                     (blue-green vs beige)
  red_blue    : mean R / mean B                       (turbid sediment water > 1,
                                                       clear blue-green water < 1)
  ice_fraction: share of pixels that are bright and unsaturated (ice proxy)
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from .config import Config
from .utils import log


def _lake_metrics(bgr: np.ndarray) -> dict:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    b, g, r = [bgr[..., i].astype(float).mean() for i in range(3)]
    h = hsv[..., 0].astype(float) * 2.0  # OpenCV hue 0-179 -> degrees
    hue = float(np.degrees(np.arctan2(np.sin(np.radians(h)).mean(), np.cos(np.radians(h)).mean())) % 360)
    ice = (hsv[..., 2] > 170) & (hsv[..., 1] < 40)
    return {"brightness": float(hsv[..., 2].mean()), "saturation": float(hsv[..., 1].mean()), "hue_deg": hue,
            "red_blue": r / b if b else np.nan, "mean_r": r, "mean_g": g, "mean_b": b, "ice_fraction": float(ice.mean())}


def run(cfg: Config) -> pd.DataFrame:
    used = pd.read_csv(cfg.paths.output / "images_used.csv", parse_dates=["datetime"])
    rows = []
    for gname, g in cfg.groups.items():
        if not g.lake_rect:
            continue
        x, y, w, h = g.lake_rect
        for r in used[used.group == gname].itertuples(index=False):
            img = cv2.imread(str(cfg.paths.images / r.file), cv2.IMREAD_REDUCED_COLOR_4)
            if img is None:
                continue
            crop = img[y // 4:(y + h) // 4, x // 4:(x + w) // 4]
            m = _lake_metrics(crop); m.update({"file": r.file, "datetime": r.datetime, "group": gname}); rows.append(m)
    df = pd.DataFrame(rows).sort_values("datetime") if rows else pd.DataFrame()
    df.to_csv(cfg.paths.output / "lake_index.csv", index=False)
    log.info("lake: %d images -> lake_index.csv", len(df))
    return df
