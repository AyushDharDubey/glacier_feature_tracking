# Glacier Tracking Module using Time Lapse Camera

Python implementation of the glacier-velocity methodology of

> Singh, P., Vijay, S., Azam, M.F. (2026). *High-Frequency observations of glacier ice
> velocities at Drang Drung Glacier, Western Himalaya, using a terrestrial time-lapse
> imaging system.* Science of Remote Sensing 13, 100431.
> https://doi.org/10.1016/j.srs.2026.100431

Every setting is in [config.yaml](config.yaml). What each setting means is in
[docs/configuration.md](docs/configuration.md).

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the pipeline

All commands run from the repository root.

```bash
python -m glacier_tlc all            # run all stages in order
python -m glacier_tlc --help         # list stages and options
```

Each stage reads the files written by the stage before it. The first time, run them in
this order if running them individually:

```bash
python -m glacier_tlc inventory
python -m glacier_tlc quality
python -m glacier_tlc extract
python -m glacier_tlc track
python -m glacier_tlc velocity
python -m glacier_tlc aggregate
python -m glacier_tlc plots
```

### Command-line options

| Option | Default | Meaning |
| --- | --- | --- |
| `stage` | required | One of `inventory`, `quality`, `extract`, `track`, `velocity`, `aggregate`, `plots`, or `all`. |
| `-c`, `--config` | `config.yaml` | Configuration file. Relative paths inside it are resolved from the folder the config file is in. |
| `-j`, `--workers` | CPUs - 1 | Number of worker processes. Used by `quality`, `extract` and `track`. |
| `--limit N` | none | `track` only: process just the first N image pairs. Use it for a quick test of new tracking settings. |
| `-v`, `--verbose` | off | Debug-level logging. |

### Quick test on a new dataset

Tracking every pair can take hours. To test the settings on a few pairs first, run:

```bash
python -m glacier_tlc inventory
python -m glacier_tlc quality
python -m glacier_tlc extract
python -m glacier_tlc track --limit 200
python -m glacier_tlc velocity
```

Then open `output/pairs_velocity.csv` and check `n_vectors` and `valid`. If the results
look right, delete `.cache/vectors` and run `track` without `--limit`.

## Pipeline stages

| # | Stage | What it does | Reads | Writes |
| --- | --- | --- | --- | --- |
| 1 | `inventory` | Reads EXIF capture times, keeps one image per day near `target_hour`, assigns each image to a camera group by date. | `input/*.jpg` | `output/inventory.csv` |
| 2 | `quality` | Scores every daily image (brightness, contrast, sharpness, clipping, scene visibility) and decides which are usable. Applies the manual include/exclude lists. | `inventory.csv` | `output/quality_assessment.csv`, `output/images_used.csv` |
| 3 | `extract` | Crops each ROI (plus a margin) from every usable image, applies contrast enhancement (CLAHE), and caches the crops. | `images_used.csv`, images | `.cache/crops/<group>/<image>.npz` |
| 4 | `track` | For every pair of usable images in the same group and every ROI: SIFT keypoints, then KLT optical flow checked forwards and backwards, then RANSAC affine outlier removal, then a flow-direction filter. | crops | `output/pairs_raw.csv`, `.cache/vectors/<group>/<A>__<B>.npz` |
| 5 | `velocity` | Subtracts the stable-region shift (camera motion) from each glacier ROI, computes the uncertainty (NMAD of the stable region), and converts pixels to m/yr and m/month. | `pairs_raw.csv`, vectors | `output/pairs_velocity.csv` |
| 6 | `aggregate` | Combines the per-pair velocities into monthly (or custom) windows, annual summaries and short-term daily series with local maxima. | `pairs_velocity.csv` | `output/velocity_windows.csv`, `velocity_annual.csv`, `velocity_daily.csv`, `velocity_local_maxima.csv` |
| 7 | `plots` | Draws the paper-style figures. | all of the above | `output/figures/*.png` |

### How a velocity is computed

For one image pair (A, B) taken `days` apart, and one glacier ROI:

1. Track features from A to B, which gives displacement vectors `(dx, dy)` in pixels.
2. Track the stable ROI the same way. Its median `(dx, dy)` is the apparent shift caused
   by the camera moving. Subtract it from every glacier vector.
3. Take the median of the corrected vectors: the magnitude gives the *feature velocity*,
   the x component gives the *horizontal* velocity and the y component gives the
   *vertical* motion.
4. Convert to metres with the ground sampling distance of that ROI:
   `GSD = distance_m x (sensor_width_mm / image_width_px) / focal_length_mm` (m per px),
   then divide by `days`.
5. Uncertainty = NMAD (normalised median absolute deviation) of the stable-region
   vectors, scaled the same way.

A pair-ROI result is valid only if both the glacier ROI and the stable ROI keep at
least `velocity.min_vectors` / `velocity.min_vectors_stable` vectors.

#### Sign conventions

- `horizontal_m_yr`: positive in the glacier's main flow direction. That direction is
  detected automatically per group, or set with `flow_sign_x`.
- `vertical_m_month`: positive upward. Negative values mean the surface is lowering
  (thinning).

## Outputs

Everything is written to `paths.output` (default `./output`).

| File | One row per | Key columns |
| --- | --- | --- |
| `inventory.csv` | image | `datetime`, `daily_pick` (the image chosen for that day), `group` (empty = outside every group, ignored) |
| `quality_assessment.csv` | daily image | quality metrics, `auto_ok`, `manual`, `usable`, `flags` (why an image was rejected: `low_visibility`, `blurry`, `low_contrast`, `dark`, `overexposed`, `clipped`, `manual_exclude`, `manual_include`) |
| `images_used.csv` | usable image | same columns, only `usable == True` rows |
| `pairs_raw.csv` | pair x ROI | uncorrected pixel statistics: `n_sift`, `n_klt`, `n_ransac`, `n_vectors`, `mag_*`, `dx_*`, `dy_*`, `dir_*` (median, mean, std, nmad) |
| `pairs_velocity.csv` | pair x glacier ROI | `valid`, `days`, `date_mid`, `feature_velocity_m_yr`, `horizontal_m_yr`, `vertical_m_month`, `unc_*` (uncertainties), `stable_*` (camera shift), `gsd_m_per_px`, `flow_sign_x` |
| `velocity_windows.csv` | window x ROI | `window`, `n_pairs`, `n_images`, the three velocities (using the configured statistic) and their `*_mean_*` versions, `unc_*`, `spread_*` (NMAD across pairs) |
| `velocity_annual.csv` | annual period x ROI | `*_window_mean` (mean of the window values), `*_pairs` (statistic over all pairs in the period), `unc_*` |
| `velocity_daily.csv` | day x ROI x short-term period | `value` (daily median), `unc`, `n_pairs`, `trend` (rolling median), `local_max` |
| `velocity_local_maxima.csv` | local maximum | `period`, `roi`, `date`, `trend_value`, `daily_value` |
| `figures/fig3_feature_velocity.png` | | feature velocity per window, one panel per ROI |
| `figures/fig3a_horizontal_velocity.png` | | horizontal velocity per window, all ROIs, plus optional reference lines |
| `figures/fig3b_vertical_motion.png` | | vertical motion per window |
| `figures/fig4_vectors_<label>_<group>_<roi>.png` | | tracked vectors of one long-baseline pair drawn over the image |
| `figures/fig5_field_<label>_<group>_<roi>.png` | | gridded median velocity field over a time window |
| `figures/fig6_short_term_<period>.png` | | daily velocity, trend and local maxima |
