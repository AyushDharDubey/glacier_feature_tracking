# Configuration reference

All settings are read from a YAML file, `config.yaml` by default (choose another with
`python -m glacier_tlc <stage> --config other.yaml`). This page describes every section
and every key.

- The Default column is the value the code uses when the key is missing, which is not
  always the value in `config.yaml`. "required" means the key has no default.
- Dates are ISO `YYYY-MM-DD`. Ranges include both end dates.
- Pixel coordinates are full-resolution image pixels with the origin at the top-left:
  x points right, y points down.
- The stages that read a section are listed in brackets under its heading. After
  changing a setting, re-run from the first of those stages. `extract` and `track`
  reuse cached results by file name, so if you change ROI rectangles, `pad_px`,
  `enhancement` or tracking settings, delete `.cache/crops` and/or `.cache/vectors`
  first.

## Contents

- [paths](#paths)
- [camera](#camera)
- [distances_m](#distances_m)
- [inventory](#inventory)
- [groups](#groups)
- [quality](#quality)
- [enhancement](#enhancement)
- [tracking](#tracking)
- [pairs](#pairs)
- [velocity](#velocity)
- [aggregation](#aggregation)
- [short_term](#short_term)
- [plots](#plots)
- [reference and auxiliary (optional)](#reference-and-auxiliary-optional)

## paths

[all stages]

| Key | Default | Meaning |
| --- | --- | --- |
| `images` | required | Folder with the input JPEGs. |
| `cache` | `.cache` | Folder for the ROI crops and the tracked vectors. It can grow to several GB. |
| `output` | `output` | Folder for the CSV results and `figures/`. |

Relative paths are resolved from the folder that contains the config file, not from the
folder you run the command in.

## camera

[velocity, plots]

Used to convert pixels to metres.

| Key | Meaning |
| --- | --- |
| `model` | Label only. |
| `sensor_width_mm` | Physical sensor width. Canon EOS 2000D: 22.3 mm. |
| `sensor_height_mm` | Physical sensor height (not used in any calculation). |
| `image_width_px` | Image width in pixels. |
| `image_height_px` | Image height in pixels. `extract` skips images whose size differs from `image_width_px` x `image_height_px`. |
| `focal_length_mm` | Lens focal length. |

All keys are required. The ground sampling distance (metres per pixel) of an ROI at
distance `D` is:

```text
GSD = D x (sensor_width_mm / image_width_px) / focal_length_mm
```

With the shipped values, GSD = D x 0.000155 m/px. At 900 m that is 0.14 m/px.

## distances_m

[velocity, plots]

Distance from the camera to each ROI, in metres, keyed by ROI name:

```yaml
distances_m:
  ROI1: 900
  ROI2: 700
  ROI3: 450
  stable: 900
```

These values apply to that ROI name in every group. To use a different value in one
group, set `distance_m` (or `scale_m_per_px`) on the ROI itself (see [groups](#groups)).
Every ROI needs a distance from one of these places, or the config fails to load.

The stable ROI's distance is required but has no effect on any result, because the
camera-motion correction is applied in pixels.

## inventory

[inventory]

| Key | Default | Meaning |
| --- | --- | --- |
| `extensions` | `[.jpg, .jpeg]` | File extensions to read (case-insensitive). |
| `target_hour` | `13.0` | Preferred capture time, in decimal local hours (13.5 = 13:30). The paper uses the ~13:00 image of each day. |
| `hour_window` | `2.0` | Only images within +/- this many hours of `target_hour` are considered. On days with no image inside the window, no image is used. |

For each day, the image closest to `target_hour` is kept (`daily_pick = True` in
`inventory.csv`).

## groups

[every stage from inventory on]

The camera moves slightly whenever it is serviced or buried by snow, so the same
pixel rectangle stops covering the same ground. The record is therefore split into
groups: date ranges in which the camera stayed still. Each group has its own ROI
rectangles, and images are only paired with images from the same group.

```yaml
groups:
  GRP1:
    start: 2023-10-05
    end: 2024-02-16
    rois:
      stable: {rect: [681, 3314, 654, 78], role: stable}
      ROI1:   {rect: [4515, 3014, 654, 78]}
      ROI2:   {rect: [3969, 3194, 588, 108]}
```

### Group keys

| Key | Default | Meaning |
| --- | --- | --- |
| `start`, `end` | required | Date range of the group. Images outside every group are ignored. Groups should not overlap; if they do, a date goes to the first group listed. |
| `rois` | required | ROIs of this group, keyed by ROI name (see below). |
| `reference_image` | middle image of the group | File name of the image that the quality stage compares every other image against to check the scene is visible. Set it if the automatic choice is a poor image (cloud, snow). |
| `flow_sign_x` | `velocity.flow_sign_x` | `1`, `-1` or `auto`. Per-group override of the flow direction sign (see [velocity](#velocity)). |
| `lake_rect` | | Not used at present. |

### ROI keys

An ROI can be written as a mapping or, for short, as a bare list
(`ROI1: [4515, 3014, 654, 78]`).

| Key | Default | Meaning |
| --- | --- | --- |
| `rect` | required | `[x, y, w, h]`: top-left corner, width and height in full-resolution pixels. |
| `role` | `stable` if the name starts with "stable", else `motion` | `stable` = non-moving terrain used to measure camera motion. `motion` = glacier surface to measure. Each group needs exactly one stable ROI. |
| `distance_m` | from `distances_m` | Camera-to-ROI distance for this group only. |
| `scale_m_per_px` | computed from the distance | Sets the GSD directly and ignores the distance. |
| `label` | the ROI name | Display label (not used in figures at present). |

When choosing ROIs, the stable ROI should be rock or moraine that clearly does not
move, is rarely covered by snow, and is at a similar distance to the glacier ROIs.
Glacier ROIs should be textured ice or debris. The ROI names (`ROI1`, ...) must be the
same in every group so the results join into one time series.

## quality

[quality]

Decides automatically which daily images are good enough to track.

| Key | Default | Meaning |
| --- | --- | --- |
| `static_fraction` | `0.7` | Only the top part of the frame (this fraction of the height) is used for the scene-visibility check. The idea is to use the mountains and valley walls and leave out the foreground. |
| `neighbour_images` | `2` | Each image is also matched against the +/- N images next to it in time. Its visibility score is the best of those matches and the reference-image match. This stops images being rejected just because the season changed since the reference image. |
| `exclude_list` | `exclude_images.txt` | File listing images that must never be used. |
| `include_list` | `include_images.txt` | File listing images that must always be used, even if they fail the checks. |

Both list files are looked for next to the image folder, i.e. in the parent of
`paths.images`. A missing file is fine.

### quality.thresholds

An image is usable (`auto_ok`) only when it passes all of these checks. The metrics
are computed on a quarter-resolution greyscale copy (0-255 scale).

| Key | Default | Flag when failed | Meaning |
| --- | --- | --- | --- |
| `min_visibility_inliers` | `30` | `low_visibility` | Minimum number of SIFT matches (after RANSAC) with the reference or a neighbouring image. Low values mean cloud, fog, snow on the lens, or a large camera shift. |
| `min_sharpness` | `50` | `blurry` | Minimum variance of the Laplacian (a standard focus measure). |
| `min_contrast` | `15` | `low_contrast` | Minimum standard deviation of the grey values. |
| `min_brightness` | `30` | `dark` | Minimum mean grey value. |
| `max_brightness` | `235` | `overexposed` | Maximum mean grey value. |
| `max_clipped_frac` | `0.3` | `clipped` | Maximum fraction of pixels that are almost black (< 5) or almost white (> 250). |

To tune these, look at `output/quality_assessment.csv`, compare the metric columns of
good and bad images, and adjust. For single images, the include/exclude lists are
quicker.

## enhancement

[extract]

Contrast enhancement applied to each ROI crop before tracking. The paper uses MATLAB
`adapthisteq`; here it is OpenCV CLAHE, which is the same algorithm.

| Key | Default | Meaning |
| --- | --- | --- |
| `method` | `clahe` | `clahe` (alias `adapthisteq`), `none` (no enhancement), or `canny` (keeps grey values only on Canny edges). |
| `clip_limit_matlab` | `0.01` | CLAHE clip limit in MATLAB's units (the `adapthisteq` `ClipLimit`). It is converted to OpenCV's units as `1 + c x (n_bins - 1)`, so 0.01 becomes ~3.55. |
| `clip_limit_opencv` | | If set, used directly as OpenCV's `clipLimit`, and `clip_limit_matlab` is ignored. |
| `n_bins` | `256` | Histogram bins, used only in the clip-limit conversion. |
| `tiles` | `[8, 8]` | CLAHE tile grid (rows, columns) per crop. |
| `canny_low`, `canny_high` | `50`, `150` | Canny thresholds, used only with `method: canny`. |

## tracking

[extract, track]

Settings for the feature tracker, which runs once for every image pair and every ROI:

```text
SIFT keypoints in image A (inside the ROI)
  -> KLT optical flow A->B and B->A; keep points that return to where they started
  -> RANSAC affine model; drop outliers
  -> direction filter; drop vectors far from the median direction
  -> final motion vectors
```

| Key | Default | Meaning |
| --- | --- | --- |
| `rois` | all ROIs of the group | Which ROIs to track. Must include the stable ROI, otherwise no velocity can be computed. |
| `pad_px` | `40` | Margin added around each ROI when cropping. Keypoints are only detected inside the ROI, but they can be followed into the margin. Make it larger than the largest expected displacement in pixels over your longest pair. |
| `min_vectors` | `20` | Fallback for `velocity.min_vectors` when that key is not set. |

### tracking.sift

Keypoint detection (OpenCV `SIFT_create`). Only the keypoint locations are used; the
descriptors are ignored.

| Key | Default | Meaning |
| --- | --- | --- |
| `contrast_threshold` | `0.04` | Lower values give more (and weaker) keypoints. |
| `edge_threshold` | `10` | Higher values keep more edge-like keypoints. |
| `n_octave_layers` | `3` | Layers per octave. |
| `sigma` | `1.6` | Gaussian blur of the base octave. |
| `max_features` | `0` | Keep at most this many of the strongest keypoints. `0` means no limit. |

### tracking.klt

Pyramidal Lucas-Kanade optical flow (OpenCV `calcOpticalFlowPyrLK`).

| Key | Default | Meaning |
| --- | --- | --- |
| `win_size` | `31` | Search window side, in pixels. |
| `pyramid_levels` | `3` | Number of pyramid levels including full resolution. More levels can follow larger motions. |
| `max_iterations` | `30` | Iteration limit per level. |
| `epsilon` | `0.01` | Stop iterating when an update is smaller than this. |
| `max_bidirectional_error` | `2.0` | A point is tracked A->B and then back B->A. It is kept only if it lands within this many pixels of where it started. |

### tracking.ransac

Outlier removal with an affine motion model (OpenCV `estimateAffine2D`).

| Key | Default | Meaning |
| --- | --- | --- |
| `reproj_threshold_px` | `2.0` | Maximum distance, in pixels, between a vector and the fitted model for the vector to count as an inlier. |
| `max_trials` | `5000` | Maximum RANSAC iterations. |
| `confidence` | `0.99` | Target confidence. |
| `min_points` | `6` | Minimum number of KLT matches needed to try RANSAC. With fewer, the pair-ROI gets no vectors. |

### tracking.direction_filter

After RANSAC, drops vectors that point far away from the typical flow direction.

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Switch the filter on or off. |
| `threshold_deg` | `30` | Keep vectors within +/- this many degrees of the reference direction. |
| `apply_to_stable` | `false` | Also filter the stable ROI. Normally off, because camera shake has no preferred direction. |
| `reference_direction` | median of the pair | Optional fixed direction per group and ROI, in degrees (0 = +x/right, 90 = +y/down), e.g. `{GRP1: {ROI1: 170}}`. Useful when a pair has so much noise that its median direction is unreliable. |

## pairs

[track]

Every usable image in a group is paired with every later image in the same group
(all n-choose-2 combinations), limited by the time gap (baseline) between them.

| Key | Default | Meaning |
| --- | --- | --- |
| `min_baseline_days` | `0.5` | Shortest allowed gap. `0.5` rules out two images from the same day. A value of `0` is treated as the default. |
| `max_baseline_days` | unlimited | Longest allowed gap. `null` means no limit. The number of pairs grows with the square of the number of images, so a limit (e.g. `60`) greatly reduces tracking time. |

## velocity

[velocity]

| Key | Default | Meaning |
| --- | --- | --- |
| `min_vectors` | `tracking.min_vectors`, then `20` | A glacier ROI result is valid only if at least this many vectors survived tracking. |
| `min_vectors_stable` | `min_vectors` | The stable ROI of the same pair also needs at least this many vectors, otherwise the camera correction is unreliable and the pair is invalid. |
| `flow_sign_x` | `auto` | Sets which image-x direction counts as positive horizontal velocity. `1` = glacier flows toward +x (right in the image), `-1` = toward -x, `auto` = detect it per group from the sign of the median corrected dx. A group's own `flow_sign_x` takes precedence. |
| `flow_sign_min_days` | `7` | Only pairs at least this many days apart are used for `auto` detection. Short pairs are dominated by noise. |

Output units: `feature_velocity_m_yr` and `horizontal_m_yr` in m/yr, `vertical_m_month`
in m/month (a year is 365.25 days, a month is 365.25/12 days).

## aggregation

[aggregate, plots]

Combines per-pair velocities into time windows. A pair counts toward a window when it
is valid, its baseline is >= `min_days`, and both of its images fall inside the
window.

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `monthly` | `monthly`: one window per calendar month in each group. A month split by a group boundary becomes two windows labelled `YYYY-MMa` and `YYYY-MMb`. `custom`: use the `custom` list. |
| `custom` | | Used when `mode: custom`. A list of `{label, start, end}`. |
| `stat` | `median` | How pair values are combined into one window value: `median`, `mean`, or `weighted_mean` (weights = baseline squared, favouring long pairs because their relative error is smaller). |
| `min_days` | `5` | Shortest pair baseline counted in windows and annual periods. |
| `min_pairs` | `3` | A window needs at least this many valid pairs, otherwise it is left out. The shipped config uses 20. |
| `annual_periods` | none | List of `{label, start, end}` periods for `velocity_annual.csv`. |

Example of custom windows:

```yaml
aggregation:
  mode: custom
  custom:
    - {label: winter-2023, start: 2023-12-01, end: 2024-02-15}
    - {label: summer-2024, start: 2024-06-01, end: 2024-08-15}
```

For each window, the uncertainty is the median of the per-pair stable-region
uncertainties, and the spread is the NMAD of the pair values.

## short_term

[aggregate, plots]

Daily velocity series built from short-baseline pairs, with local maxima picked out
(the paper's Fig. 6).

| Key | Default | Meaning |
| --- | --- | --- |
| `quantity` | `horizontal_m_yr` | Which velocity to use: `horizontal_m_yr`, `feature_velocity_m_yr` or `vertical_m_month`. |
| `max_baseline_days` | `1.5` | Only pairs at most this many days apart are used. |
| `smoothing_window_days` | `5` | Length of the centred rolling-median trend. A day is a local maximum when its trend value is the highest within +/- half this window. |
| `periods` | none | List of `{label, start, end}`. Each period can also override `quantity`, `max_baseline_days` and `smoothing_window_days`. |

Each pair is assigned to its midpoint date, rounded to the nearest day. The daily value
is the median of the pairs on that day.

## plots

[plots]

| Key | Default | Meaning |
| --- | --- | --- |
| `rois` | all ROIs in the results | Which ROIs to plot, and in what order. |
| `vector_overlays` | none | List of Fig. 4 specs (below). |
| `vector_fields` | none | List of Fig. 5 specs (below). |

### plots.vector_overlays (Fig. 4)

For each spec and group, the pipeline takes the valid pair with the longest baseline
inside `[start, end]` that is valid for all requested ROIs. It draws that pair's
corrected vectors over the second image of the pair.

| Key | Default | Meaning |
| --- | --- | --- |
| `label` | `start` | Used in the file name. |
| `start`, `end` | required | Time window. |
| `rois` | `plots.rois` | ROIs to draw. |
| `vmax_m_month` | `3.5` | Top of the colour scale (m/month). |
| `arrow_scale` | `5` | Arrows are drawn this many times longer than the actual pixel displacement. |
| `max_vectors` | `400` | Randomly thin to at most this many arrows so the figure stays readable. |

### plots.vector_fields (Fig. 5)

Combines all valid pairs in the window. Each pair's vectors are converted to
px/day and binned on a grid, and each grid cell shows the median. The field stays dense
over long windows, where only a few features survive a single long pair.

| Key | Default | Meaning |
| --- | --- | --- |
| `label` | `start` | Used in the file name. |
| `start`, `end` | required | Time window. |
| `rois` | `plots.rois` | ROIs to draw. |
| `grid_px` | `40` | Grid cell size in pixels. |
| `min_days` | `5` | Shortest pair baseline to include. |
| `min_count` | `10` | A cell needs at least this many vectors to be drawn. |
| `max_pairs` | `2000` | Randomly sample at most this many pairs, to limit run time. |
| `vmax_m_month` | `3.5` | Top of the colour scale (m/month). |
| `arrow_scale` | `3` | Arrow length = one month's displacement x this factor. |

## reference and auxiliary (optional)

These sections are not in the shipped config. Add them to show comparison data in the
figures.

```yaml
reference:
  its_live_m_yr: {ROI1: 25.0, ROI2: 18.0}   # dotted line per ROI in fig3a
  field_observation: {velocity_m_yr: 22.0, roi: ROI2}   # dashed black line in fig3a

auxiliary:
  era5_daily_csv: era5_daily.csv   # needs columns `date` and `net_radiation`; drawn on a second axis in fig6
```

`era5_daily_csv` is looked for as given (relative to the folder you run the command in)
and then next to the image folder.
