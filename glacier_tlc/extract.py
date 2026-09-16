"""Stage 3: crop every ROI (with a margin) of every usable image, enhance it,
and cache the crops. Decoding a 24 MP JPEG dominates run time, so each image
is read exactly once here and the pair stage works on the small cached crops.

Cache layout: .cache/crops/<group>/<file stem>.npz with arrays
  <roi>_raw  : uint8 grayscale padded crop (for overlays)
  <roi>_enh  : uint8 enhanced padded crop (input to feature tracking)
  <roi>_rect : [x0, y0, w, h] of the padded crop in full-resolution coordinates
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .config import Config, Group
from .utils.enhance import crop, make_enhancer, padded_rect
from .utils import ensure_dir, log


def crop_path(cfg: Config, group: str, file: str) -> Path:
    return cfg.paths.cache / "crops" / group / (Path(file).stem + ".npz")


def _extract_one(args):
    img_path, out_path, rois, pad, enh_cfg, size = args
    out_path = Path(out_path)
    if out_path.exists():
        return str(out_path), "cached"
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return str(out_path), "unreadable"
    h, w = img.shape
    if (w, h) != tuple(size):
        return str(out_path), f"size_mismatch {w}x{h}"
    enhance = make_enhancer(enh_cfg)
    arrays = {}
    for name, rect in rois.items():
        prect = padded_rect(rect, pad, w, h)
        raw = np.ascontiguousarray(crop(img, prect))
        arrays[f"{name}_raw"] = raw
        arrays[f"{name}_enh"] = enhance(raw)
        arrays[f"{name}_rect"] = np.array(prect, dtype=np.int32)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, **arrays)
    return str(out_path), "ok"


def run(cfg: Config, workers: int = 0) -> None:
    used = pd.read_csv(cfg.paths.output / "images_used.csv")
    pad = int(cfg.tracking.get("pad_px", 40))
    size = (cfg.camera.image_width_px, cfg.camera.image_height_px)
    tasks = []
    for gname, g in cfg.groups.items():
        rois = {r.name: r.rect for r in g.rois.values()}
        for f in used.loc[used.group == gname, "file"]:
            tasks.append((str(cfg.paths.images / f), str(crop_path(cfg, gname, f)), rois, pad, cfg.enhancement, size))
    ensure_dir(cfg.paths.cache / "crops")
    workers = workers or max(1, (cv2.getNumberOfCPUs() or 2) - 1)
    log.info("extract: %d images, %d workers", len(tasks), workers)
    stats: dict[str, int] = {}
    with ProcessPoolExecutor(workers) as ex:
        for i, (p, status) in enumerate(ex.map(_extract_one, tasks, chunksize=2), 1):
            stats[status] = stats.get(status, 0) + 1
            if status not in ("ok", "cached"):
                log.warning("%s: %s", p, status)
            if i % 100 == 0:
                log.info("extract: %d/%d", i, len(tasks))
    log.info("extract done: %s", stats)
