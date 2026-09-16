# Feature-tracking core — `utils.tracking`

| | |
| --- | --- |
| **Module** | `glacier_tlc/utils/tracking.py` |
| **Type** | library module (no CLI stage); driven by `track.py` |
| **Also used by** | `tests/test_tracking_synthetic.py`, `tests/test_matlab_parity.py` |

## Overview

Implements the per-pair, per-ROI motion measurement of the paper (Sect. 3.2.2): from
two enhanced crops A and B, produce a set of motion vectors in pixels and their
summary statistics. The module knows nothing about files, dates, groups or metres —
those belong to `track` and `velocity`. Because it is self-contained it can be called
directly on any two arrays, which is how the tests validate it.

```text
enh_a ──SIFT (detect only, masked to ROI)──► p0
p0    ──KLT A→B──► p1 ;  p1 ──KLT B→A──► p0r ;  keep if |p0 − p0r| ≤ 2 px and inside crop
(p0, p1) ──RANSAC affine, 2 px──► inliers
inliers ──direction filter ±30° around the median (motion ROIs only)──► final vectors
```

## `TrackResult`

| Field | Content |
| --- | --- |
| `p0` | (n, 2) float32 — start positions of the final vectors in **full-resolution image coordinates** (crop origin added) |
| `vec` | (n, 2) float32 — displacements `(dx, dy)` in pixels, x right, y down |
| `n_sift`, `n_klt`, `n_ransac`, `n_final` | survivor counts after each step |
| `affine` | the 2 × 3 RANSAC affine matrix (or `None`) — diagnostic only, not used downstream |
| `median_direction_deg` | median direction **before** the direction filter |
| `.magnitude` | property, `hypot(dx, dy)` |
| `.direction_deg` | property, `degrees(atan2(dy, dx))` in `(−180, 180]` |

`_empty(n_sift, n_klt, n_ransac)` builds a result with zero vectors but the counts so
far, so the diagnostics of a failed pair are still recorded.

## `Tracker(cfg_tracking)`

Constructed once per worker process from the `tracking:` section. Parameters:

| Key | Default | Used as |
| --- | --- | --- |
| `sift.max_features` | 0 (unlimited) | `cv2.SIFT_create(nfeatures)` |
| `sift.n_octave_layers` | 3 | `nOctaveLayers` |
| `sift.contrast_threshold` | 0.04 | `contrastThreshold` (OpenCV convention; equivalent to MATLAB 0.0133) |
| `sift.edge_threshold` | 10 | `edgeThreshold` |
| `sift.sigma` | 1.6 | `sigma` |
| `klt.win_size` | 31 | `winSize = (31, 31)` |
| `klt.pyramid_levels` | 3 | `maxLevel = levels − 1` (OpenCV counts from 0) |
| `klt.max_iterations`, `klt.epsilon` | 30, 0.01 | termination criteria (count **or** eps) |
| `klt.max_bidirectional_error` | 2.0 | forward–backward threshold, px |
| `ransac.reproj_threshold_px` | 2.0 | `ransacReprojThreshold` |
| `ransac.max_trials` | 5000 | `maxIters` |
| `ransac.confidence` | 0.99 | `confidence` |
| `ransac.min_points` | 6 | minimum KLT survivors to attempt RANSAC |
| `direction_filter.enabled` | true | |
| `direction_filter.threshold_deg` | 30 | half-width of the accepted window |
| `direction_filter.apply_to_stable` | false | whether the stable ROI is filtered |
| `min_vectors` | 20 | stored, but the validity test is applied in `velocity`, not here |

## `Tracker.track(...)`

```python
Tracker.track(enh_a, enh_b, roi_rect_in_crop, crop_origin,
              is_stable=False, reference_direction=None) -> TrackResult
```

Arguments: the two enhanced padded crops; the ROI rectangle **in crop coordinates**
`(x, y, w, h)`; the crop's origin `(x0, y0)` in full-resolution coordinates; whether
this is the stable ROI; an optional fixed reference direction in degrees.

1. **Mask**: zeros the size of `enh_a`, 255 inside the ROI rectangle. Keypoints are
   detected only inside the ROI proper; the padding exists so they can be *tracked*
   outside it.
