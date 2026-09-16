"""Stage 9: markdown summary of the deliverables."""
from __future__ import annotations

import pandas as pd

from .config import Config
from .utils import log


def _md(df: pd.DataFrame, cols=None, nd=1) -> str:
    if df is None or df.empty:
        return "_no data_\n"
    d = df[cols] if cols else df
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(nd)
    return d.to_markdown(index=False) + "\n" if hasattr(d, "to_markdown") else d.to_string(index=False) + "\n"


def run(cfg: Config) -> None:
    o = cfg.paths.output
    rd = lambda n, **k: pd.read_csv(o / n, **k) if (o / n).exists() else pd.DataFrame()
    inv, q, used = rd("inventory.csv"), rd("quality.csv"), rd("images_used.csv")
    if not q.empty:
        q = q[q.group.notna()]
    pv, win = rd("pairs_velocity.csv"), rd("velocity_windows.csv")
    annual, seasons, change = rd("velocity_annual.csv"), rd("velocity_seasonal.csv"), rd("velocity_seasonal_change.csv")
    inter, maxima, comp = rd("velocity_interannual.csv"), rd("velocity_local_maxima.csv"), rd("comparison_field_itslive.csv")
    L = []
    L.append("# Drang Drung Glacier TLC velocity pipeline: results summary\n")
    L.append("Method: Singh, Vijay & Azam (2026), Science of Remote Sensing 13, 100431. All values derived by `glacier_tlc`.\n")
    L.append("## 1. Data\n")
    if not inv.empty:
        L.append(f"- Images with EXIF time: {len(inv)}; daily picks near the target hour: {int(inv.daily_pick.sum())}\n")
    if not q.empty:
        L.append(f"- Usable after quality screening: {int(q.usable.sum())} / {len(q)} "
                 + "(" + ", ".join(f"{g}: {int(((q.group == g) & q.usable).sum())}/{int((q.group == g).sum())}" for g in cfg.groups) + ")\n")
        flags = q.loc[~q.usable, "flags"].str.split(";").explode().value_counts()
        if len(flags):
            L.append("- Exclusion reasons (an image can have several): " + ", ".join(f"{k} {v}" for k, v in flags.items() if k) + "\n")
    L.append("\n## 2. Camera groups and scaling\n")
    rows = []
    for g in cfg.groups.values():
        for r in g.rois.values():
            rows.append({"group": g.name, "period": f"{g.start} to {g.end}", "roi": r.name, "role": r.role, "rect_xywh": str(list(r.rect)),
                         "distance_m": r.distance_m, "gsd_m_per_px": round(cfg.roi_scale(r), 4)})
    L.append(_md(pd.DataFrame(rows), nd=4))
    if not pv.empty:
        L.append(f"\nPairs tracked: {pv.groupby(['group']).size().to_dict()} pair x ROI rows; valid {int(pv.valid.sum())} / {len(pv)}.\n")
        fs = pv.groupby("group").flow_sign_x.first().to_dict()
        L.append(f"Flow sign (image x -> along-flow): {fs}\n")
    L.append("\n## 3. Weekly-to-monthly velocities (paper Figs. 3, 5, 6)\n")
    if not win.empty:
        L.append(_md(win, ["window", "roi", "n_pairs", "mean_baseline_days", "feature_velocity_m_yr", "unc_feature_velocity_m_yr",
                           "horizontal_m_yr", "unc_horizontal_m_yr", "vertical_m_month", "unc_vertical_m_month"]))
    L.append("\n## 4. Annual and seasonal summaries\n")
    L.append(_md(annual, ["period", "roi", "n_windows", "n_pairs", "feature_velocity_m_yr_window_mean", "horizontal_m_yr_window_mean", "vertical_m_month_window_mean", "unc_horizontal_m_yr"]))
    L.append("\nSeasons:\n\n" + _md(seasons, ["period", "roi", "n_windows", "n_pairs", "feature_velocity_m_yr_window_mean", "horizontal_m_yr_window_mean", "vertical_m_month_window_mean"]))
    L.append("\nSeasonal change:\n\n" + _md(change))
    L.append("\nInterannual (same months, consecutive years):\n\n" + _md(inter))
    L.append("\n## 5. Short-term (daily) velocity maxima (paper Fig. 7)\n")
    L.append(_md(maxima))
    L.append("\n## 6. Comparison with field GNSS and ITS_LIVE (paper Sect. 5.4)\n")
    L.append(_md(comp, nd=2))
    L.append("\n## 7. Figures\n")
    for p in sorted((o / "figures").glob("*.png")) if (o / "figures").exists() else []:
        L.append(f"- figures/{p.name}\n")
    (o / "report.md").write_text("".join(L))
    log.info("report -> %s", o / "report.md")
