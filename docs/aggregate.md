# Stage 6 — `aggregate`

| | |
| --- | --- |
| **Module** | `glacier_tlc/aggregate.py` |
| **Command** | `python -m glacier_tlc aggregate` |
| **Reads** | `output/pairs_velocity.csv` |
| **Writes** | `velocity_windows.csv`, `velocity_annual.csv`, `velocity_seasonal.csv`, `velocity_seasonal_change.csv`, `velocity_interannual.csv`, `velocity_daily.csv`, `velocity_local_maxima.csv` (all in `output/`) |

## Overview

Reduces the per-pair table to the time-series products of the paper: velocity per
window (Figs. 3, 5, 6), annual and seasonal summaries with percentage changes
(Sect. 4.1, Table S1), and the short-term daily series with local maxima (Fig. 7).
It runs in seconds and is the stage to re-run after editing any `aggregation` or
`short_term` key.

The three quantities handled throughout are

```python
VEL_COLS = ["feature_velocity_m_yr", "horizontal_m_yr", "vertical_m_month"]
UNC_COLS = {feature → unc_feature_m_yr, horizontal → unc_horizontal_m_yr,
            vertical → unc_vertical_m_month}
```

## Helpers

### `_stat(x, w, how)`

Reduces a series after dropping non-finite values: `median` (default), `mean`, or
`weighted_mean` with weights `w²` (w = baseline in days, so long pairs dominate).
Empty → NaN.

### `_summarise(sel, how) -> dict`

For a set of pair rows: `n_pairs`, `n_images` (distinct files in A ∪ B),
`mean_baseline_days`, `date_start` (min `datetime_a`), `date_end` (max `datetime_b`),
and for each quantity `c`:

| Output | Definition |
| --- | --- |
| `c` | `_stat(sel[c], days, how)` — the window value |
| `c` with `_m_` → `_mean_m_` (e.g. `horizontal_mean_m_yr`) | plain mean, always, for comparison |
| `unc_c` | `nanmedian` of the pairs' `UNC_COLS[c]` — measurement uncertainty |
| `spread_c` | `nmad` across the pairs' `c` (NaN if fewer than 2 pairs) — between-pair variability |

## Windows — `aggregate_windows(cfg, pv)`

1. `valid = pv[pv.valid & (pv.days ≥ aggregation.min_days)]` (default 5 days).
2. For each `Window` from `cfg.windows()` (monthly per group, or custom) and each ROI,
   select pairs with `datetime_a ≥ window.start` **and**
   `datetime_b < window.end + 1 day` — both images inside the window.
3. Skip the window if it has fewer than `aggregation.min_pairs` pairs (shipped config
   20; code default 3).
4. Row: `window, window_start, window_end, group, roi` + `_summarise`.

### `velocity_windows.csv`

Columns: `window, window_start, window_end, group, roi, n_pairs, n_images,
mean_baseline_days, date_start, date_end`, then for each of feature / horizontal /
vertical: value, `*_mean_*`, `unc_*`, `spread_*` (for example `horizontal_m_yr,
horizontal_mean_m_yr, unc_horizontal_m_yr, spread_horizontal_m_yr`). 45 rows on the
Drang Drung dataset.

## Annual and seasonal — `annual_and_seasonal(cfg, pv, win)`

`period_rows(label, start, end)` for each ROI:

- `sel` — valid pairs (≥ `min_days`) with both images inside the period;
- `wsel` — rows of `velocity_windows.csv` whose `window_start ≥ start` and
  `window_end < end + 1 day` (windows fully inside the period);
- for each quantity: `c_window_mean` = mean of `wsel[c]` (the figure the paper's
  annual means correspond to), `c_pairs` = `_stat(sel[c], …, how)`, `unc_c` = median
  pair uncertainty.

Applied to `aggregation.annual_periods` → `velocity_annual.csv`, and to
`aggregation.seasons` → `velocity_seasonal.csv`. Columns of both:
`period, start, end, roi, n_windows, n_pairs`, then per quantity
`<c>_window_mean, <c>_pairs, unc_<c>`.

