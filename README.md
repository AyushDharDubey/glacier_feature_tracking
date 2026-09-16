# Drang Drung Glacier: terrestrial time-lapse velocity pipeline (`glacier_tlc`)

Python implementation of the glacier-velocity methodology of

> Singh, P., Vijay, S., Azam, M.F. (2026). *High-Frequency observations of glacier ice
> velocities at Drang Drung Glacier, Western Himalaya, using a terrestrial time-lapse
> imaging system.* Science of Remote Sensing 13, 100431.
> https://doi.org/10.1016/j.srs.2026.100431


## Quick start

Create a virtual environment, install the dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

put the daily JPEGs (with EXIF capture time) in ./input, edit config.yaml if needed

```bash
python -m glacier_tlc all -j 10          # every stage in order
python -m glacier_tlc track --limit 50   # or run single stages
```

All settings live in [config.yaml](config.yaml). Outputs go to `output/`, caches to `.cache/`
(both git-ignored, `.cache/` can be deleted at any time).

## Documentation

* **[docs/PIPELINE.md](docs/PIPELINE.md)** — how every stage works, the conventions and the
  uncertainty model, a register of all 17 points where the implementation departs from the
  paper or fills a gap it leaves, the validation evidence, and an output-file reference.
* **[docs/MATLAB_COMPARISON.md](docs/MATLAB_COMPARISON.md)** — what is derived from the
  authors' MATLAB prototype, what is changed and why, what is added, the 13 defects found
  in the prototype with the evidence for each, and a numerical parity table against the
  authors' own output.
* **[docs/REMOTE_RUN.md](docs/REMOTE_RUN.md)** — sizing and running the full uncapped
  `track` stage (28,546 pairs) on a server: time and disk estimates by worker count, and
  how to carry over a partial local cache so only the missing pairs get computed.

## Pipeline

| stage | what it does (paper section) | writes |
|---|---|---|
| `inventory` | EXIF capture times, one image per day nearest 13:00, camera-position group per image (3.1, 3.2) | `output/inventory.csv` |
| `quality` | brightness / contrast / sharpness metrics and a scene-visibility check (SIFT + RANSAC against the group reference and neighbouring days); manual `exclude_images.txt` / `include_images.txt` override (3.1.2) | `output/quality.csv`, `output/images_used.csv` |
| `extract` | crop each ROI (+40 px margin) of each usable image once, apply CLAHE (= MATLAB `adapthisteq`), cache | `.cache/crops/` |
| `track` | all image pairs inside a group (nC2, unbounded by default, matching the paper and the MATLAB script; a baseline cap is optional and cached pairs are reused on rerun); per ROI: SIFT keypoints → pyramidal KLT with forward–backward check → RANSAC affine → ±30° direction filter → vector statistics (3.2.2) | `output/pairs_raw.csv`, `.cache/vectors/` |
| `velocity` | subtract median stable-region displacement, NMAD uncertainty, photogrammetric scaling to metres, horizontal / vertical components (3.3) | `output/pairs_velocity.csv` |
| `aggregate` | monthly (or custom) windows, annual / seasonal / interannual summaries, short-term daily series + local maxima (4.1, 5.2) | `output/velocity_*.csv` |
| `compare` | TLC vs in-situ GNSS stake and ITS_LIVE (3.4, 5.4) | `output/comparison_field_itslive.csv` |
| `lake` | optional lake colour / ice indices from a lake window (4.2) | `output/lake_index.csv` |
| `plots` | paper-style Figs. 3–7 and QA figures | `output/figures/` |
| `report` | markdown summary | `output/report.md` |

### Method details and conventions

* **Groups.** The camera moved at every retrieval and after each snow burial, so the record is
  split into GRP1 (5 Oct 2023 – 16 Feb 2024), GRP2 (16 May – 18 Aug 2024) and GRP3
  (19 Aug 2024 – 24 Feb 2025). The boundaries were measured from the whole-scene shift of
  every image (`shift_dx_px`, `shift_dy_px` in `quality.csv`); the ROI rectangles are the
  authors' MATLAB coordinates for the matching camera position.
* **Enhancement.** OpenCV CLAHE with the MATLAB `adapthisteq` defaults; the MATLAB clip limit
  0.01 maps to OpenCV `clipLimit = 1 + 0.01·255 ≈ 3.55` (derivation in `glacier_tlc/enhance.py`).
