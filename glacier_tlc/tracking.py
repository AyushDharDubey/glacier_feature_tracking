"""Core feature-tracking step for one image pair and one ROI (paper Sect. 3.2.2).

    enhanced crop A --SIFT--> keypoint locations (descriptors are NOT used)
                    --KLT (pyramidal Lucas-Kanade, forward + backward)-->
                      matches with bidirectional error <= threshold
                    --RANSAC, affine motion model--> inliers
                    --direction filter (|dir - median dir| <= threshold)-->
                      final motion vectors (pixels)

Parameter defaults follow the authors' MATLAB script where the paper is silent
(SIFT defaults, 31x31 KLT window, 3 pyramid levels, 30 iterations, 2 px
bidirectional error, 5000 RANSAC trials at 99 % confidence, 30 deg direction
window). The one deliberate difference: the script's RANSAC `MaxDistance` of
2000 px accepted every correspondence as an inlier, i.e. it disabled the
outlier rejection the paper describes, so a real reprojection threshold
(default 2 px) is used here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .utils import circ_diff_deg, mean_below_p95, nmad


@dataclass
class TrackResult:
    p0: np.ndarray # start positions in full-resolution image coordinates
    vec: np.ndarray # displacement dx, dy in pixels (image x right, y down)
    n_sift: int = 0
    n_klt: int = 0
    n_ransac: int = 0
    n_final: int = 0
    affine: np.ndarray | None = None
    median_direction_deg: float = float("nan")

    @property
    def magnitude(self) -> np.ndarray:
        return np.hypot(self.vec[:, 0], self.vec[:, 1]) if len(self.vec) else np.empty(0)

    @property
    def direction_deg(self) -> np.ndarray:
        return np.degrees(np.arctan2(self.vec[:, 1], self.vec[:, 0])) if len(self.vec) else np.empty(0)


def _empty(n_sift=0, n_klt=0, n_ransac=0) -> TrackResult:
    return TrackResult(np.empty((0, 2), np.float32), np.empty((0, 2), np.float32), n_sift, n_klt, n_ransac, 0)


class Tracker:
    def __init__(self, cfg_tracking: dict):
        s = cfg_tracking.get("sift", {})
        self.sift = cv2.SIFT_create(
            nfeatures=int(s.get("max_features", 0)),
            nOctaveLayers=int(s.get("n_octave_layers", 3)),
            contrastThreshold=float(s.get("contrast_threshold", 0.04)),
            edgeThreshold=float(s.get("edge_threshold", 10)),
            sigma=float(s.get("sigma", 1.6)),
        )
        k = cfg_tracking.get("klt", {})
        win = int(k.get("win_size", 31))
        self.lk = dict(
            winSize=(win, win),
            maxLevel=int(k.get("pyramid_levels", 3)) - 1,
            criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, int(k.get("max_iterations", 30)), float(k.get("epsilon", 0.01))),
        )
        self.max_bidir_err = float(k.get("max_bidirectional_error", 2.0))
        r = cfg_tracking.get("ransac", {})
        self.ransac_thr = float(r.get("reproj_threshold_px", 2.0))
        self.ransac_iters = int(r.get("max_trials", 5000))
        self.ransac_conf = float(r.get("confidence", 0.99))
        self.ransac_min = int(r.get("min_points", 6))
        d = cfg_tracking.get("direction_filter", {})
        self.dir_enabled = bool(d.get("enabled", True))
        self.dir_thr = float(d.get("threshold_deg", 30.0))
        self.dir_apply_stable = bool(d.get("apply_to_stable", False))
        self.min_vectors = int(cfg_tracking.get("min_vectors", 20))

    def track(self, enh_a: np.ndarray, enh_b: np.ndarray, roi_rect_in_crop, crop_origin,
              is_stable: bool = False, reference_direction: float | None = None) -> TrackResult:
        """Track ROI features from enhanced crop A to enhanced crop B.

        roi_rect_in_crop: (x, y, w, h) of the ROI proper inside the padded crop
        crop_origin:      (x0, y0) of the padded crop in full-resolution coordinates
        """
        x, y, w, h = roi_rect_in_crop
        mask = np.zeros(enh_a.shape, np.uint8)
        mask[y:y + h, x:x + w] = 255
        kps = self.sift.detect(enh_a, mask)
        if len(kps) < 3:
            return _empty(len(kps))
        p0 = np.float32([kp.pt for kp in kps]).reshape(-1, 1, 2)

        p1, st1, _ = cv2.calcOpticalFlowPyrLK(enh_a, enh_b, p0, None, **self.lk)
        p0r, st2, _ = cv2.calcOpticalFlowPyrLK(enh_b, enh_a, p1, None, **self.lk)
        fb = np.linalg.norm(p0.reshape(-1, 2) - p0r.reshape(-1, 2), axis=1)
        H, W = enh_b.shape
        inside = (p1[:, 0, 0] >= 0) & (p1[:, 0, 0] < W) & (p1[:, 0, 1] >= 0) & (p1[:, 0, 1] < H)
        ok = (st1.ravel() == 1) & (st2.ravel() == 1) & (fb <= self.max_bidir_err) & inside
        n_klt = int(ok.sum())
        if n_klt < self.ransac_min:
            return _empty(len(kps), n_klt)
        a, b = p0[ok].reshape(-1, 2), p1[ok].reshape(-1, 2)

        # RANSAC with an affine motion model
        M, inl = cv2.estimateAffine2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=self.ransac_thr,
                                      maxIters=self.ransac_iters, confidence=self.ransac_conf, refineIters=10)
        if M is None or inl is None or inl.sum() < 3:
            return _empty(len(kps), n_klt)
        inl = inl.ravel().astype(bool)
        a, b = a[inl], b[inl]
        n_ransac = int(inl.sum())
        vec = b - a

        # direction filter around the median flow direction
        direction = np.degrees(np.arctan2(vec[:, 1], vec[:, 0]))
        med_dir = float(np.median(direction)) if len(direction) else float("nan")
        if self.dir_enabled and (self.dir_apply_stable or not is_stable) and len(direction):
            ref = med_dir if reference_direction is None else float(reference_direction)
            keep = circ_diff_deg(direction, ref) <= self.dir_thr
            a, b, vec = a[keep], b[keep], vec[keep]
        res = TrackResult(a + np.float32(crop_origin), vec, len(kps), n_klt, n_ransac, len(vec), M, med_dir)
        return res


def vector_stats(res: TrackResult, prefix: str = "") -> dict:
    """Per-pair statistics of the motion vectors (superset of the MATLAB CSV columns)."""
    n = len(res.vec)
    out = {f"{prefix}n_sift": res.n_sift, f"{prefix}n_klt": res.n_klt, f"{prefix}n_ransac": res.n_ransac, f"{prefix}n_vectors": n}
    keys = ["mag_median", "mag_mean", "mag_mean95", "mag_std", "mag_nmad",
            "dir_median", "dir_mean", "dir_std", "dir_nmad",
            "dx_median", "dx_mean", "dx_std", "dx_nmad",
            "dy_median", "dy_mean", "dy_std", "dy_nmad"]
    if n == 0:
        out.update({f"{prefix}{k}": np.nan for k in keys})
        return out
    mag, d = res.magnitude, res.direction_deg
    dx, dy = res.vec[:, 0], res.vec[:, 1]
    # circular mean for direction
    ang = np.radians(d)
    dir_mean = float(np.degrees(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())))
    dmed = float(np.median(d))
    dir_dev = circ_diff_deg(d, dmed)
    vals = [np.median(mag), mag.mean(), mean_below_p95(mag), mag.std(ddof=1) if n > 1 else 0.0, nmad(mag),
            dmed, dir_mean, dir_dev.std(ddof=1) if n > 1 else 0.0, 1.4826 * np.median(dir_dev),
            np.median(dx), dx.mean(), dx.std(ddof=1) if n > 1 else 0.0, nmad(dx),
            np.median(dy), dy.mean(), dy.std(ddof=1) if n > 1 else 0.0, nmad(dy)]
    out.update({f"{prefix}{k}": float(v) for k, v in zip(keys, vals)})
    return out
