# Stage 7 — `plots`

| | |
| --- | --- |
| **Module** | `glacier_tlc/plots.py` |
| **Command** | `python -m glacier_tlc plots` |
| **Reads** | `pairs_velocity.csv`, `velocity_windows.csv`, `quality.csv`, `velocity_daily.csv`, `.cache/vectors/`, `.cache/crops/`, optional ERA5 CSV |
| **Writes** | `output/figures/*.png` |

## Overview

Draws the paper-style result figures (Figs. 3–7) and a set of quality-assurance
figures from the CSVs and caches. Matplotlib runs with the `Agg` backend, so no
display is needed. The stage has no numerical side effects and can be re-run freely.

ROI colours are fixed: `ROI1 #e4572e`, `ROI2 #2ca25f`, `ROI3 #3b7dd8`,
`ROI4 #9467bd`; anything else is grey.

## `run(cfg)`

1. Create `output/figures/`.
2. Load `pairs_velocity.csv`, `velocity_windows.csv`, and `quality.csv` if present.
3. `rois = plots.rois`, or every ROI in the windows table.
4. `fig_windows` (if windows exist) → Figs. 3, 5, 6.
5. `fig_short_term` if `velocity_daily.csv` exists and has rows for those ROIs → Fig. 7.
6. `fig_vectors` → Fig. 4 overlays (if `plots.vector_overlays` is configured).
7. `fig_qa` → four QA figures.

## Figures

### `_bars(ax, w, col, unc_col, roi)`

Draws one window as a horizontal line from `date_start` to `date_end` at the window
value, with a translucent band of ± the uncertainty column. Windows with a non-finite
value are skipped. Used by all three window figures.

### `fig_windows` → Figs. 3, 5, 6

| File | Content |
| --- | --- |
| `fig3_feature_velocity.png` | one panel per ROI; `feature_velocity_m_yr` ± `unc_feature_velocity_m_yr` |
| `fig5_horizontal_velocity.png` | all ROIs on one axis; `horizontal_m_yr` ± `unc_horizontal_m_yr`. If a `reference:` section exists in the config, dotted lines are drawn at `reference.its_live_m_yr` per ROI and a dashed black line at `reference.field_observation.velocity_m_yr` |
| `fig6_vertical_motion.png` | one panel per ROI; `vertical_m_month` ± `unc_vertical_m_month`, with a zero line |

### `fig_short_term` → `fig7_short_term_<period>.png`

One figure per `period` in `velocity_daily.csv`, one panel per ROI: the daily `value`
with `unc` error bars, the `trend` line, and red stars at `local_max` annotated with
the trend value and date. If `auxiliary.era5_daily_csv` points to an existing file
(absolute, or relative to the parent of the image folder) with a `net_radiation`
column, it is plotted on a twin y-axis.

### `fig_vectors` → `fig4_vectors_<label>_<group>.png`

For each spec in `plots.vector_overlays` and each group:

1. Select valid pairs with both images in `[start, end]`.
2. `rois` = the group's motion ROIs that are in `spec.rois` (or `plots.rois`) **and**
   were actually tracked.
3. Pick the pair with the **longest baseline** that has a valid row for every such ROI.
4. Load its vector file and image B's crop file; take the stable correction
   `(stable_dx_px, stable_dy_px)` from the pair's row.
5. Per ROI: draw the raw crop; subtract the stable shift from the vectors; thin to
   `max_vectors` (seeded RNG 0) if there are more; colour each arrow by its corrected
   magnitude converted to m/month with the ROI's GSD and the pair's baseline;
   `quiver` with `scale = 1/arrow_scale` and colour range `[0, vmax_m_month]`.
6. One colour bar for the figure.

A group with no valid pair in the date range produces no file (with the shipped
config, `winter` yields only `GRP1` and `summer` only `GRP2`).

### `fig_qa`

| File | Content |
| --- | --- |
| `qa_camera_shift.png` | pairs with `days ≤ 1.5` (one row per pair): `stable_dx_px`, `stable_dy_px` versus date (top) and `stable_nmad_mag_px` (bottom) — the camera-motion diagnostic |
| `qa_image_quality.png` | `sharpness`, `vis_inliers`, `brightness` from `quality.csv` versus date; green = usable, red = excluded (skipped if `quality.csv` is absent) |
| `qa_vectors_per_pair.png` | `n_vectors` versus `date_mid` per ROI, log y-axis |
| `qa_pair_velocities.png` | one panel per ROI: `horizontal_m_yr` of every valid pair versus `date_mid`, coloured by baseline (`viridis`, 0–35 days); y-limits fixed at −40 … 80 m/yr |

## Configuration

```yaml
plots:
  rois: [ROI1, ROI2, ROI3]
  vector_overlays:
    - {label: winter, start: 2023-12-01, end: 2024-01-31, vmax_m_month: 3.5, arrow_scale: 4, max_vectors: 300}
    # optional per spec: rois: [ROI1]
auxiliary:
  era5_daily_csv: null          # CSV with columns date,net_radiation for Fig. 7
reference:                      # optional; reference lines on Fig. 5
  its_live_m_yr: {ROI1: 13.0, ROI2: 9.0, ROI3: 3.5}
  field_observation: {roi: ROI2, velocity_m_yr: 23.64}
```

## Behaviour to be aware of

- `fig_vectors` needs **both caches**; if `.cache/` was deleted after `track`, it
  raises `FileNotFoundError`. Delete or empty `vector_overlays` to skip it.
- Fig. 4 shows the single longest-baseline pair in the range, not an average — the
  arrows are one pair's vectors.
- `qa_pair_velocities.png` uses a hard-coded y-range (−40 … 80 m/yr) and baseline
  colour range (0–35 days); values outside them are clipped from view, not from the
  data.
- Figures are overwritten on every run but never deleted, so a figure from a previous
  configuration (for example an old overlay label) persists until removed by hand.

## See also

- [aggregate.md](aggregate.md), [velocity.md](velocity.md), [quality.md](quality.md)
  — the inputs.
- [extract.md](extract.md), [track.md](track.md) — the caches used for Fig. 4.
- [report.md](report.md) — lists whatever PNGs exist in `output/figures/`.
