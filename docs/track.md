# Stage 4 — `track`

| | |
| --- | --- |
| **Module** | `glacier_tlc/track.py` (algorithm in [`utils/tracking.py`](tracking.md)) |
| **Command** | `python -m glacier_tlc track [-j N] [--limit N]` |
| **Reads** | `output/images_used.csv`, `.cache/crops/` |
| **Writes** | `output/pairs_raw.csv`, `.cache/vectors/<group>/<A>__<B>.npz` |

## Overview

Forms the image pairs, runs the tracker on every pair × ROI in parallel, caches the
resulting vectors per pair, and writes the per-pair statistics table in pixel units.
It is the only expensive stage (about 66 min at 4 workers, or 16 min at 16 workers,
for the 28,546 uncapped pairs of the Drang Drung dataset) and the only one that
resumes from its own cache.

## Pair formation — `build_pairs(cfg, used) -> DataFrame`

1. `min_b = pairs.min_baseline_days` (default 0.5); `max_b = pairs.max_baseline_days`,
   where `null` / `none` / `unlimited` / absent → `+∞`.
2. For each group, take its usable images sorted by datetime and form every
   `itertools.combinations(…, 2)` — nC2, A before B.
3. Keep the pair if `min_b ≤ (t_B − t_A) in days ≤ max_b`.
4. Return one row per pair: `group, file_a, file_b, datetime_a, datetime_b, days`.

Pairs never cross a group boundary. `days` is the exact fractional separation
(seconds / 86 400), not rounded. On the Drang Drung dataset the uncapped count is
28,546 pairs; a 20-day cap gives 7,147.

## Processing

### `run(cfg, workers, limit)`

1. Load `images_used.csv`; `build_pairs`; apply `--limit` (`pairs.head(limit)`).
2. Log the pair count per group; create `.cache/vectors/`.
3. For each pair build a task tuple:
   - `rois = {name: (rect, role)}` for the group's ROIs, restricted to
     `tracking.rois` if that list is set (shipped config: `[stable, ROI1, ROI2, ROI3]`);
   - `meta = {vec_dir, reference_direction:
     tracking.direction_filter.reference_direction[group]}` (empty if not configured);
   - crop paths of A and B via `extract.crop_path`.
4. `ProcessPoolExecutor(workers, initializer=_init, initargs=(cfg.tracking,))` — each
   worker builds one `Tracker` and sets `cv2.setNumThreads(1)`.
5. `ex.map(_track_pair, tasks, chunksize=8)`, zipped with the pair rows in order. For
   each result:
   - `None` → log `pair A-B: <status>` as a warning and skip;
   - otherwise one record per ROI: the pair columns + `roi` + the `vector_stats` dict;
   - every 250 pairs, log progress and how many pairs came from the cache.
6. Write `pairs_raw.csv`.

### `_track_pair(args)` — per pair, in a worker

1. `np.load` both crop files; failure → `(None, "load error …")`.
2. Target path `.cache/vectors/<group>/<stemA>__<stemB>.npz`.
3. **Resume check**: if the file exists and contains `<roi>_vec` for **every requested
   ROI**, rebuild a `TrackResult` per ROI from `_p0`, `_vec` and `_diag` (older files
   without `_diag` get counts `−1`), compute `vector_stats`, and return
   `(rows, "cached")`. Nothing is tracked. If the file is missing any requested ROI,
   or fails to load, it is recomputed **for all ROIs** and overwritten.
4. For each ROI:
   - `prect = A["<roi>_rect"]`; `rect_in_crop = (rect.x − x0, rect.y − y0, w, h)`;
   - `res = TRACKER.track(A["<roi>_enh"], B["<roi>_enh"], rect_in_crop, (x0, y0),
     is_stable=(role == "stable"), reference_direction=ref_dirs.get(roi))`;
   - `rows[roi] = vector_stats(res)`; collect `p0`, `vec` (float32) and
     `diag = [n_sift, n_klt, n_ransac]` (int32).
5. `np.savez_compressed` the vector file; return `(rows, "ok")`.

## Outputs

### `output/pairs_raw.csv` — one row per pair × tracked ROI

| Column | Meaning |
| --- | --- |
| `group`, `file_a`, `file_b`, `datetime_a`, `datetime_b`, `days` | the pair |
| `roi` | ROI name (`stable`, `ROI1`, …) |
| `n_sift`, `n_klt`, `n_ransac`, `n_vectors` | survivors after each step (`n_vectors` = final) |
| `mag_median`, `mag_mean`, `mag_mean95`, `mag_std`, `mag_nmad` | magnitude statistics, px |
| `dir_median`, `dir_mean`, `dir_std`, `dir_nmad` | direction statistics, degrees (see [tracking.md](tracking.md)) |
| `dx_median`, `dx_mean`, `dx_std`, `dx_nmad` | x-component statistics, px |
| `dy_median`, `dy_mean`, `dy_std`, `dy_nmad` | y-component statistics, px |

All values are **raw** (uncorrected for camera motion) and in pixels. The file is
rewritten in full on every run; rows for pairs skipped by `--limit` or the baseline
cap are not present.

### `.cache/vectors/<group>/<A>__<B>.npz` — one file per pair

| Key | Content |
| --- | --- |
| `<roi>_p0` | (n, 2) float32 — start positions, full-resolution image coordinates |
| `<roi>_vec` | (n, 2) float32 — displacements `(dx, dy)`, px |
| `<roi>_diag` | (3,) int32 — `[n_sift, n_klt, n_ransac]` |

About 1.6 GB for the uncapped run. Read by `velocity` (to apply the stable correction
per vector) and `plots` (Fig. 4 overlays).

## Configuration

```yaml
pairs:
  min_baseline_days: 0.5
  max_baseline_days: null        # or a number of days
tracking:
  rois: [stable, ROI1, ROI2, ROI3]   # subset to track; omit → all ROIs of the group
  direction_filter:
    reference_direction: {GRP1: {ROI1: -160}}   # optional fixed azimuths
  # sift / klt / ransac / direction_filter → see tracking.md
```

## Resumability and cache semantics

- A pair is reused when its vector file holds every ROI in `tracking.rois`. So
  narrowing the ROI list, or widening or removing the baseline cap, costs only the
  new work; **adding** an ROI recomputes every pair (the check fails for all of them).
- The cache stores **vectors, not parameters**. After changing anything under
  `tracking.sift/klt/ransac/direction_filter`, `enhancement`, `pad_px` or an ROI
  rectangle, delete `.cache/vectors/` (and `.cache/crops/` for the latter three).
- The `pairs_raw.csv` statistics of cached pairs are recomputed from the stored
  vectors on every run, so a change in `vector_stats` itself takes effect without
  re-tracking.
- The stable ROI must be among the tracked ROIs, otherwise `velocity` finds no
  correction data and skips every pair.

## Failure modes

| Message | Cause |
| --- | --- |
| `pair A-B: load error …` | a crop file is missing (the image failed in `extract`) |
| `KeyError: 'ROIx_rect'` in a worker | the crop cache predates an added ROI — delete `.cache/crops/` |
| `track: 0 pairs` | no usable images, or `max_baseline_days < min_baseline_days` |
| `FileNotFoundError: images_used.csv` | `quality` has not run |

## See also

- [tracking.md](tracking.md) — the algorithm and the statistics definitions.
- [extract.md](extract.md) — the crop cache this stage consumes.
- [velocity.md](velocity.md) — the next consumer of `pairs_raw.csv` and the vectors.