**Seasonal change** — for each `{reference, target}` in `season_comparisons`, each ROI
and each of `feature_velocity_m_yr`, `horizontal_m_yr`:
`change_percent = (target_window_mean − reference_window_mean) / reference_window_mean · 100`.
→ `velocity_seasonal_change.csv`: `comparison ("target vs reference"), roi, quantity,
reference_value, target_value, change_percent`.

**Interannual** (in `run`) — for each `{reference, target}` in
`aggregation.interannual` and each ROI present in both seasons: the `horizontal` and
`feature` window means of each side. → `velocity_interannual.csv`: `comparison, roi,
horizontal_reference_m_yr, horizontal_target_m_yr, feature_reference_m_yr,
feature_target_m_yr`.

## Short-term series — `short_term_series(cfg, pv, period)`

Per entry in `short_term.periods` (each may override `max_baseline_days`,
`smoothing_window_days` and `quantity`):

1. `sel` — valid pairs with `days ≤ max_baseline_days` (shipped config 3.0; code
   default 1.5) and both images inside the period.
2. `date = date_mid` rounded to the day: each pair is assigned to its mid-date.
3. Per ROI: group by `date` → `value` (median of `quantity`), `unc` (median of the
   matching `UNC_COLS` entry), `n_pairs`; re-index to a **complete daily calendar**
   (`asfreq("D")`) so missing days appear as NaN rows.
4. `trend` = centred rolling median over `smoothing_window_days` (default 5) with
   `min_periods = max(2, win // 2)`.
5. **Local maxima**: `half = max(1, win // 2)` (= 2). For each index
   `i in [half, len − half)` (edges excluded) with a finite trend,
   `neigh = trend[i−half : i+half+1]`; mark `local_max` if `trend[i] ≥ nanmax(neigh)`,
   at least two finite neighbours exist, and `trend[i] ≠ trend[i−1]` (a plateau is
   counted once, on its first day).
6. Return the daily table and a maxima table.

`run` concatenates over periods and writes `velocity_daily.csv`
(`date, value, unc, n_pairs, roi, trend, local_max, period`) and
`velocity_local_maxima.csv` (`period, roi, date, trend_value, daily_value, quantity`).
These two files are written only if at least one period is configured.

## Configuration

```yaml
aggregation:
  mode: monthly | custom          # custom needs aggregation.custom: [{label, start, end}]
  stat: median | mean | weighted_mean
  min_days: 5
  min_pairs: 20
  annual_periods: [{label, start, end}]
  seasons: [{label, start, end}]
  season_comparisons: [{reference, target}]     # labels from seasons
  interannual: [{reference, target}]            # labels from seasons
short_term:
  quantity: horizontal_m_yr
  max_baseline_days: 3.0
  smoothing_window_days: 5
  periods: [{label, start, end, [max_baseline_days], [smoothing_window_days], [quantity]}]
```

## Behaviour to be aware of

- `min_days` applies to the window, annual and seasonal statistics; `short_term`
  uses the opposite selection (`days ≤ max_baseline_days`). A 3-day pair is in the
  daily series and out of every window.
- The pair-inclusion rule (both images inside) means a window shorter than
  `min_days + 1` can never contain a pair; a month clipped to a few days by a group
  boundary (for example `2024-08b`, starting 19 Aug) has correspondingly few pairs.
- `season_comparisons` and `interannual` silently skip a comparison whose season has
  no rows for an ROI (for example a season entirely inside a data gap).
- `unc_*` at every level is a **median of per-pair uncertainties** — there is no √n
  reduction.
- `n_windows` counts windows *fully* inside the period, so a period starting
  mid-month excludes that month's window.

## See also

- [velocity.md](velocity.md) — the input columns.
- [config.md](config.md) — `cfg.windows()` and the `a`/`b` month split.
- [plots.md](plots.md), [report.md](report.md) — consumers.
