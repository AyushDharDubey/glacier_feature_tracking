"""Stage 5: camera-motion correction, uncertainty and photogrammetric scaling
(paper Sect. 3.3).

For every image pair
  * the stable, non-moving terrain region gives the apparent displacement
    caused by camera movement; its median (dx, dy) is subtracted from every
    glacier motion vector, and the NMAD of the stable-region displacement is
    the uncertainty of the pair;
  * the corrected vectors are summarised by the median magnitude (feature
    velocity) and the median x / y components (horizontal = parallel to the
    glacier surface, vertical = normal to it; the camera looks roughly
    perpendicular to the flow direction);
  * pixels are converted to metres with the ground sampling distance
    GSD = distance * pixel_pitch / focal_length  (m / px)
    computed from the camera sensor size, image resolution, focal length and
    the measured camera-to-ROI distance, then divided by the time separation.

Sign conventions of the outputs
  horizontal_m_yr : positive along the dominant flow direction of the group
                    (flow_sign_x, auto-detected or configured)
  vertical_m_month: positive upward (image y points down, so vertical = -dy);
                    negative values = surface lowering / thinning
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .utils import DAYS_PER_MONTH, DAYS_PER_YEAR, log, nmad


def _load_vectors(path: Path, roi: str):
    try:
        z = np.load(path)
        return z[f"{roi}_p0"], z[f"{roi}_vec"]
    except Exception:
        return np.empty((0, 2)), np.empty((0, 2))


def run(cfg: Config) -> pd.DataFrame:
    vc = cfg.velocity
    raw = pd.read_csv(cfg.paths.output / "pairs_raw.csv", parse_dates=["datetime_a", "datetime_b"])
    min_vec = int(vc.get("min_vectors", cfg.tracking.get("min_vectors", 20)))
    min_vec_stable = int(vc.get("min_vectors_stable", min_vec))
    vec_dir = cfg.paths.cache / "vectors"

    records = []
    for gname, g in cfg.groups.items():
        sub = raw[raw.group == gname]
        if sub.empty:
            continue
        stable_name = g.stable.name
        stab = sub[sub.roi == stable_name].set_index(["file_a", "file_b"])
        for roi in g.motion_rois:
            gsd = cfg.roi_scale(roi)
            rows = sub[sub.roi == roi.name]
            for r in rows.itertuples(index=False):
                key = (r.file_a, r.file_b)
                if key not in stab.index:
                    continue
                s = stab.loc[key]
                s_dx, s_dy = float(s.dx_median), float(s.dy_median)
                s_ok = int(s.n_vectors) >= min_vec_stable and np.isfinite(s_dx)
                # corrected vectors -> median magnitude / components
                p0, vec = _load_vectors(vec_dir / gname / f"{Path(r.file_a).stem}__{Path(r.file_b).stem}.npz", roi.name)
                if len(vec) and s_ok:
                    vc_ = vec - np.array([s_dx, s_dy])
                    mag_c = np.hypot(vc_[:, 0], vc_[:, 1])
                    mag_c_med, dx_c, dy_c = float(np.median(mag_c)), float(np.median(vc_[:, 0])), float(np.median(vc_[:, 1]))
                    mag_c_nmad = nmad(mag_c)
                else:
                    mag_c_med = dx_c = dy_c = mag_c_nmad = np.nan
                valid = bool(s_ok and int(r.n_vectors) >= min_vec and np.isfinite(mag_c_med))
                days = float(r.days)
                k_yr, k_mo = gsd / days * DAYS_PER_YEAR, gsd / days * DAYS_PER_MONTH
                records.append({
                    "group": gname, "roi": roi.name, "file_a": r.file_a, "file_b": r.file_b,
                    "datetime_a": r.datetime_a, "datetime_b": r.datetime_b, "days": days,
                    "date_mid": r.datetime_a + (r.datetime_b - r.datetime_a) / 2,
                    "n_vectors": int(r.n_vectors), "n_vectors_stable": int(s.n_vectors), "valid": valid,
                    "gsd_m_per_px": gsd, "distance_m": roi.distance_m,
                    # raw (uncorrected) pixel statistics
                    "mag_median_px": r.mag_median, "dx_median_px": r.dx_median, "dy_median_px": r.dy_median,
                    "dir_median_deg": r.dir_median,
                    # stable region (camera motion) and uncertainty in pixels
                    "stable_dx_px": s_dx, "stable_dy_px": s_dy, "stable_mag_median_px": float(s.mag_median),
                    "stable_nmad_mag_px": float(s.mag_nmad), "stable_nmad_dx_px": float(s.dx_nmad), "stable_nmad_dy_px": float(s.dy_nmad),
                    # corrected pixel statistics
                    "mag_corr_median_px": mag_c_med, "mag_corr_nmad_px": mag_c_nmad, "dx_corr_px": dx_c, "dy_corr_px": dy_c,
                    # metric
                    "feature_velocity_m_yr": mag_c_med * k_yr,
                    "dx_m_yr": dx_c * k_yr,  # signed image-x component (flow sign applied below)
                    "vertical_m_month": -dy_c * k_mo,
                    "vertical_m_yr": -dy_c * k_yr,
                    "unc_feature_m_yr": float(s.mag_nmad) * k_yr,
                    "unc_horizontal_m_yr": float(s.dx_nmad) * k_yr,
                    "unc_vertical_m_month": float(s.dy_nmad) * k_mo,
                    "spread_feature_m_yr": mag_c_nmad * k_yr,  # NMAD of corrected magnitudes within the ROI
                })
    df = pd.DataFrame(records)
    if df.empty:
        raise SystemExit("velocity: no pair rows (run `track` first)")

    # flow sign: horizontal velocity positive along the dominant flow direction
    df["flow_sign_x"] = 1
    min_days_sign = float(vc.get("flow_sign_min_days", 7))
    for gname, g in cfg.groups.items():
        m = (df.group == gname)
        if not m.any():
            continue
        if isinstance(g.flow_sign_x, (int, float)) and g.flow_sign_x in (1, -1):
            sign = int(g.flow_sign_x)
        else:
            sel = df[m & df.valid & (df.days >= min_days_sign)]
            med = float(np.nanmedian(sel.dx_corr_px)) if len(sel) else 0.0
            sign = -1 if med < 0 else 1
            log.info("velocity: group %s flow_sign_x auto -> %+d (median corrected dx of %d long-baseline pairs = %.3f px)", gname, sign, len(sel), med)
        df.loc[m, "flow_sign_x"] = sign
    df["horizontal_m_yr"] = df.dx_m_yr * df.flow_sign_x
    df["horizontal_px_day"] = df.dx_corr_px * df.flow_sign_x / df.days

    out = cfg.paths.output / "pairs_velocity.csv"
    df.to_csv(out, index=False)
    log.info("velocity: %d pair-ROI rows, %d valid -> %s", len(df), int(df.valid.sum()), out)
    return df
