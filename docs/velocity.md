# Stage 5 — `velocity`

| | |
| --- | --- |
| **Module** | `glacier_tlc/velocity.py` |
| **Command** | `python -m glacier_tlc velocity` |
| **Reads** | `output/pairs_raw.csv`, `.cache/vectors/` |
| **Writes** | `output/pairs_velocity.csv` |

## Overview

Converts each pair's raw pixel measurements into corrected, scaled velocities (paper
Sect. 3.3): subtract the stable-region displacement from every glacier vector, derive
the pair's uncertainty from the stable region's NMAD, convert pixels to metres with
the ROI's ground sampling distance, divide by the baseline, and split the result into
feature (magnitude), horizontal (along-flow) and vertical components.

The output has one row per pair × **motion** ROI; the stable ROI appears only through
its correction columns.

## Processing — `run(cfg)`

1. Load `pairs_raw.csv`. `min_vec = velocity.min_vectors` (fallback
   `tracking.min_vectors`, default 20); `min_vec_stable = velocity.min_vectors_stable`
   (fallback `min_vec`).
2. **For each group**, index the stable-ROI rows by `(file_a, file_b)`.
   **For each motion ROI** of the group, `gsd = cfg.roi_scale(roi)`.
   **For each pair row** of that ROI:
   1. Look up the stable row for the same pair; if absent (stable not tracked) the
      pair is **skipped** — no output row at all.
   2. `s_dx, s_dy = stable dx_median, dy_median`;
      `s_ok = stable n_vectors ≥ min_vec_stable and s_dx finite`.
   3. Load this ROI's vectors from `.cache/vectors/<group>/<A>__<B>.npz`
      (`_load_vectors`; missing file → empty arrays).
   4. If vectors exist and `s_ok`:

      ```python
      vc         = vec − (s_dx, s_dy)                 # per-vector correction
      mag_c      = hypot(vc.x, vc.y)
      mag_c_med, dx_c, dy_c = median(mag_c), median(vc.x), median(vc.y)
      mag_c_nmad = nmad(mag_c)
      ```

      otherwise all four are NaN.
   5. `valid = s_ok and n_vectors ≥ min_vec and mag_c_med finite`.
   6. Scale factors: `k_yr = gsd / days · 365.25`, `k_mo = gsd / days · 30.4375`.
   7. Emit the record (columns below). Note `vertical = −dy` because image y points
      down.
3. Build the DataFrame; empty → `SystemExit("run track first")`.
4. **Flow sign per group** (`flow_sign_x` column):
   - if the group's `flow_sign_x` is `+1` or `−1`, use it;
   - otherwise (`auto`): among rows of the group that are `valid` and have
     `days ≥ velocity.flow_sign_min_days` (default 7), take the median of
     `dx_corr_px`; the sign is `−1` if that median is `< 0`, else `+1`; log the
     decision.
   - The automatic decision is made over **all motion ROIs of the group together**,
     not per ROI.
5. `horizontal_m_yr = dx_m_yr · flow_sign_x`;
   `horizontal_px_day = dx_corr_px · flow_sign_x / days`.
6. Write `pairs_velocity.csv`; log the row count and the number of valid rows.

Invalid pairs are **kept** with `valid = False` (and NaN corrected values) so that
nothing disappears silently; every downstream stage filters on `valid`.

## Output — `output/pairs_velocity.csv`

One row per pair × motion ROI.

| Column | Unit | Meaning |
| --- | --- | --- |
| `group`, `roi`, `file_a`, `file_b`, `datetime_a`, `datetime_b`, `days` | | the pair |
| `date_mid` | datetime | midpoint of A and B (used by the short-term series and plots) |
| `n_vectors`, `n_vectors_stable` | | final vector counts of the ROI and of the stable region |
| `valid` | bool | see step 2.5 |
| `gsd_m_per_px`, `distance_m` | m/px, m | scale used |
| `mag_median_px`, `dx_median_px`, `dy_median_px`, `dir_median_deg` | px, ° | **raw** (uncorrected) medians copied from `pairs_raw.csv` |
| `stable_dx_px`, `stable_dy_px`, `stable_mag_median_px` | px | the stable-region medians that were subtracted |
| `stable_nmad_mag_px`, `stable_nmad_dx_px`, `stable_nmad_dy_px` | px | stable-region NMADs (the uncertainty source) |
| `mag_corr_median_px` | px | median magnitude of the **corrected** vectors |
| `mag_corr_nmad_px` | px | NMAD of corrected magnitudes within the ROI (internal spread) |
| `dx_corr_px`, `dy_corr_px` | px | median corrected components |
| `feature_velocity_m_yr` | m/yr | `mag_corr_median_px · k_yr` |
| `dx_m_yr` | m/yr | `dx_corr_px · k_yr`, signed in image x |
| `vertical_m_month` | m/month | `−dy_corr_px · k_mo` (positive up) |
| `vertical_m_yr` | m/yr | `−dy_corr_px · k_yr` |
| `unc_feature_m_yr` | m/yr | `stable_nmad_mag_px · k_yr` |
| `unc_horizontal_m_yr` | m/yr | `stable_nmad_dx_px · k_yr` |
| `unc_vertical_m_month` | m/month | `stable_nmad_dy_px · k_mo` |
| `spread_feature_m_yr` | m/yr | `mag_corr_nmad_px · k_yr` |
| `flow_sign_x` | ±1 | sign applied to image x for this group |
| `horizontal_m_yr` | m/yr | `dx_m_yr · flow_sign_x` — positive along flow |
| `horizontal_px_day` | px/day | the same, in pixels per day |

Uncertainties are scaled with the **glacier ROI's** GSD, not the stable ROI's, so
they are in the units of the velocity they qualify.

## Configuration

```yaml
velocity:
  min_vectors: 20
  min_vectors_stable: 20
  flow_sign_x: auto        # or +1 / -1; can also be set per group under groups.GRPx.flow_sign_x
  flow_sign_min_days: 7
distances_m: {...}         # → gsd via config.roi_scale
groups.GRPx.rois.*.scale_m_per_px   # optional GSD override per ROI
```

## Behaviour to be aware of

- The stage needs the vector cache. If `.cache/vectors/` has been deleted but
  `pairs_raw.csv` still exists, every row gets NaN corrected values and
  `valid = False`.
- Because the correction is applied per vector, `mag_corr_median_px` is **not** equal
  to `|mag_median_px − stable_mag_median_px|`; the magnitude is taken after the
  subtraction.
- Only ROIs present in `pairs_raw.csv` are processed; with the shipped
  `tracking.rois`, ROI4 rows do not appear even though ROI4 is defined in the config.
- Runtime is about 2 min for 28k pairs (one `np.load` per pair × ROI).

## See also

- [track.md](track.md) — producer of the inputs.
- [aggregate.md](aggregate.md) — the consumer.
- [config.md](config.md) — `roi_scale` and `flow_sign_x` resolution.
