"""Synthetic checks of the tracking core: a textured crop shifted by a known
sub-pixel vector must be recovered by SIFT -> KLT -> RANSAC -> direction filter,
and a stable-region correction must remove a common camera shift."""
import numpy as np
import cv2

from glacier_tlc.tracking import Tracker, vector_stats
from glacier_tlc.enhance import make_enhancer
from glacier_tlc.utils import nmad

CFG = {"sift": {}, "klt": {"win_size": 31, "pyramid_levels": 3, "max_iterations": 30, "epsilon": 0.01, "max_bidirectional_error": 2.0},
       "ransac": {"reproj_threshold_px": 2.0, "max_trials": 5000, "confidence": 0.99}, "direction_filter": {"enabled": True, "threshold_deg": 30}}


def _texture(seed=0, shape=(200, 700)):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.random(shape).astype(np.float32), (0, 0), 2.0)
    img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def _shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def test_recovers_subpixel_shift():
    enh = make_enhancer({"method": "clahe"})
    a = _texture(); b = _shift(a, -2.3, 0.7)
    tr = Tracker(CFG)
    res = tr.track(enh(a), enh(b), (40, 40, 620, 120), (0, 0))
    st = vector_stats(res)
    assert st["n_vectors"] > 100, st
    assert abs(st["dx_median"] - (-2.3)) < 0.1 and abs(st["dy_median"] - 0.7) < 0.1, st
    assert st["mag_nmad"] < 0.2


def test_direction_filter_removes_outliers():
    enh = make_enhancer({"method": "clahe"})
    a = _texture(1); b = _shift(a, 3.0, 0.0)
    tr = Tracker(CFG)
    res = tr.track(enh(a), enh(b), (40, 40, 620, 120), (0, 0))
    d = res.direction_deg
    assert np.all(np.abs(d) <= 30.0)


def test_stable_correction():
    """Glacier ROI moves (-1.5, +0.4) px, camera shakes (+0.8, -0.6): the
    corrected ROI displacement must equal the glacier motion."""
    enh = make_enhancer({"method": "clahe"})
    cam = np.array([0.8, -0.6]); ice = np.array([-1.5, 0.4])
    s_a = _texture(2, (150, 400)); s_b = _shift(s_a, *cam)
    r_a = _texture(3, (150, 400)); r_b = _shift(r_a, *(cam + ice))
    tr = Tracker(CFG)
    rs = tr.track(enh(s_a), enh(s_b), (30, 30, 340, 90), (0, 0), is_stable=True)
    rr = tr.track(enh(r_a), enh(r_b), (30, 30, 340, 90), (0, 0))
    s_med = np.median(rs.vec, axis=0)
    corr = np.median(rr.vec - s_med, axis=0)
    assert np.allclose(corr, ice, atol=0.1), (corr, ice)
    assert nmad(np.hypot(*rs.vec.T)) < 0.2


if __name__ == "__main__":
    test_recovers_subpixel_shift(); test_direction_filter_removes_outliers(); test_stable_correction()
    print("all synthetic tests passed")
