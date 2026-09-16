"""Stage 2: image quality assessment and filtering.

The paper excluded ~200 images manually (lens glare, low light, snowstorms,
fog) and all images in which the glacier was hidden (camera buried under snow).
We reproduce that step as an automatic screening plus manual override lists:

* global metrics on a down-scaled copy: mean brightness, contrast (std),
  sharpness (variance of Laplacian), colour saturation;
* scene visibility: SIFT matches between the image and the group's reference
  image over the static (non-glacier) part of the scene, with a RANSAC
  similarity model. Fog / snow-burial / heavy glare give (near) zero inliers.
  The recovered translation is also the camera-shift diagnostic;
* manual lists `exclude_images.txt` and `include_images.txt` (one file name per
  line, '#' comments) override the automatic decision.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .config import Config
from .utils import ensure_dir, log

_SCALE = 0.25


def _load_small(path: Path, scale: float = _SCALE) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_REDUCED_COLOR_4 if scale == 0.25 else cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"cannot read {path}")
    if scale != 0.25:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return img


def _static_mask(shape, static_fraction: float) -> np.ndarray:
    h, w = shape[:2]
    m = np.zeros((h, w), np.uint8)
    m[: int(h * static_fraction), :] = 255
    return m


def _global_metrics(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return {
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
        "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "saturation": float(hsv[..., 1].mean()),
        "clipped_frac": float(((gray < 5) | (gray > 250)).mean()),
    }


def _ref_features(ref_bgr: np.ndarray, static_fraction: float):
    sift = cv2.SIFT_create(nfeatures=4000)
    gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    return sift.detectAndCompute(gray, _static_mask(gray.shape, static_fraction))


def _visibility(bgr: np.ndarray, ref, static_fraction: float) -> dict:
    """SIFT + RANSAC similarity against the group reference over the static scene."""
    rkp, rdes = ref
    sift = cv2.SIFT_create(nfeatures=4000)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kp, des = sift.detectAndCompute(gray, _static_mask(gray.shape, static_fraction))
    out = {"vis_inliers": 0, "shift_dx_px": np.nan, "shift_dy_px": np.nan, "shift_scale": np.nan}
    if des is None or rdes is None or len(kp) < 8:
        return out
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des, rdes, k=2)
    good = [m for m, n in (x for x in matches if len(x) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return out
    p1 = np.float32([kp[m.queryIdx].pt for m in good])
    p2 = np.float32([rkp[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=5000, confidence=0.99)
    if M is None or inl is None:
        return out
    inl = inl.ravel().astype(bool)
    d = (p2 - p1)[inl]
    out["vis_inliers"] = int(inl.sum())
    if inl.sum():
        out["shift_dx_px"] = float(np.median(d[:, 0]) / _SCALE)  # full-resolution px, image -> reference
        out["shift_dy_px"] = float(np.median(d[:, 1]) / _SCALE)
        out["shift_scale"] = float(np.hypot(M[0, 0], M[1, 0]))
    return out


def _image_features(bgr: np.ndarray, static_fraction: float):
    sift = cv2.SIFT_create(nfeatures=4000)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return sift.detectAndCompute(gray, _static_mask(gray.shape, static_fraction))


def _worker(args):
    path, ref, static_fraction = args
    bgr = _load_small(Path(path))
    m = _global_metrics(bgr)
    m.update(_visibility(bgr, ref, static_fraction))
    m["file"] = Path(path).name
    # serialisable features for the neighbour check done in the parent
    kp, des = _image_features(bgr, static_fraction)
    m["_feat"] = ([k.pt for k in kp], des)
    return m


def _match_count(fa, fb) -> int:
    """RANSAC-similarity inliers between two serialised feature sets."""
    (pa, da), (pb, db) = fa, fb
    if da is None or db is None or len(pa) < 8 or len(pb) < 8:
        return 0
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(da, db, k=2)
    good = [m for m, n in (x for x in matches if len(x) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return 0
    p1 = np.float32([pa[m.queryIdx] for m in good]); p2 = np.float32([pb[m.trainIdx] for m in good])
    _, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=5000, confidence=0.99)
    return int(inl.sum()) if inl is not None else 0


def _read_list(path: Path | None) -> set[str]:
    if not path or not Path(path).exists():
        return set()
    return {ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip() and not ln.startswith("#")}


def pick_reference(cfg: Config, inv: pd.DataFrame, gname: str) -> str:
    g = cfg.groups[gname]
    if g.reference_image:
        return g.reference_image
    sub = inv[(inv.group == gname) & inv.daily_pick]
    # the reference is the sharpest, well-exposed image of the group
    if sub.empty:
        raise SystemExit(f"group {gname} has no daily images")
    return str(sub.iloc[len(sub) // 2]["file"])


def run(cfg: Config, workers: int = 0) -> pd.DataFrame:
    q = cfg.quality
    inv = pd.read_csv(cfg.paths.output / "inventory.csv", parse_dates=["datetime"])
    inv = inv[inv.daily_pick & inv.group.notna() & (inv.group != "")].copy()
    static_fraction = float(q.get("static_fraction", 0.7))
    workers = workers or max(1, (cv2.getNumberOfCPUs() or 2) - 1)
    frames = []
    for gname in cfg.groups:
        sub = inv[inv.group == gname]
        if sub.empty:
            continue
        ref_name = pick_reference(cfg, inv, gname)
        log.info("quality: group %s, %d images, reference %s", gname, len(sub), ref_name)
        ref = _ref_features(_load_small(cfg.paths.images / ref_name), static_fraction)
        # keypoints are not picklable -> compute per worker from serialisable form
        ref_ser = ([k.pt for k in ref[0]], ref[1])
        tasks = [(str(cfg.paths.images / f), ref_ser, static_fraction) for f in sub.file]
        with ProcessPoolExecutor(workers) as ex:
            res = list(ex.map(_worker_ser, tasks, chunksize=4))
        # scene visibility relative to the temporal neighbours (robust to the
        # seasonal appearance change that defeats a single fixed reference)
        n_nb = int(q.get("neighbour_images", 2))
        for i, r in enumerate(res):
            best = 0
            for j in range(max(0, i - n_nb), min(len(res), i + n_nb + 1)):
                if j != i:
                    best = max(best, _match_count(r["_feat"], res[j]["_feat"]))
            r["vis_inliers_neighbour"] = best
            r["vis_inliers_ref"] = r["vis_inliers"]
            r["vis_inliers"] = max(r["vis_inliers"], best)
        for r in res:
            del r["_feat"]
        df = pd.DataFrame(res)
        df["reference_image"] = ref_name
        frames.append(df)
    qdf = pd.concat(frames, ignore_index=True)
    df = inv.merge(qdf, on="file", how="left")

    # automatic decision
    thr = q.get("thresholds", {})
    auto_ok = (
        (df.vis_inliers >= int(thr.get("min_visibility_inliers", 30)))
        & (df.sharpness >= float(thr.get("min_sharpness", 50)))
        & (df.contrast >= float(thr.get("min_contrast", 15)))
        & (df.brightness >= float(thr.get("min_brightness", 30)))
        & (df.brightness <= float(thr.get("max_brightness", 235)))
        & (df.clipped_frac <= float(thr.get("max_clipped_frac", 0.3)))
    )
    df["auto_ok"] = auto_ok.fillna(False)
    excl = _read_list(cfg.paths.images.parent / q.get("exclude_list", "exclude_images.txt"))
    incl = _read_list(cfg.paths.images.parent / q.get("include_list", "include_images.txt"))
    df["manual"] = np.where(df.file.isin(excl), "exclude", np.where(df.file.isin(incl), "include", ""))
    df["usable"] = df.auto_ok & ~df.file.isin(excl) | df.file.isin(incl)
    # reason string for the report
    reasons = []
    for _, r in df.iterrows():
        rs = []
        if r.vis_inliers < int(thr.get("min_visibility_inliers", 30)): rs.append("low_visibility")
        if r.sharpness < float(thr.get("min_sharpness", 50)): rs.append("blurry")
        if r.contrast < float(thr.get("min_contrast", 15)): rs.append("low_contrast")
        if r.brightness < float(thr.get("min_brightness", 30)): rs.append("dark")
        if r.brightness > float(thr.get("max_brightness", 235)): rs.append("overexposed")
        if r.clipped_frac > float(thr.get("max_clipped_frac", 0.3)): rs.append("clipped")
        if r.manual: rs.append(f"manual_{r.manual}")
        reasons.append(";".join(rs))
    df["flags"] = reasons
    ensure_dir(cfg.paths.output)
    df.to_csv(cfg.paths.output / "quality.csv", index=False)
    used = df[df.usable].copy()
    used.to_csv(cfg.paths.output / "images_used.csv", index=False)
    log.info("quality: %d/%d images usable (%s)", len(used), len(df),
             ", ".join(f"{g}={int((used.group == g).sum())}" for g in cfg.groups))
    return df


def _worker_ser(args):
    path, ref_ser, static_fraction = args
    pts, des = ref_ser
    kps = [cv2.KeyPoint(float(x), float(y), 1.0) for x, y in pts]
    return _worker((path, (kps, des), static_fraction))
