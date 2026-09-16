"""Stage 7: comparison with the in-situ GNSS stake velocity and ITS_LIVE
(paper Sect. 3.4 / 5.4). The reference values are read from the config
(`reference:` section); ITS_LIVE values can be entered per ROI from the
ITS_LIVE portal for the same period."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config
from .utils import log


def run(cfg: Config) -> pd.DataFrame:
    ref = cfg.reference
    annual = pd.read_csv(cfg.paths.output / "velocity_annual.csv")
    if annual.empty:
        log.warning("compare: no annual rows"); return annual
    label = ref.get("annual_period_label") or annual.period.iloc[0]
    a = annual[annual.period == label]
    its = ref.get("its_live_m_yr", {})
    field = ref.get("field_observation", {})
    rows = []
    for r in a.itertuples(index=False):
        h = float(r.horizontal_m_yr_window_mean); f = float(r.feature_velocity_m_yr_window_mean)
        rows.append({
            "period": label, "roi": r.roi, "n_windows": r.n_windows,
            "tlc_horizontal_m_yr": h, "tlc_feature_velocity_m_yr": f, "tlc_uncertainty_m_yr": r.unc_horizontal_m_yr,
            "its_live_m_yr": its.get(r.roi, np.nan),
            "tlc_minus_its_live_m_yr": h - its.get(r.roi, np.nan) if r.roi in its else np.nan,
            "tlc_over_its_live": h / its[r.roi] if r.roi in its and its[r.roi] else np.nan,
            "field_gnss_m_yr": field.get("velocity_m_yr", np.nan) if field.get("roi") == r.roi else np.nan,
            "tlc_minus_field_m_yr": h - field["velocity_m_yr"] if field.get("roi") == r.roi else np.nan,
            "field_note": field.get("note", "") if field.get("roi") == r.roi else "",
        })
    df = pd.DataFrame(rows)
    df.to_csv(cfg.paths.output / "comparison_field_itslive.csv", index=False)
    log.info("compare:\n%s", df.round(2).to_string(index=False))
    return df
