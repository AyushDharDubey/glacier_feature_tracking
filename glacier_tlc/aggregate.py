"""Stage 6: temporal aggregation of the per-pair velocities.

* windows   : weekly-to-monthly velocity per ROI (paper Figs. 3, 5, 6). All
              pairs with both images inside the window and a baseline of at
              least `min_days` contribute; the window value is the median (or
              mean / baseline-weighted mean) of the per-pair values, the
              uncertainty is the median of the per-pair stable-region
              uncertainties, and the spread is the NMAD across the pairs.
* annual    : mean over the windows inside the annual period + a direct
              per-pair median over the same period.
* seasonal  : summer vs winter-spring speed-up (%).
* interannual: same calendar months in consecutive years (paper Table S1).
* short-term: daily series from short-baseline pairs in a chosen period, a
              moving-window trend and its local maxima (paper Fig. 7).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import Config
from .utils import log, nmad

VEL_COLS = ["feature_velocity_m_yr", "horizontal_m_yr", "vertical_m_month"]
UNC_COLS = {"feature_velocity_m_yr": "unc_feature_m_yr", "horizontal_m_yr": "unc_horizontal_m_yr", "vertical_m_month": "unc_vertical_m_month"}


def _stat(x: pd.Series, w: pd.Series, how: str) -> float:
    x = x.to_numpy(float); w = w.to_numpy(float)
    ok = np.isfinite(x)
    x, w = x[ok], w[ok]
    if x.size == 0:
        return np.nan
    if how == "mean":
        return float(x.mean())
    if how == "weighted_mean":  # inverse-variance weights ~ baseline^2
        return float(np.average(x, weights=w ** 2))
    return float(np.median(x))


def _summarise(sel: pd.DataFrame, how: str) -> dict:
    out = {"n_pairs": len(sel), "n_images": len(set(sel.file_a) | set(sel.file_b)),
           "mean_baseline_days": float(sel.days.mean()) if len(sel) else np.nan,
           "date_start": sel.datetime_a.min(), "date_end": sel.datetime_b.max()}
    for c in VEL_COLS:
        out[c] = _stat(sel[c], sel.days, how)
        out[c.replace("_m_", "_mean_m_")] = _stat(sel[c], sel.days, "mean")
        out["unc_" + c] = float(np.nanmedian(sel[UNC_COLS[c]])) if len(sel) else np.nan
        out["spread_" + c] = nmad(sel[c]) if len(sel) > 1 else np.nan
    return out


def aggregate_windows(cfg: Config, pv: pd.DataFrame) -> pd.DataFrame:
    agg = cfg.aggregation
    how = agg.get("stat", "median")
    min_days = float(agg.get("min_days", 5))
    min_pairs = int(agg.get("min_pairs", 3))
    rows = []
    valid = pv[pv.valid & (pv.days >= min_days)]
    for w in cfg.windows():
        ws, we = pd.Timestamp(w.start), pd.Timestamp(w.end) + pd.Timedelta(days=1)
        for roi in sorted(valid.roi.unique()):
            sel = valid[(valid.roi == roi) & (valid.datetime_a >= ws) & (valid.datetime_b < we)]
            if len(sel) < min_pairs:
                continue
            r = {"window": w.label, "window_start": w.start, "window_end": w.end, "group": sel.group.iloc[0], "roi": roi}
            r.update(_summarise(sel, how))
            rows.append(r)
    df = pd.DataFrame(rows)
    return df


def annual_and_seasonal(cfg: Config, pv: pd.DataFrame, win: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    agg = cfg.aggregation
    how = agg.get("stat", "median")
    min_days = float(agg.get("min_days", 5))
    valid = pv[pv.valid & (pv.days >= min_days)]
    rois = sorted(valid.roi.unique())

    def period_rows(label, start, end):
        out = []
        s, e = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
        for roi in rois:
            sel = valid[(valid.roi == roi) & (valid.datetime_a >= s) & (valid.datetime_b < e)]
            wsel = win[(win.roi == roi) & (pd.to_datetime(win.window_start) >= s) & (pd.to_datetime(win.window_end) < e)]
            r = {"period": label, "start": start, "end": end, "roi": roi, "n_windows": len(wsel), "n_pairs": len(sel)}
            for c in VEL_COLS:
                r[c + "_window_mean"] = float(wsel[c].mean()) if len(wsel) else np.nan
                r[c + "_pairs"] = _stat(sel[c], sel.days, how) if len(sel) else np.nan
                r["unc_" + c] = float(np.nanmedian(sel[UNC_COLS[c]])) if len(sel) else np.nan
            out.append(r)
        return out

    annual = pd.DataFrame(sum((period_rows(p["label"], p["start"], p["end"]) for p in agg.get("annual_periods", [])), []))
    seasons = pd.DataFrame(sum((period_rows(p["label"], p["start"], p["end"]) for p in agg.get("seasons", [])), []))
    # seasonal change (%): each comparison is a pair of season labels
    comp_rows = []
    for c in agg.get("season_comparisons", []):
        a, b = c["reference"], c["target"]
        for roi in rois:
            ra = seasons[(seasons.period == a) & (seasons.roi == roi)]
            rb = seasons[(seasons.period == b) & (seasons.roi == roi)]
            if ra.empty or rb.empty:
                continue
            for c_ in ("feature_velocity_m_yr", "horizontal_m_yr"):
                va, vb = float(ra[c_ + "_window_mean"].iloc[0]), float(rb[c_ + "_window_mean"].iloc[0])
                comp_rows.append({"comparison": f"{b} vs {a}", "roi": roi, "quantity": c_, "reference_value": va, "target_value": vb,
                                  "change_percent": (vb - va) / va * 100.0 if va and np.isfinite(va) else np.nan})
    return annual, seasons, pd.DataFrame(comp_rows)


def short_term_series(cfg: Config, pv: pd.DataFrame, period: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily horizontal velocity from short-baseline pairs + moving-window local maxima."""
    st = cfg.short_term
    max_days = float(period.get("max_baseline_days", st.get("max_baseline_days", 1.5)))
    win_days = int(period.get("smoothing_window_days", st.get("smoothing_window_days", 5)))
    quantity = period.get("quantity", st.get("quantity", "horizontal_m_yr"))
    s, e = pd.Timestamp(period["start"]), pd.Timestamp(period["end"]) + pd.Timedelta(days=1)
    sel = pv[pv.valid & (pv.days <= max_days) & (pv.datetime_a >= s) & (pv.datetime_b < e)].copy()
    sel["date"] = sel.date_mid.dt.round("D")  # pair assigned to its (rounded) mid date
    rows, maxima = [], []
    half = max(1, win_days // 2)
    for roi in sorted(sel.roi.unique()):
        d = sel[sel.roi == roi].groupby("date").agg(value=(quantity, "median"), unc=(UNC_COLS.get(quantity, "unc_horizontal_m_yr"), "median"), n_pairs=(quantity, "size")).reset_index()
        d = d.set_index("date").asfreq("D").reset_index()
        d["roi"] = roi
        # moving-window trend (centred rolling median) and its local maxima:
        # a day is a maximum when the trend there is the highest within +-half window
        d["trend"] = d.value.rolling(win_days, center=True, min_periods=max(2, win_days // 2)).median()
        t = d.trend.to_numpy(float)
        is_max = np.zeros(len(t), bool)
        for i in range(half, len(t) - half):  # skip the edges of the series
            if not np.isfinite(t[i]):
                continue
            lo, hi = max(0, i - half), min(len(t), i + half + 1)
            neigh = t[lo:hi]
            if t[i] >= np.nanmax(neigh) and np.isfinite(neigh).sum() > 1 and not (i > lo and t[i] == t[i - 1]):
                is_max[i] = True
        d["local_max"] = is_max
        rows.append(d)
        for r in d[d.local_max].itertuples(index=False):
            maxima.append({"period": period.get("label", f"{period['start']}_{period['end']}"), "roi": roi, "date": r.date.date(),
                           "trend_value": r.trend, "daily_value": r.value, "quantity": quantity})
    daily = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "value", "unc", "n_pairs", "roi", "trend", "local_max"])
    return daily, pd.DataFrame(maxima)


def run(cfg: Config) -> None:
    pv = pd.read_csv(cfg.paths.output / "pairs_velocity.csv", parse_dates=["datetime_a", "datetime_b", "date_mid"])
    out = cfg.paths.output
    win = aggregate_windows(cfg, pv)
    win.to_csv(out / "velocity_windows.csv", index=False)
    log.info("aggregate: %d window x ROI rows -> velocity_windows.csv", len(win))
    annual, seasons, comps = annual_and_seasonal(cfg, pv, win)
    annual.to_csv(out / "velocity_annual.csv", index=False)
    seasons.to_csv(out / "velocity_seasonal.csv", index=False)
    comps.to_csv(out / "velocity_seasonal_change.csv", index=False)
    # interannual comparisons: same months, consecutive years
    rows = []
    for c in cfg.aggregation.get("interannual", []):
        a = seasons[seasons.period == c["reference"]]; b = seasons[seasons.period == c["target"]]
        for roi in sorted(set(a.roi) & set(b.roi)):
            ra, rb = a[a.roi == roi].iloc[0], b[b.roi == roi].iloc[0]
            rows.append({"comparison": f"{c['target']} vs {c['reference']}", "roi": roi,
                         "horizontal_reference_m_yr": ra.horizontal_m_yr_window_mean, "horizontal_target_m_yr": rb.horizontal_m_yr_window_mean,
                         "feature_reference_m_yr": ra.feature_velocity_m_yr_window_mean, "feature_target_m_yr": rb.feature_velocity_m_yr_window_mean})
    pd.DataFrame(rows).to_csv(out / "velocity_interannual.csv", index=False)
    # short-term daily series
    dailies, maxima = [], []
    for period in cfg.short_term.get("periods", []):
        d, m = short_term_series(cfg, pv, period)
        d["period"] = period.get("label", "")
        dailies.append(d); maxima.append(m)
    if dailies:
        pd.concat(dailies, ignore_index=True).to_csv(out / "velocity_daily.csv", index=False)
        pd.concat(maxima, ignore_index=True).to_csv(out / "velocity_local_maxima.csv", index=False)
        log.info("aggregate: short-term series for %d period(s), %d local maxima", len(dailies), sum(len(m) for m in maxima))
