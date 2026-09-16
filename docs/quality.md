# Stage 2 — `quality`

| | |
| --- | --- |
| **Module** | `glacier_tlc/quality.py` |
| **Command** | `python -m glacier_tlc quality [-j N]` |
| **Reads** | `output/inventory.csv`, the images, optional `exclude_images.txt` / `include_images.txt` |
| **Writes** | `output/quality.csv`, `output/images_used.csv` |

## Overview

Decides which daily photographs are usable. Two families of tests are computed on a
quarter-resolution copy of every in-group daily pick: global exposure and sharpness
metrics, and a scene-visibility test that matches static terrain against a reference
image and against neighbouring days. Manual lists override the automatic verdict.

A by-product — the whole-scene shift of each image relative to the group reference —
is the diagnostic used to place the camera-group boundaries in `config.yaml`.

## Processing

### `run(cfg, workers)`

1. Load `inventory.csv`; keep rows with `daily_pick` and a non-empty `group`.
2. `workers` defaults to `CPUs − 1`.
3. **Per group**:
   1. Choose the **reference image** (`pick_reference`): the group's
      `reference_image` if configured, otherwise the *middle* image (by date order)
      of the group's daily picks.
   2. Load the reference at quarter resolution and detect SIFT features on its static
      mask (`_ref_features`).
   3. Serialise the reference keypoints as `(x, y)` tuples (OpenCV `KeyPoint` objects
      are not picklable) and dispatch every image of the group to a
      `ProcessPoolExecutor` running `_worker_ser` (chunksize 4).
   4. Back in the parent, run the **neighbour check**: for image *i*, compute the
      RANSAC inlier count against each of images `i−n … i+n` (`neighbour_images`,
      default 2; excluding *i*) and take the maximum → `vis_inliers_neighbour`. Then
      `vis_inliers_ref = vis_inliers` (against the reference) and
      `vis_inliers = max(vis_inliers_ref, vis_inliers_neighbour)`.
   5. Drop the serialised features and attach `reference_image`.
4. Concatenate groups and left-join onto the inventory rows.
5. **Automatic decision** `auto_ok` — all of:
   `vis_inliers ≥ min_visibility_inliers`, `sharpness ≥ min_sharpness`,
   `contrast ≥ min_contrast`, `min_brightness ≤ brightness ≤ max_brightness`,
   `clipped_frac ≤ max_clipped_frac`. NaN → `False`.
6. **Manual lists**: read `exclude_list` and `include_list` (paths relative to the
   *parent* of the image folder, i.e. the repository root by default); one file name
   per line, blank lines and lines starting with `#` ignored. `manual` = `exclude`,
   `include` or `""`.
7. **Verdict**: `usable = (auto_ok AND NOT excluded) OR included`. An include entry
   therefore beats an exclude entry for the same file.
8. **Flags**: a `;`-joined string of every failed test — `low_visibility`, `blurry`,
   `low_contrast`, `dark`, `overexposed`, `clipped` — plus `manual_exclude` /
   `manual_include`.
9. Write `quality.csv` (all rows) and `images_used.csv` (rows with `usable`).

### `_worker(args)` — per image, in a worker process

1. `_load_small`: `cv2.imread` with `IMREAD_REDUCED_COLOR_4` — the JPEG decoder
   produces the 1500 × 1000 image directly; there is no full-resolution decode.
2. `_global_metrics` on the small image:

   | Metric | Definition |
   | --- | --- |
   | `brightness` | mean of the grey image |
   | `contrast` | standard deviation of the grey image |
   | `sharpness` | variance of the Laplacian (`cv2.Laplacian`, CV_64F) |
   | `saturation` | mean of the HSV S channel |
   | `clipped_frac` | fraction of grey pixels `< 5` or `> 250` |

3. `_visibility` against the reference:
   - SIFT (`nfeatures=4000`) on the grey image, masked to the top `static_fraction`
     (default 0.7) of the frame — `_static_mask` sets rows `0 … 0.7·h` to 255;
   - brute-force L2 kNN match (k = 2) against the reference descriptors, Lowe ratio
     test at 0.75;
   - `cv2.estimateAffinePartial2D` (similarity model) with RANSAC, 3 px threshold,
     5000 iterations, 0.99 confidence;
   - outputs: `vis_inliers` (inlier count), `shift_dx_px` / `shift_dy_px` (median
     inlier displacement image → reference, multiplied by 4 to full-resolution
     pixels), `shift_scale` (the similarity scale, `hypot(M00, M10)`);
   - fewer than 8 keypoints or 8 good matches → 0 inliers, NaN shifts.
4. `_image_features`: SIFT again on the same mask, returned in serialisable form for
   the neighbour check.

### `_match_count(fa, fb)`

The same match + RANSAC-similarity procedure as `_visibility`, between two serialised
feature sets; returns the inlier count only. Used for the neighbour comparison.

## Outputs

### `output/quality.csv` — one row per in-group daily pick

All `inventory.csv` columns, plus:

| Column | Meaning |
| --- | --- |
| `brightness`, `contrast`, `sharpness`, `saturation`, `clipped_frac` | global metrics (quarter resolution) |
| `vis_inliers` | `max(vis_inliers_ref, vis_inliers_neighbour)` — the value tested |
| `vis_inliers_ref` | inliers against the group reference |
| `vis_inliers_neighbour` | best inlier count against the ±N neighbouring days |
| `shift_dx_px`, `shift_dy_px` | whole-scene translation to the reference, full-resolution px |
| `shift_scale` | similarity scale factor to the reference (≈ 1) |
| `reference_image` | file used as the group reference |
| `auto_ok` | automatic verdict |
| `manual` | `exclude` / `include` / `""` |
| `usable` | final verdict |
| `flags` | failed tests, `;`-separated |

### `output/images_used.csv`

The subset with `usable == True`, same columns. This is the image list consumed by
`extract`, `track` (via the crops) and `report`.

## Configuration

```yaml
quality:
  static_fraction: 0.7        # top fraction of the frame used for visibility
  neighbour_images: 2         # ± days for the neighbour check
  thresholds:
    min_visibility_inliers: 30
    min_sharpness: 50
    min_contrast: 15
    min_brightness: 30
    max_brightness: 235
    max_clipped_frac: 0.3
  exclude_list: exclude_images.txt
  include_list: include_images.txt
groups:
  GRPx:
    reference_image: <file>   # optional; default = middle image of the group
```

## Notes and edge cases

- All metric thresholds are tuned to the **quarter-resolution** image; the
  `sharpness` value in particular would be very different at full resolution.
- The neighbour check operates on the *in-group daily-pick* order, so "±2 neighbours"
  are the nearest two rows, which may be more than two calendar days apart across a
  gap.
- The reference choice affects `shift_dx_px` / `shift_dy_px` (they are relative to
  it) but has little effect on `usable`, because the neighbour match rescues
  seasonally different images.
- The stage always recomputes; there is no cache. About 2.5 min at 10 workers for
  420 images.
- `hour_offset`, `in_hour_window` and the other inventory columns are carried through
  unchanged.

## See also

- [inventory.md](inventory.md) — where the rows come from.
- [extract.md](extract.md) — consumes `images_used.csv`.
- [plots.md](plots.md) — `qa_image_quality.png` visualises these columns.