2. **SIFT detect**: `self.sift.detect(enh_a, mask)` → keypoint locations only.
   Descriptors are never computed. Fewer than 3 keypoints → empty result.
3. **KLT forward**: `cv2.calcOpticalFlowPyrLK(enh_a, enh_b, p0)` → `p1`, status `st1`.
4. **KLT backward**: `calcOpticalFlowPyrLK(enh_b, enh_a, p1)` → `p0r`, status `st2`.
5. **Survivor mask** `ok`: `st1 == 1` and `st2 == 1` and `‖p0 − p0r‖ ≤ max_bidir_err`
   and `p1` inside `[0, W) × [0, H)` of crop B. `n_klt = count(ok)`. Fewer than
   `ransac.min_points` → empty result with `n_sift`, `n_klt`.
6. **RANSAC affine**: `cv2.estimateAffine2D(a, b, RANSAC, reproj_threshold, maxIters,
   confidence, refineIters=10)` on the survivors. A `None` result or fewer than 3
   inliers → empty result. Keep the inliers; `n_ransac = count`; `vec = b − a`. The
   affine matrix `M` is stored, but the **individual inlier vectors**, not the model,
   are what is reported.
7. **Direction filter** (if `enabled` and (`apply_to_stable` or not `is_stable`)):
   `direction = degrees(atan2(dy, dx))`; the reference is `reference_direction` if
   given, otherwise `median(direction)` (a plain, non-circular median); keep vectors
   with `circ_diff_deg(direction, ref) ≤ threshold_deg`.
8. Return `TrackResult(a + crop_origin, vec, n_sift, n_klt, n_ransac, n_final, M,
   med_dir)`.

Every threshold has the value given by the paper or the MATLAB prototype, with one
deliberate change: the RANSAC threshold is 2 px instead of the prototype's 2000 px,
which accepted every match.

## `vector_stats(res, prefix="") -> dict`

Turns a `TrackResult` into the flat row written to `pairs_raw.csv`. Always includes
`n_sift`, `n_klt`, `n_ransac`, `n_vectors`; the 17 statistics below are NaN when
`n_vectors == 0`.

| Group | Columns | Definition |
| --- | --- | --- |
| magnitude | `mag_median`, `mag_mean`, `mag_mean95`, `mag_std`, `mag_nmad` | median, mean, `mean_below_p95`, sample std (ddof = 1; 0 if n = 1), `nmad` |
| direction | `dir_median` | plain median of the angles |
| | `dir_mean` | **circular** mean: `atan2(mean sin, mean cos)` |
| | `dir_std` | sample std of `circ_diff_deg(direction, dir_median)` |
| | `dir_nmad` | `1.4826 · median(circ_diff_deg(direction, dir_median))` |
| x | `dx_median`, `dx_mean`, `dx_std`, `dx_nmad` | on `vec[:, 0]` |
| y | `dy_median`, `dy_mean`, `dy_std`, `dy_nmad` | on `vec[:, 1]` |

`prefix` is unused by the pipeline (always `""`); it exists so a caller could merge
motion and stable rows side by side as the MATLAB CSV did.

## Behaviour to be aware of

- **Determinism**: SIFT and KLT are deterministic; RANSAC uses OpenCV's internal RNG,
  so inlier sets can differ marginally between runs. `track` sets
  `cv2.setNumThreads(1)` per worker, which also keeps results stable.
- **The direction reference is the median of the pair's own vectors** unless
  `direction_filter.reference_direction.<GRP>.<ROI>` is configured. On near-zero
  motion this median is defined by noise.
- **Coordinates**: everything inside `track()` is in crop pixels; only `p0` is
  shifted to image coordinates at the end. `vec` is a difference and needs no shift.
- **`min_vectors` is not enforced here.** A pair-ROI with 5 vectors still gets a row
  in `pairs_raw.csv`; `velocity` marks it invalid.

## See also

- [track.md](track.md) — how crops, ROIs and pairs are fed to `track()`.
- [utils.md](utils.md) — `nmad`, `circ_diff_deg`, `mean_below_p95`.
- [tests.md](tests.md) — synthetic and parity checks that exercise this module
  directly.
