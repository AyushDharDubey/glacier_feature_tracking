"""Parity check of the Python tracker against the authors' own MATLAB output.

The repository ships one result file produced by the authors' MATLAB script,
`motion_statistics_ROI4_Grp3_adapthisteq.csv`: ROI4 and the stable region of
camera group GRP3 geometry, adapthisteq enhancement, the six pairs formed by
the four images of 3-6 November 2023.

This test re-computes those six pairs with `glacier_tlc.tracking` configured to
match the MATLAB script exactly (RANSAC effectively disabled with a 2000 px
threshold, direction filter applied to the stable region as well) and asserts
that every median statistic agrees. It is skipped when the images are absent.

Run:  PYTHONPATH=. python tests/test_matlab_parity.py
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from glacier_tlc.enhance import crop, make_enhancer
from glacier_tlc.inventory import read_exif_datetime
from glacier_tlc.tracking import Tracker, vector_stats

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "input"
MATLAB_CSV = ROOT / "motion_statistics_ROI4_Grp3_adapthisteq.csv"

# GRP3 geometry of the authors' script, the two regions the CSV contains
RECTS = {"motion": (3755, 3195, 338, 172), "stable": (1347, 3290, 416, 178)}
WANTED_DATES = ["2023-11-03", "2023-11-04", "2023-11-05", "2023-11-06"]

# MATLAB script settings: RANSAC MaxDistance 2000 px accepts every point, and
# filterByDirection is called for the stable region too.
MATLAB_CFG = {
    "sift": {},
    "klt": {"win_size": 31, "pyramid_levels": 3, "max_iterations": 30, "max_bidirectional_error": 2.0},
    "ransac": {"reproj_threshold_px": 2000.0, "max_trials": 5000, "confidence": 0.99},
    "direction_filter": {"enabled": True, "threshold_deg": 30, "apply_to_stable": True},
}
# Tolerances. Displacements must agree to 0.02 px. The angular tolerance is
# looser because the stable region's "direction" is the direction of ~1 px of
# residual noise, which a handful of extra vectors can rotate by a degree.
TOL_PX, TOL_DEG = 0.02, 1.5


def _images() -> dict[str, Path]:
    if not IMAGES.exists() or not MATLAB_CSV.exists():
        pytest.skip("input images or the MATLAB reference CSV are not available")
    out = {}
    for p in sorted(IMAGES.glob("*.JPG")):
        t = read_exif_datetime(p)
        if t and t.strftime("%Y-%m-%d") in WANTED_DATES:
            out[t.strftime("%Y-%m-%d")] = p
    if len(out) != 4:
        pytest.skip(f"expected the four 3-6 Nov 2023 images, found {len(out)}")
    return out


def compare() -> pd.DataFrame:
    import cv2

    files = _images()
    ref = pd.read_csv(MATLAB_CSV)
    ref["a"] = pd.to_datetime(ref["Image Date A_motion"]).dt.strftime("%Y-%m-%d")
    ref["b"] = pd.to_datetime(ref["Image Date B_motion"]).dt.strftime("%Y-%m-%d")
    enh = make_enhancer({"method": "clahe"})
    gray = {d: cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for d, p in files.items()}
    tr = Tracker(MATLAB_CFG)
    rows = []
    for da, db in itertools.combinations(WANTED_DATES, 2):
        m = ref[(ref.a == da) & (ref.b == db)]
        assert len(m) == 1, f"{da} -> {db} missing from the MATLAB CSV"
        m = m.iloc[0]
        for region, rect in RECTS.items():
            res = tr.track(enh(crop(gray[da], rect)), enh(crop(gray[db], rect)),
                           (0, 0, rect[2], rect[3]), (rect[0], rect[1]),
                           is_stable=(region == "stable"))
            st = vector_stats(res)
            sfx = "_motion" if region == "motion" else "_stable"
            rows.append({
                "pair": f"{da[5:]} -> {db[5:]}", "region": region,
                "n_py": st["n_vectors"], "n_mat": int(m["Number of Vectors" + sfx]),
                "mag_med_py": st["mag_median"], "mag_med_mat": m["Median Magnitude" + sfx],
                "mag_mean_py": st["mag_mean"], "mag_mean_mat": m["Mean Magnitude" + sfx],
                "dx_med_py": st["dx_median"], "dx_med_mat": m["Median Motion X" + sfx],
                "dy_med_py": st["dy_median"], "dy_med_mat": m["Median Motion Y" + sfx],
                "dir_med_py": st["dir_median"], "dir_med_mat": m["Median Direction" + sfx],
            })
    df = pd.DataFrame(rows)
    for c in ("mag_med", "mag_mean", "dx_med", "dy_med", "dir_med"):
        df["d_" + c] = df[c + "_py"] - df[c + "_mat"]
    df["d_n_percent"] = (df.n_py - df.n_mat) / df.n_mat * 100.0
    return df


def test_matlab_parity():
    df = compare()
    for c in ("mag_med", "mag_mean", "dx_med", "dy_med"):
        worst = df["d_" + c].abs().max()
        assert worst <= TOL_PX, f"{c}: worst difference {worst:.4f} px\n{df}"
    assert df.d_dir_med.abs().max() <= TOL_DEG, f"direction\n{df}"
    # vector counts differ slightly (SIFT implementation detail), but not much
    assert df.d_n_percent.abs().max() < 12.0, f"vector counts\n{df}"


if __name__ == "__main__":
    d = compare()
    pd.set_option("display.width", 250)
    print(d[["pair", "region", "n_mat", "n_py", "d_n_percent", "mag_med_mat", "mag_med_py", "d_mag_med",
             "dx_med_mat", "dx_med_py", "d_dx_med", "dy_med_mat", "dy_med_py", "d_dy_med",
             "dir_med_mat", "dir_med_py", "d_dir_med"]].round(4).to_string(index=False))
    print("\nworst |difference|:", {c: round(float(d["d_" + c].abs().max()), 4) for c in ("mag_med", "mag_mean", "dx_med", "dy_med", "dir_med")})
    print(f"vector-count difference: {d.d_n_percent.min():+.1f} % to {d.d_n_percent.max():+.1f} %")
    test_matlab_parity(); print("\nPARITY TEST PASSED")
