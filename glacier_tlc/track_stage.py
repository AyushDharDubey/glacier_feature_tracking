"""Stage 4: run feature tracking for every image pair and ROI.

Pairs are all combinations (nC2) of usable images inside one camera-position
group whose time separation lies within [min_baseline_days, max_baseline_days]
(the paper combines images within each group; limiting the baseline keeps the
pair count tractable and matches the weekly-to-monthly windows analysed).

Outputs
  output/pairs_raw.csv        one row per pair x ROI with the vector statistics
                              (pixels, uncorrected) + tracking diagnostics
  .cache/vectors/<group>/<A>__<B>.npz  the final motion vectors of every ROI of
                              the pair (start positions + displacements), used
                              for vector-overlay figures and re-analysis
"""
from __future__ import annotations

import itertools
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .config import Config
from .extract import crop_path
from .tracking import Tracker, TrackResult, vector_stats
from .utils import ensure_dir, log

_TRACKER: Tracker | None = None
_CFG_TRACK: dict = {}


def _init(cfg_tracking: dict):
    global _TRACKER, _CFG_TRACK
    cv2.setNumThreads(1)
    _CFG_TRACK = cfg_tracking
    _TRACKER = Tracker(cfg_tracking)


def build_pairs(cfg: Config, used: pd.DataFrame) -> pd.DataFrame:
    pc = cfg.pairs
    min_b = float(pc.get("min_baseline_days") or 0.5)
    raw_max = pc.get("max_baseline_days")
    max_b = float("inf") if raw_max in (None, "null", "none", "unlimited") else float(raw_max)
    rows = []
    for gname in cfg.groups:
        sub = used[used.group == gname].sort_values("datetime")
        recs = list(sub[["file", "datetime"]].itertuples(index=False))
        for (fa, ta), (fb, tb) in itertools.combinations(recs, 2):
            dtd = (tb - ta).total_seconds() / 86400.0
            if min_b <= dtd <= max_b:
                rows.append({"group": gname, "file_a": fa, "file_b": fb, "datetime_a": ta, "datetime_b": tb, "days": dtd})
    return pd.DataFrame(rows)


def _track_pair(args):
    gname, fa, fb, path_a, path_b, rois, meta = args
    assert _TRACKER is not None
    try:
        A, B = np.load(path_a), np.load(path_b)
    except Exception as e:  # pragma: no cover
        return None, f"load error {e}"
    rows, vec_arrays = {}, {}
    ref_dirs = meta.get("reference_direction", {})
    out = Path(meta["vec_dir"]) / gname / f"{Path(fa).stem}__{Path(fb).stem}.npz"
    # resume: reuse a cached pair if it holds every requested ROI
    if out.exists():
        try:
            z = np.load(out)
            if all(f"{n}_vec" in z for n in rois):
                for name in rois:
                    diag = z[f"{name}_diag"] if f"{name}_diag" in z else np.array([-1, -1, -1])
                    res = TrackResult(z[f"{name}_p0"], z[f"{name}_vec"], int(diag[0]), int(diag[1]), int(diag[2]), len(z[f"{name}_vec"]))
                    rows[name] = vector_stats(res)
                return rows, "cached"
        except Exception:
            pass
    for name, (rect, role) in rois.items():
        prect = A[f"{name}_rect"]
        x0, y0 = int(prect[0]), int(prect[1])
        rect_in_crop = (rect[0] - x0, rect[1] - y0, rect[2], rect[3])
        res = _TRACKER.track(A[f"{name}_enh"], B[f"{name}_enh"], rect_in_crop, (x0, y0),
                             is_stable=(role == "stable"), reference_direction=ref_dirs.get(name))
        rows[name] = vector_stats(res)
        vec_arrays[f"{name}_p0"] = res.p0.astype(np.float32)
        vec_arrays[f"{name}_vec"] = res.vec.astype(np.float32)
        vec_arrays[f"{name}_diag"] = np.array([res.n_sift, res.n_klt, res.n_ransac], dtype=np.int32)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **vec_arrays)
    return rows, "ok"


def run(cfg: Config, workers: int = 0, limit: int | None = None) -> pd.DataFrame:
    used = pd.read_csv(cfg.paths.output / "images_used.csv", parse_dates=["datetime"])
    pairs = build_pairs(cfg, used)
    if limit:
        pairs = pairs.head(limit)
    log.info("track: %d pairs (%s)", len(pairs), ", ".join(f"{g}={int((pairs.group == g).sum())}" for g in cfg.groups))
    vec_dir = ensure_dir(cfg.paths.cache / "vectors")
    tasks = []
    for r in pairs.itertuples(index=False):
        g = cfg.groups[r.group]
        wanted = cfg.tracking.get("rois")  # optional subset, e.g. [stable, ROI1, ROI2, ROI3]
        rois = {roi.name: (roi.rect, roi.role) for roi in g.rois.values() if not wanted or roi.name in wanted}
        meta = {"vec_dir": str(vec_dir), "reference_direction": cfg.tracking.get("direction_filter", {}).get("reference_direction", {}).get(r.group, {})}
        tasks.append((r.group, r.file_a, r.file_b, str(crop_path(cfg, r.group, r.file_a)), str(crop_path(cfg, r.group, r.file_b)), rois, meta))
    workers = workers or max(1, (cv2.getNumberOfCPUs() or 2) - 1)
    records = []
    n_cached = 0
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(cfg.tracking,)) as ex:
        for i, ((pr, status), rows_out) in enumerate(zip(ex.map(_track_pair, tasks, chunksize=8), pairs.itertuples(index=False)), 1):
            n_cached += status == "cached"
            if pr is None:
                log.warning("pair %s-%s: %s", rows_out.file_a, rows_out.file_b, status)
                continue
            base = rows_out._asdict()
            for roi, stats in pr.items():
                rec = dict(base); rec["roi"] = roi; rec.update(stats); records.append(rec)
            if i % 250 == 0:
                log.info("track: %d/%d pairs (%d from cache)", i, len(tasks), n_cached)
    df = pd.DataFrame(records)
    df.to_csv(cfg.paths.output / "pairs_raw.csv", index=False)
    log.info("track done: %d pair-ROI rows -> %s", len(df), cfg.paths.output / "pairs_raw.csv")
    return df