* **Tracking parameters** (config `tracking:`): SIFT defaults (OpenCV 0.04 contrast threshold ≡
  MATLAB 0.0133), KLT 31×31 window, 3 pyramid levels, 30 iterations, bidirectional error ≤ 2 px,
  RANSAC affine with 2 px reprojection threshold, 5000 trials, 99 % confidence, direction window
  ±30° around the pair's median direction (motion ROIs only).
* **Correction and uncertainty.** Per pair, `(dx, dy)` of every glacier vector minus the median
  stable-region `(dx, dy)`; the pair velocity is the median corrected magnitude; the uncertainty is
  the stable-region NMAD (of magnitude, dx, dy) scaled like the velocity.
* **Scaling.** `GSD = distance × (sensor width / image width) / focal length`; Canon EOS 2000D,
  24 mm: 0.139 m/px at 900 m (ROI1, stable), 0.108 m/px at 700 m (ROI2), 0.070 m/px at 450 m (ROI3).
* **Signs.** `horizontal_m_yr` is positive along the dominant flow direction (image −x here,
  auto-detected per group); `vertical_m_month` is positive upward (image y points down), so
  negative values mean surface lowering, as in the paper's Fig. 6.
* **Compute budget.** The default `config.yaml` tracks the three paper ROIs plus the stable
  region (`tracking.rois`), with no baseline cap — the full nC2 combination, 28,546 pairs
  for this dataset (~66 min at 4 workers, ~16 min at 16). `pairs.max_baseline_days` can
  cap the baseline for a lighter/faster run, at the cost of noisier windows (the longest
  pairs are the quietest — see `docs/PIPELINE.md` Section 9). Finished pairs are cached in
  `.cache/vectors/`, so a capped smoke-test run followed by an uncapped production run only
  computes the difference. See `docs/REMOTE_RUN.md` for sizing a run on a larger machine.
* **Windows.** A pair contributes to a window when both images lie inside it and the baseline is
  ≥ `aggregation.min_days` (5 d); the window value is the median of the per-pair velocities, the
  uncertainty the median per-pair uncertainty, and `spread_*` the NMAD across pairs.
* **Short-term series.** Short-baseline pairs (≤ 3 d, assigned to their mid date) give the daily
  horizontal velocity; a 5-day centred rolling median is the moving-window trend; local maxima are
  the maxima of that trend within ±2 days (series edges excluded), as in the paper's Fig. 7.

## Relation to the MATLAB prototype

Reproduced: CLAHE crop enhancement, SIFT detection, KLT with bidirectional error 2 px,
direction filter of 30°, the same per-pair statistics (mean, mean-below-95th-percentile,
median, std, NMAD of magnitude, direction, x and y). Checked during development against a
reference sample the authors provided (ROI4, camera group 3, 3–6 Nov 2023): the Python
tracker matched the MATLAB medians to ≤ 0.005 px and ≤ 0.4° — details and the full table
in [docs/MATLAB_COMPARISON.md](docs/MATLAB_COMPARISON.md), Appendix 1.

Changed, because the paper supersedes the script:

| MATLAB script | paper / this pipeline |
|---|---|
| RANSAC `MaxDistance = 2000` px → every point is an inlier, no outlier rejection | real reprojection threshold (2 px) |
| no stable-region correction, no uncertainty, no metric scaling in the script | median stable-region subtraction, NMAD uncertainty, photogrammetric scaling |
| every image paired with every other (`nchoosek`), unbounded | nC2 inside a camera group, unbounded by default (matches the prototype); a baseline cap is available and optional |
| missing EXIF time replaced by *today's* date | image dropped with a warning |
| direction filter also applied to the stable region | stable region keeps all RANSAC inliers (camera shake has no preferred direction) |
| final CSV written only after a bug fix; results per pair only | per-pair, per-window, annual, seasonal, short-term tables and figures |

## Repository layout

```
glacier_tlc/        pipeline package (one module per stage; tracking.py is the core)
config.yaml         all parameters, ROIs, groups, distances, references
docs/                pipeline reference, MATLAB comparison, remote-run guide
input/               daily JPEGs (not tracked in git)
output/, .cache/       results and caches (not tracked in git)
```
