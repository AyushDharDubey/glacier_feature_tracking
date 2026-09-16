# Tests

| | |
| --- | --- |
| **Files** | `tests/conftest.py`, `tests/test_tracking_synthetic.py`, `tests/test_matlab_parity.py` |
| **Run** | `pytest tests/` (or a file directly: `PYTHONPATH=. python tests/<file>.py`) |

## Overview

Two independent checks of the tracking core (`utils/tracking.py` and
`utils/enhance.py`): synthetic images with a known answer, and numerical parity with
the authors' own MATLAB output. Neither test touches the stage modules, the config
file or the caches.

`conftest.py` only inserts the repository root into `sys.path` so that `glacier_tlc`
imports without installation.

## `test_tracking_synthetic.py`

Uses a shared tracker configuration equal to the pipeline defaults (31 px KLT window,
3 levels, 2 px bidirectional error, 2 px RANSAC threshold, ±30° direction filter)
and CLAHE enhancement. Helper functions:

- `_texture(seed, shape)` — Gaussian-blurred uniform noise, normalised to uint8: a
  featureful, non-repeating image;
- `_shift(img, dx, dy)` — `cv2.warpAffine` translation with cubic interpolation and
  reflected borders.

| Test | Set-up | Asserts |
| --- | --- | --- |
| `test_recovers_subpixel_shift` | 200 × 700 texture shifted by (−2.3, +0.7) px; ROI (40, 40, 620, 120) | > 100 final vectors; median dx, dy within 0.1 px of the truth; magnitude NMAD < 0.2 px |
| `test_direction_filter_removes_outliers` | shift (+3, 0) | every surviving direction has an absolute angle ≤ 30° |
| `test_stable_correction` | two textures: "stable" shifted by camera shake (+0.8, −0.6); "glacier" shifted by shake + ice motion (−1.5, +0.4); stable tracked with `is_stable=True` | `median(glacier vectors) − median(stable vectors)` equals the ice motion within 0.1 px; stable NMAD < 0.2 px |

Together these verify the SIFT → KLT → RANSAC → direction chain, the direction
window, and the per-vector stable correction that `velocity` applies.

## `test_matlab_parity.py`

Reproduces the six pairs in `motion_statistics_ROI4_Grp3_adapthisteq.csv` (the
authors' MATLAB output for ROI4 and the stable region, GRP3 rectangles, images of
3–6 November 2023) and compares every median statistic.

The set-up differs from the pipeline deliberately, to match the prototype:

```python
MATLAB_CFG = {"ransac": {"reproj_threshold_px": 2000.0, ...},    # prototype's MaxDistance → no rejection
              "direction_filter": {"apply_to_stable": True, ...}} # prototype filtered the stable region too
RECTS = {"motion": (3755, 3195, 338, 172), "stable": (1347, 3290, 416, 178)}
```

Steps of `compare()`:

1. Find the four images by EXIF date in `input/` (`read_exif_datetime`); skip the
   test if the folder or the CSV is missing, or fewer than four images are found.
2. Decode each in grey at full resolution; for every pair `(da, db)` and region:
   `Tracker(MATLAB_CFG).track(enh(crop(A)), enh(crop(B)), (0, 0, w, h), (x, y),
   is_stable=…)` — **unpadded** crops, as the prototype used.
3. Collect Python versus MATLAB `n_vectors`, `mag_median`, `mag_mean`, `dx_median`,
   `dy_median`, `dir_median` per region-pair and their differences.

`test_matlab_parity` asserts, over all twelve region-pairs: every displacement
difference ≤ 0.02 px, direction difference ≤ 1.5°, vector-count difference < 12 %.
Running the file directly prints the full comparison table and the worst
differences.

## Coverage

The stage modules (`inventory` … `report`), the configuration loader, pair
formation, the cache/resume logic and the aggregation rules have no automated tests;
they are validated by end-to-end agreement with the published results.

## See also

- [tracking.md](tracking.md), [enhance.md](enhance.md) — the code under test.
