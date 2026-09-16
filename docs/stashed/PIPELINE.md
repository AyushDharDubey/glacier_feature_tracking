# `glacier_tlc` — pipeline reference

How every stage of the Drang Drung terrestrial time-lapse velocity pipeline works,
what it produces, and every point at which it departs from the published method.

Reference method:

> Singh, P., Vijay, S., Azam, M.F. (2026). *High-Frequency observations of glacier ice
> velocities at Drang Drung Glacier, Western Himalaya, using a terrestrial time-lapse
> imaging system.* Science of Remote Sensing 13, 100431.
> https://doi.org/10.1016/j.srs.2026.100431

Section numbers in square brackets, such as [3.2.2], refer to that paper.
A companion document, [MATLAB_COMPARISON.md](MATLAB_COMPARISON.md), covers the
relationship to the authors' MATLAB prototype.

---

## Contents

1. [What the pipeline computes](#1-what-the-pipeline-computes)
2. [Data flow](#2-data-flow)
3. [The configuration model](#3-the-configuration-model)
4. [Stage 1 — `inventory`](#4-stage-1--inventory)
5. [Stage 2 — `quality`](#5-stage-2--quality)
6. [Stage 3 — `extract`](#6-stage-3--extract)
7. [Stage 4 — `track` (the core)](#7-stage-4--track-the-core)
8. [Stage 5 — `velocity`](#8-stage-5--velocity)
9. [Stage 6 — `aggregate`](#9-stage-6--aggregate)
10. [Stage 7 — `compare`](#10-stage-7--compare)
11. [Stage 8 — `lake`](#11-stage-8--lake)
12. [Stage 9 — `plots`, Stage 10 — `report`](#12-stage-9--plots-stage-10--report)
13. [Conventions: axes, signs, units](#13-conventions-axes-signs-units)
14. [The uncertainty model](#14-the-uncertainty-model)
15. [Deviation register](#15-deviation-register)
16. [Validation evidence](#16-validation-evidence)
17. [Known limitations](#17-known-limitations)
18. [Output file reference](#18-output-file-reference)
19. [Compute cost and how to reduce it](#19-compute-cost-and-how-to-reduce-it)

---

## 1. What the pipeline computes

From a folder of daily time-lapse photographs of the glacier, it produces, for each
region of interest and each time window:

* **feature velocity** — the median magnitude of the corrected motion vectors, in m yr⁻¹;
* **horizontal velocity** — the along-flow component, in m yr⁻¹;
* **vertical motion** — the surface-normal component, in m month⁻¹, negative for lowering;
* **an uncertainty** for each of the three, from the stable reference region;

plus annual, seasonal and interannual summaries, a short-term daily series with local
maxima, a comparison against in-situ GNSS and ITS_LIVE, an optional proglacial-lake
colour index, the paper's figure set, and a written report.

Every number is traceable: a window value points to the pairs that produced it
(`pairs_velocity.csv`), each pair points to its motion vectors (`.cache/vectors/`), and
each vector to the image pair and ROI it came from.

---

## 2. Data flow

```
input/*.JPG  (one photograph per day, ~13:00 local, EXIF capture time required)
     |
  [inventory] ── inventory.csv          EXIF times, daily pick, camera group
     |
  [quality]   ── quality.csv            metrics + visibility; images_used.csv
     |
  [extract]   ── .cache/crops/<group>/*.npz     ROI crops, enhanced, cached
     |
  [track]     ── pairs_raw.csv          per pair x ROI vector statistics (pixels)
     |          .cache/vectors/<group>/*.npz    the motion vectors themselves
     |
  [velocity]  ── pairs_velocity.csv     corrected, scaled, in metres per unit time
     |
  [aggregate] ── velocity_windows.csv   monthly (or custom) windows
     |          velocity_annual.csv, velocity_seasonal.csv,
     |          velocity_seasonal_change.csv, velocity_interannual.csv,
     |          velocity_daily.csv, velocity_local_maxima.csv
     |
  [compare]   ── comparison_field_itslive.csv
  [lake]      ── lake_index.csv
  [plots]     ── output/figures/*.png
  [report]    ── output/report.md
```

Run everything with `python -m glacier_tlc all -j 10`, or any single stage by name.
Stages read the outputs of earlier stages from disk, so each can be re-run on its own
after a configuration change without repeating the expensive steps.

---

## 3. The configuration model

Everything that can be varied lives in `config.yaml`; no analysis constant is hard-coded
in the source. The file is parsed into typed objects by `glacier_tlc/config.py`, which
validates the structure eagerly (a group must contain exactly one ROI with
`role: stable`; every ROI must have either a `distance_m` or an explicit
`scale_m_per_px`; every rectangle must have four elements).

The four blocks that matter most:

**`camera`** — physical camera parameters, used only for the pixel-to-metre conversion.

**`groups`** — the camera-position periods. The TLC was knocked out of position at each
data retrieval and each snow burial, so the paper splits the record into three groups
that are processed independently [3.2]. Each group carries its own ROI rectangles in
full-resolution pixel coordinates, because the same patch of ice sits at different image
coordinates after the camera moves.

**`distances_m`** — camera-to-ROI distances, the other half of the scaling. Defaults come
from the paper [3.2.1]: ROI1 ≈ 900 m, ROI2 ≈ 700 m, ROI3 ≈ 450 m, stable ≈ 900 m.

**`tracking`** — SIFT, KLT, RANSAC and direction-filter parameters (Section 7 below).

A group is selected for a photograph by date, so adding a fourth camera period means
adding a `groups:` entry with its date range and rectangles, nothing else.

---

## 4. Stage 1 — `inventory`

**Module** `glacier_tlc/inventory.py` · **reads** `input/*.JPG` · **writes** `output/inventory.csv`

### What it does

1. **Reads the EXIF capture time** of every JPEG, preferring `DateTimeOriginal`
   (tag 36867) and falling back to `DateTime` (tag 306). An image whose time cannot be
   read is dropped with a warning, and the dropped file names are logged.
2. **Selects one photograph per day.** The paper uses "daily images captured around
   1300 h local time to ensure consistent lighting conditions" [3.2]. The stage keeps,
   for each calendar day, the photograph closest to `inventory.target_hour` (13:00),
   provided it falls within `± hour_window` (2 h) of it. Days with no photograph in that
   window contribute nothing.
3. **Assigns a camera group** by comparing the date against each group's range.
4. Records `day_index`, days since the first photograph, for convenience.

### Why the hour matters

Illumination geometry changes the apparent position of shadow-defined features. Fixing
the time of day keeps the sun azimuth nearly constant between the two images of a pair,
so residual displacement is glacier motion rather than moving shadow. This is the
paper's stated reason for the 13:00 selection.

### On this dataset

584 photographs spanning 563 days, all at 12:00–13:59 local, all 6000 × 4000 from a
Canon EOS 2000D. 563 daily picks; the surplus comes from 4 October 2023, when the camera
was reinstalled and fired repeatedly. 420 of those picks fall inside the three camera
groups; the remainder are from the two snow-burial gaps, which lie between groups.

---

## 5. Stage 2 — `quality`

**Module** `glacier_tlc/quality.py` · **reads** `inventory.csv` · **writes** `quality.csv`, `images_used.csv`

The paper excluded roughly 200 photographs manually for "lens glare, low lighting,
snowstorms, and fog, which intermittently obscured the view of the glacier", and
excluded the whole mid-February-to-early-May 2024 period during which the camera was
buried in snow [3.1.2]. Manual inspection of 584 images is not reproducible, so this
stage screens automatically and lets you override the result by hand.

### The two kinds of test

**Global image metrics**, computed on a quarter-resolution copy (the JPEG decoder
produces this directly, so it costs almost nothing):

| metric | meaning | catches |
|---|---|---|
| `brightness` | mean grey level | night, whiteout |
| `contrast` | standard deviation of grey level | fog, snow-covered lens |
| `sharpness` | variance of the Laplacian | defocus, snow or water on the lens |
| `saturation` | mean HSV saturation | colour casts |
| `clipped_frac` | fraction of pixels below 5 or above 250 | glare, heavy under- or over-exposure |

**Scene visibility.** Global metrics alone cannot distinguish "hazy but usable" from
"the glacier is gone". So the stage detects SIFT keypoints in the upper
`static_fraction` (default 0.7) of the frame — the valley walls and ridges, which do not
move — and matches them, with a ratio test and a RANSAC similarity model, against:

* the **group reference image**, and
* the **±2 temporally neighbouring photographs**.

The larger inlier count of the two becomes `vis_inliers`. The neighbour comparison
matters because the scene's appearance changes seasonally: a January image matches a
January neighbour far better than an October reference, and judging it only against the
reference would reject a perfectly good winter photograph.

The RANSAC translation recovered against the reference is also written out as
`shift_dx_px` / `shift_dy_px`. That is the diagnostic used to establish the camera-group
boundaries — see Section 16.

### The decision

An image is usable when all thresholds in `quality.thresholds` pass. Two plain-text
files beside the image folder override the automatic verdict: `exclude_images.txt`
removes an image the screen accepted, `include_images.txt` forces in one it rejected.
Both take one file name per line and ignore `#` comments. `quality.csv` records the
metrics, the verdict and a semicolon-separated `flags` string naming every failed test,
so a rejection can always be explained.

### On this dataset

402 of the 420 in-group daily photographs pass. The 18 rejections break down as
16 low visibility, 14 blurry, 13 low contrast (an image usually trips several at once)
and correspond to snow-covered-lens days and one whiteout.

**Deviation.** This is an automated reconstruction of a manual step, so the excluded set
will not be identical to the authors'. The paper's ~200 exclusions were drawn from the
full ~3250-image archive (all times of day), whereas this dataset is already reduced to
one photograph per day, which is why the rejection count here is much smaller.

---

## 6. Stage 3 — `extract`

**Module** `glacier_tlc/extract.py` · **reads** `images_used.csv` · **writes** `.cache/crops/`

A purely mechanical stage, and the one that makes the pipeline fast.

For each usable photograph it decodes the full-resolution grey-scale image **once**,
cuts out every ROI of that image's group with a `tracking.pad_px` (40 px) margin on all
sides, applies the enhancement, and stores raw crop, enhanced crop and the crop's origin
in a compressed `.npz`. Everything downstream works on these small arrays.

The margin exists so that features near an ROI edge can be tracked to positions outside
the nominal rectangle: KLT needs a 31 × 31 window around the tracked point, and a
feature that moves outward would otherwise be lost against the crop boundary.

### Image enhancement

The paper enhances with adaptive histogram equalisation (Hummel 1977), naming MATLAB's
`adapthisteq`, and reports it gave "the most robust and abundant feature detections
compared to the other enhancement methods tested" [3.2]. OpenCV's CLAHE is the same
algorithm, but its clip limit is parameterised differently. `glacier_tlc/enhance.py`
converts between them:

```
MATLAB:  clip = ceil(N/bins) + c_m · (N − ceil(N/bins))
OpenCV:  clip = c_cv · N / bins
     ⇒   c_cv = 1 + c_m · (bins − 1)
```

With MATLAB's defaults (`c_m` = 0.01, 256 bins, 8 × 8 tiles), `c_cv` ≈ 3.55, which is the
configured value. Two alternative methods, `none` and `canny`, are available for
reproducing the comparison the authors ran (their Figure S1); `clahe` is the default
because that is what the paper adopted.

---

## 7. Stage 4 — `track` (the core)

**Module** `glacier_tlc/track.py`, algorithm in `glacier_tlc/tracking.py`
**reads** `.cache/crops/` · **writes** `pairs_raw.csv`, `.cache/vectors/`

This implements [3.2.2] exactly as described: a hybrid SIFT–KLT workflow, RANSAC with an
affine motion model, then a direction filter.

### Pair formation

All combinations (nC2) of usable photographs **within one camera group**. Pairs never
cross a group boundary, because the ROI rectangles and the camera pose differ on either
side. By default `pairs.max_baseline_days` is unset (`null`), so every pair a group's
images can form is tracked — 28,546 pairs for this dataset — matching both the paper's
Figure 2 and the MATLAB script's unbounded `nchoosek(1:numImages, 2)`. Setting a number
caps the baseline for a lighter, faster run; see `docs/REMOTE_RUN.md` for sizing a full
uncapped run on a larger machine.

### The five steps, per pair and per ROI

**1 · SIFT keypoint detection.** SIFT is run on the enhanced crop of image A, masked to
the ROI rectangle. Only the **keypoint locations** are used. The descriptors are computed
by neither side and never matched, exactly as the paper specifies: "These SIFT-derived
keypoints served only as the initial feature positions; we did not use SIFT descriptors
for matching" [3.2.2]. SIFT is chosen for detection because its keypoints are stable
under the lighting, shadow, fog and snow changes that a year of time-lapse imagery
contains.

**2 · KLT optical flow, forward and backward.** Each keypoint is tracked into image B by
pyramidal Lucas–Kanade (31 × 31 window, 3 pyramid levels, up to 30 iterations), then
tracked back from B into A. A point survives only if both directions converge, the
end point lies inside the crop, and the round-trip discrepancy is at most
`max_bidirectional_error` (2 px). This is the paper's "maximum bidirectional error
threshold to ensure high-quality matches", and it is what removes points that drifted
onto a different feature.

**3 · RANSAC with an affine model.** The surviving correspondences are fitted with a
full affine transform, and points more than `ransac.reproj_threshold_px` (2 px) from
their modelled position are discarded. The paper's justification for affine rather than
a simpler model is worth restating because it drives the choice: "the apparent glacier
motion in the image plane encompasses not only translation but also first-order
deformation (rotation, shear, and slight differential scaling) resulting from velocity
gradients, surface topography, and variations in camera orientation. Simpler
translational or rigid-body models were insufficient" [3.2.2].

Note that the affine fit is used **only to identify outliers**. The velocity is taken
from the surviving individual vectors, not from the fitted transform, so real
within-ROI velocity gradients are preserved rather than collapsed onto a plane.

**4 · Direction filter.** Vectors whose direction differs from the reference direction by
more than `direction_filter.threshold_deg` (30°) are dropped, the difference being
computed on the circle so that the ±180° wrap is handled correctly. The reference is by
default the pair's own median direction. The filter is applied to the glacier ROIs only,
not to the stable region (deviation D4).

**5 · Statistics.** For the surviving vectors the stage records counts at every step
(`n_sift`, `n_klt`, `n_ransac`, `n_vectors`) and, for magnitude, direction and the x and
y components, the median, mean, standard deviation and NMAD, plus the mean below the
95th percentile. Direction statistics are circular: the mean is the angle of the mean
unit vector, and the spread is measured as deviation from the median.

The vectors themselves are written to `.cache/vectors/<group>/<A>__<B>.npz` so that
figures and any re-analysis need not repeat the tracking.

### Resumability

Before tracking a pair, the stage checks for a cached `.npz` containing every requested
ROI and reuses it if present. Widening the baseline, adding an ROI or changing a
downstream parameter therefore costs only the genuinely new work. Caching happens at the
level of the vectors, so a change to a **tracking** parameter does require deleting
`.cache/vectors/`.

### Parameter provenance

| parameter | value | source |
|---|---|---|
| SIFT contrast threshold | 0.04 (OpenCV) | OpenCV default; equals MATLAB's 0.0133 default after OpenCV's internal division by the 3 octave layers |
| SIFT edge threshold, octave layers, σ | 10, 3, 1.6 | defaults in both libraries |
| KLT window | 31 × 31 | MATLAB `vision.PointTracker` default, matching the prototype |
| KLT pyramid levels / iterations | 3 / 30 | as above |
| max bidirectional error | 2 px | explicit in the prototype; the paper states the criterion without a value |
| RANSAC trials / confidence | 5000 / 99 % | explicit in the prototype |
| RANSAC reprojection threshold | 2 px | **this pipeline** — the prototype's value disabled rejection (deviation D3) |
| direction window | ±30° | explicit in the prototype; the paper states the criterion without a value |

---

## 8. Stage 5 — `velocity`

**Module** `glacier_tlc/velocity.py` · **reads** `pairs_raw.csv`, `.cache/vectors/` · **writes** `pairs_velocity.csv`

This is [3.3]: camera-motion correction, uncertainty, and the conversion to metric units.

### Camera-motion correction

Every pair also carries a measurement of the stable, non-moving terrain region near the
lake margin. Whatever displacement is measured there is not ground motion; it is the
camera having shifted, plus the tracking algorithm's own error. Following the paper,
"the systematic camera-induced bias was removed by subtracting the median displacement
of the stable region from the glacier motion estimates":

```
v_corrected = v_raw − median(v_stable)
```

The subtraction is applied **to each glacier vector individually**, before any statistic
is taken, so that the corrected magnitude is the magnitude of the corrected vector and
not the difference of two magnitudes. The pair's velocity is then the median of those
corrected magnitudes, matching "the median magnitude across all motion vectors was
computed" [3.2.2].

A pair is marked `valid` when the stable region yielded at least
`velocity.min_vectors_stable` vectors, the glacier ROI at least `velocity.min_vectors`
(20 each), and the corrected median is finite. Invalid rows are kept in the output with
`valid = False` rather than deleted, so nothing disappears silently.

### Scaling to metres

The paper converts with "a photogrammetric scaling approach ... using TLC parameters
(camera sensor size, image resolution, and focal length) and the metric measured
distance between the features and the camera position" [3.3]. For a pinhole camera the
ground sampling distance at range *D* is

```
GSD = D · (sensor width / image width) / focal length
```

For this camera — 22.3 mm sensor width, 6000 px, 24 mm lens — the pixel pitch is
3.717 µm and

| ROI | distance | GSD | ROI width in metres |
|---|---|---|---|
| ROI1 | 900 m | 0.1394 m/px | 69–91 m |
| ROI2 | 700 m | 0.1084 m/px | 62–70 m |
| ROI3 | 450 m | 0.0697 m/px | 40–54 m |
| stable | 900 m | 0.1394 m/px | 58–91 m |

consistent with the paper's description of "~100 m ROIs" [5.4]. Velocity follows by
dividing by the pair's time separation and rescaling to a year or a month:

```
feature velocity [m yr⁻¹] = median|v_corrected| [px] · GSD · 365.25 / Δt[days]
horizontal      [m yr⁻¹] = median(Δx_corrected) · sign · GSD · 365.25 / Δt
vertical        [m mo⁻¹] = −median(Δy_corrected)      · GSD · 30.44  / Δt
```

An explicit `scale_m_per_px` in the configuration overrides the computed GSD, which is
how you would substitute a scale derived from surveyed ground control points.

### Flow sign

The paper reports horizontal velocity as a positive quantity along the flow direction.
In image coordinates the glacier at Drang Drung moves toward −x, so the pipeline
multiplies by a per-group sign. With `flow_sign_x: auto` the sign is determined from the
median corrected Δx over all long-baseline pairs of the group; it resolved to −1 for all
three groups here, with medians of −5.8, −6.9 and −5.3 px. It can be pinned per group.

---

## 9. Stage 6 — `aggregate`

**Module** `glacier_tlc/aggregate.py` · **reads** `pairs_velocity.csv` · **writes** the `velocity_*.csv` family

### Windows

The paper presents velocity as a sequence of horizontal bars spanning weeks to months
(its Figures 3, 5, 6). A window here collects every valid pair whose **both** images lie
inside it and whose baseline is at least `aggregation.min_days` (5 days); the window is
reported only if at least `aggregation.min_pairs` (20) such pairs exist.

Three numbers come out of each window:

* **the value** — the median across the contributing pairs (configurable to `mean` or
  `weighted_mean`, the latter weighting by baseline squared);
* **`unc_*`** — the median of the pairs' stable-region uncertainties, the measurement
  uncertainty;
* **`spread_*`** — the NMAD *across* the pairs, a measure of how consistent the pairs
  are with one another. Large spread with small uncertainty means real sub-window
  variability, not measurement noise.

In `monthly` mode the windows are calendar months clipped to the group ranges. A month
split by a camera move produces two windows, suffixed `a` and `b` — August 2024 here,
where the 19 August retrieval moved the camera. Arbitrary windows can be supplied with
`mode: custom`.

The minimum pair count matters more than it appears. Set to 20, it discards the May 2024
window, which rested on 6 to 12 pairs from the handful of images recovered as the camera
emerged from the snow and reported implausible velocities of 30 to 52 m yr⁻¹. Including
it inflated the ROI2 annual mean by almost 3 m yr⁻¹. A window built on few pairs
near a data gap should not be trusted, and the threshold is the mechanism that says so.

The minimum baseline of 5 days exists because displacement scales with time while the
noise floor does not: velocity is a pixel displacement divided by elapsed time, and the
stable-region tracking noise that sets that displacement's precision does not shrink with
a shorter baseline, so a 5-day pair carries several times the velocity noise of a
20-day pair. With `pairs.max_baseline_days` capped at 20 days (as it was for an earlier,
faster run on this dataset), a window's pairs came entirely from the 5–20 day range and
were dominated by the noisier short end; measured on this data, restricting a window to
its 14–20 day pairs alone roughly halved `spread_horizontal_m_yr` while leaving the
median value essentially unchanged. With the cap removed (the default), windows also draw
on pairs beyond 20 days, which are quieter still, and the visible spread in
`fig3_feature_velocity.png` and `fig5_horizontal_velocity.png` narrows correspondingly. At ROI1, 25 m yr⁻¹ over one day is 0.49 px, comparable to the
tracking noise, whereas over 12 days it is 5.9 px. Short pairs are retained in
`pairs_velocity.csv` and used for the short-term analysis, but they are kept out of the
window statistics.

### Annual, seasonal, interannual

Periods are named in the configuration. For each, the stage reports both the mean over
the monthly windows (`*_window_mean`, the figure the paper's annual means correspond to)
and a direct statistic over all the pairs in the period (`*_pairs`). Quoting both makes
the sensitivity to the aggregation choice visible rather than hidden.

`season_comparisons` produces the percentage speed-up between two named seasons, the
paper's "summer velocities were 42 % higher than the winter–spring values" [4.1].
`interannual` compares the same calendar months in consecutive years, its Table S1.

### Short-term series and local maxima

For [5.2], the June 2024 analysis: pairs with a baseline of at most
`short_term.max_baseline_days` (3 days) are assigned to their mid-date and reduced to a
daily median. A centred rolling median over `smoothing_window_days` (5 days) is the
moving-window trend, and a local maximum is a day at which that trend is the highest
within ±2 days, with the series edges excluded because a trend value there is computed
from a truncated window.

The paper describes this as "applying a moving window to the velocity time series"
without stating the window length or the maximum criterion, so the exact set of maxima
is implementation-dependent — see deviation D11.

---

## 10. Stage 7 — `compare`

**Module** `glacier_tlc/compare.py` · **writes** `comparison_field_itslive.csv`

Places the annual TLC velocity beside the two independent references used in [3.4] and
[5.4]: the GNSS ablation-stake velocity of 23.64 m yr⁻¹ near ROI2 measured between
September 2022 and September 2023, and the ITS_LIVE values for each ROI. It reports the
difference and the ratio. Both references come from the configuration, so a fresh
ITS_LIVE extraction can be dropped in without touching the code.

---


## 12. Stage 9 — `plots`, Stage 10 — `report`

`plots` writes the paper-equivalent figures and a set of quality-assurance figures that
have no counterpart in the paper but are what you look at when a number seems wrong:

| figure | shows |
|---|---|
| `fig3_feature_velocity.png` | feature velocity per window, one panel per ROI |
| `fig4_vectors_<season>_<group>.png` | motion vectors on the image, coloured by velocity |
| `fig5_horizontal_velocity.png` | horizontal velocity, all ROIs, with ITS_LIVE and GNSS lines |
| `fig6_vertical_motion.png` | vertical motion per window |
| `fig7_short_term_<period>.png` | daily series, trend, local maxima, optional ERA5 overlay |
| `qa_camera_shift.png` | stable-region displacement per day through the record |
| `qa_image_quality.png` | the screening metrics, accepted and rejected |
| `qa_vectors_per_pair.png` | surviving vectors per pair through time |
| `qa_pair_velocities.png` | every valid pair's velocity, coloured by baseline |
| `lake_indices.png` | the lake colour indices |

`report` assembles `output/report.md` from the CSVs: data counts and exclusion reasons,
the group and scaling table, every window, the annual and seasonal summaries, the
short-term maxima, and the comparison table.

---

## 13. Conventions: axes, signs, units

Image coordinates follow the paper's Figure 2: **x** to the right, **y downward**,
origin at the top-left corner, in full-resolution pixels.

| quantity | convention | unit |
|---|---|---|
| feature velocity | median corrected vector magnitude, always ≥ 0 | m yr⁻¹ |
| horizontal | positive **along flow**; image x multiplied by `flow_sign_x` | m yr⁻¹ |
| vertical | positive **upward**, i.e. −Δy; negative means lowering | m month⁻¹ |
| direction | degrees, `atan2(Δy, Δx)`, in raw image coordinates | ° |
| uncertainty | one stable-region NMAD, not a multiple of it | same as the quantity |

The paper decomposes motion into a component "parallel to the glacier surface" and one
"normal to" it, justifying the direct use of image axes by noting that "the camera was
set up at a close angle perpendicular to the glacier ice flow direction" [4.1]. This
pipeline inherits that simplification (deviation D8).

Vertical motion is reported per month, as in the paper's Figure 6, because it is an
order of magnitude smaller than horizontal motion and a yearly rate would be misleading
for a signal that is confined to the melt season. `vertical_m_yr` is also available in
`pairs_velocity.csv`.

---

## 14. The uncertainty model

The paper's rule is direct: "the Normalised Median Absolute Deviation (NMAD) of the
stable-region displacement was used as the uncertainty measure" [3.3]. NMAD is
`1.4826 · median(|x − median(x)|)`, the robust equivalent of a standard deviation.

The chain is:

1. **Per pair** — the stable region's NMAD of magnitude, Δx and Δy, in pixels. It
   captures both the residual camera motion the median correction did not remove and the
   tracking algorithm's own error, on the same scene, on the same day, under the same
   illumination.
2. **Scaled** — multiplied by the *glacier* ROI's GSD and divided by the baseline, so
   that the uncertainty is expressed in the same units as the velocity it qualifies. A
   long baseline therefore yields a smaller uncertainty, correctly: a fixed pixel error
   over more days is a smaller velocity error.
3. **Per window** — the median of the contributing pairs' uncertainties.

Step 3 is deliberately conservative. The pairs in a window share images and are not
independent, so dividing by √n would overstate the precision; taking the median instead
keeps the window uncertainty at the level of a single measurement.

Typical values here: the stable-region NMAD spans 0.06–0.66 px between the 5th and 95th
percentiles, giving a median window uncertainty of 0.62 m yr⁻¹ and a range of roughly
0.2–1.0 m yr⁻¹ for most windows. Three windows exceed 2 m yr⁻¹ — February 2024 and
November–December 2024 — when snow cover reduced the stable region's texture. The paper
reports "±0.3 and ±1.2 m yr⁻¹, corresponding to 1 %–5 % of the seasonal ice velocities"
[4.1].

Two other spread measures are reported and should not be confused with the uncertainty:
`mag_corr_nmad_px` / `spread_feature_*` is the variability of motion *within* an ROI, and
`spread_*` at window level is the variability *between* pairs.

---

## 15. Deviation register

Every point at which this pipeline does something the paper does not specify, or does
something different from what it specifies. Nothing else in the method departs from
the publication.

| # | Paper | Pipeline | Why | Impact | Knob |
|---|---|---|---|---|---|
| **D1** | nC2 over all images of a group, no stated bound [Fig. 2] | none by default; `pairs.max_baseline_days` can optionally cap it for a lighter run | — | none when uncapped (default); a capped run excludes long-baseline pairs, which measurably *increases* window spread — see Section 9 | `pairs.max_baseline_days` (default `null` = unbounded) |
| **D2** | ~200 images excluded manually [3.1.2] | automatic thresholds plus manual override lists | manual selection is not reproducible | the excluded set will differ from the authors' | `quality.thresholds`, `exclude_images.txt` |
| **D3** | outliers "removed using RANSAC" [3.2.2], no threshold given | 2 px reprojection threshold | the prototype's 2000 px accepted every point, contradicting the stated intent | rejects genuine outliers; see MATLAB_COMPARISON.md §6 | `tracking.ransac.reproj_threshold_px` |
| **D4** | direction filter described for glacier motion vectors [3.2.2] | applied to glacier ROIs only, not the stable region | camera shake has no preferred direction; filtering it biases the correction toward its own median | slightly larger, more honest stable-region NMAD | `direction_filter.apply_to_stable` |
| **D5** | reference direction is "the median glacier flow direction, as derived from terrestrial observations" [3.2.2] | the pair's own median direction by default | no per-ROI flow azimuth is published | on near-zero-motion pairs the median direction is noise-defined, so the filter retains a noise cluster rather than rejecting it | `direction_filter.reference_direction` accepts a fixed azimuth per group and ROI |
| **D6** | not mentioned | no lens-distortion correction | no calibration published | second-order: both images are distorted identically, so the differential displacement is largely unaffected | — |
| **D7** | "the metric measured distance between the features and the camera" [3.3] | one distance per ROI, from the paper's stated values | the surveyed distances are not published | velocities are ROI-mean-scaled; an oblique view has a range gradient across an ROI | `distances_m`, `scale_m_per_px` |
| **D8** | horizontal parallel to, vertical normal to, the glacier surface [4.1] | image x and −y used directly | the paper makes the same simplification, justified by the near-perpendicular view | "vertical" is image-plane vertical and mixes in some flow-parallel motion for a downward-looking view | — |
| **D9** | median magnitude across vectors [3.2.2]; pair-to-window combination unspecified | median across pairs | consistency with the per-pair statistic | mean shifts values by a few tenths of a m yr⁻¹ | `aggregation.stat` |
| **D10** | NMAD is the uncertainty [3.3]; combination across pairs unspecified | median of the per-pair NMADs | pairs share images and are not independent | conservative; no √n reduction | — |
| **D11** | "applying a moving window to the velocity time series" [5.2] | 5-day centred rolling median; maxima of the trend within ±2 d, edges excluded | window length and criterion not published | 3 maxima for ROI1 in June 2024 against the paper's 5 | `short_term.smoothing_window_days` |
| **D12** | daily velocities in the June analysis [Fig. 7] | pairs up to 3 days, placed at their mid-date | one-day pairs alone are close to the noise floor | smoother series, slightly reduced temporal resolution | `short_term.max_baseline_days` |
| **D13** | three ROIs [3.2.1] | a fourth ROI is defined but excluded by default | ROI4 exists in the prototype for all three groups but appears nowhere in the paper | none | `tracking.rois` |
| **D14** | ERA5-Land, PlanetScope, GCP survey [3.1.3, 3.4] | not bundled; ERA5 overlay accepted as a CSV | the data are not in the repository | the scaling validation of Figure S2 cannot be reproduced | `auxiliary.era5_daily_csv` |
| **D15** | camera group periods shown as figure labels [Fig. 2] | exact boundaries measured from scene shift | day-level boundaries are not published | agrees with the published labels; see Section 16 | `groups` |
| **D16** | — | quantitative lake colour index | the paper's lake analysis is visual | an addition; no paper equivalent | `lake_rect` |
| **D17** | — | flow-sign auto-detection | the paper states the sign convention implicitly | an addition | `velocity.flow_sign_x` |

---

## 16. Validation evidence

**Numerical parity with the authors' own output.** The authors provided one result file
from their MATLAB script, for ROI4 and the stable region over the four images of
3–6 November 2023 (not carried in this repository). During development, a parity test
re-computed those six pairs with the tracker configured to match the prototype exactly
and compared every median statistic against it — the full reasoning and table are in
`docs/MATLAB_COMPARISON.md`, Appendix 1. Worst disagreement across all twelve
region-pairs:

| statistic | worst difference |
|---|---|
| median magnitude | 0.007 px |
| mean magnitude | 0.007 px |
| median Δx | 0.015 px |
| median Δy | 0.008 px |
| median direction | 1.26° (on the stable region, where the signal is ~1 px of noise) |
| vector count | −0.1 % to +6.9 % |

At a GSD of 0.085 m/px and a one-day baseline, 0.015 px is 0.47 m yr⁻¹; over the 12-day
baselines that dominate the windows it is 0.04 m yr⁻¹. The residual comes from
implementation differences in the SIFT keypoint list, which is why the counts differ by
a few per cent while the medians do not move.

**Synthetic recovery.** A synthetic check shifted a textured image by a known sub-pixel
amount and confirmed the tracker recovers it to better than 0.1 px, that the direction
filter respects its window, and that a stable-region correction applied to a scene with
both camera shake and target motion returns the target motion alone.

**Camera-group boundaries.** Whole-scene SIFT matching of all 584 photographs against
fixed reference frames gives a step of ≈ −780 px in x at the 19 August 2024 retrieval and
≈ 97 px in y between the May–August and August-onward positions, with the intervening
periods showing no visibility at all. The resulting boundaries — 5 October 2023 to
16 February 2024, 16 May to 18 August 2024, 19 August 2024 to 24 February 2025 — match
the group labels printed in the paper's Figure 2 ("Oct 2023–Feb 2024", "May–Aug 2024",
"Aug 2024–Feb 2025"), which were not otherwise available as dates.

**Agreement with the published results.**

| quantity | this pipeline | paper |
|---|---|---|
| ROI2 annual horizontal, Oct 2023–Oct 2024 | 20.8 m yr⁻¹ | TLC 20.3 [5.4] |
| ROI2 annual minus GNSS stake | −2.9 m yr⁻¹ | −3.3 (20.3 against 23.64) [5.4] |
| ROI1 / ROI3 annual horizontal | 24.1 / 8.7 m yr⁻¹ | 24–28 / 6–14 [4.1] |
| summer speed-up, ROI1 / ROI2 / ROI3 | +39 / +54 / +63 % | +42 / +35 / +55 % [4.1] |
| peak vertical, ROI1 / ROI2 / ROI3 | −2.6 / −1.9 / −1.0 m mo⁻¹ | −2.0 / −1.4 / −0.9 [4.1] |
| ROI1 peak feature velocity | 43 m yr⁻¹ (August 2024) | ~40 [5.1] |
| typical uncertainty | 0.2–1.0 m yr⁻¹ | ±0.3 to ±1.2 [4.1] |
| TLC ÷ ITS_LIVE, ROI1 / ROI2 / ROI3 | 1.9 / 2.3 / 2.5 | ITS_LIVE substantially underestimates [5.4] |

The ROI2 row is the most informative: it is the only region with an independent in-situ
measurement. This pipeline gives 20.8 m yr⁻¹ where the paper's own TLC analysis gives
20.3, and both fall about 3 m yr⁻¹ below the GNSS ablation-stake value of 23.64 m yr⁻¹,
which the paper attributes to interannual variability, point-against-ROI sampling and the
mismatched observation periods [5.4]. Reproducing not just the velocity but the sign and
size of its disagreement with the stake is stronger evidence than the velocity alone.

The seasonal pattern, the ranking of the three regions, the summer thinning signal and
the ITS_LIVE underestimate all reproduce. The paper's quoted annual means of
35.4 and 19.5 m yr⁻¹ for the lake- and land-terminating regions [abstract, 4.1] are
higher than both this pipeline's values and the values legible in the paper's own
Figure 3, so that particular pair of numbers could not be reproduced.

---

## 17. Known limitations

* **Scaling rests on unpublished distances.** The three camera-to-ROI distances are the
  paper's approximate values. A 10 % error in a distance is a 10 % error in that ROI's
  velocity, applied uniformly. Replacing them with the surveyed values would be the
  single most valuable improvement, and needs only an edit to `distances_m`.
* **A single range per ROI.** The near and far edges of an obliquely viewed ROI are at
  different distances, so one GSD is an approximation whose error grows with ROI extent.
* **No tilt correction**, as discussed under D8: the vertical component is measured in
  the image plane.
* **Quality screening is automatic**, so borderline images may be judged differently
  from the authors' manual pass.
* **The spring gaps are unbridgeable.** February to mid-May 2024 and after
  25 February 2025 the camera was buried or the glacier not visible; no method recovers
  velocity there, and the paper says the same [3.1.2, 4.1].
* **Uncertainty covers measurement, not the scale.** The stable-region NMAD says nothing
  about systematic error in the distance or focal length.

---

## 18. Output file reference

| file | rows | key columns |
|---|---|---|
| `inventory.csv` | one per image with a readable EXIF time | `file`, `datetime`, `daily_pick`, `group` |
| `quality.csv` | one per in-group daily pick | metrics, `vis_inliers`, `shift_dx_px`, `shift_dy_px`, `usable`, `flags` |
| `images_used.csv` | the usable subset | as above |
| `pairs_raw.csv` | pair × ROI, pixel units | `n_sift`, `n_klt`, `n_ransac`, `n_vectors`, `mag_*`, `dir_*`, `dx_*`, `dy_*` |
| `pairs_velocity.csv` | pair × glacier ROI, metric | `valid`, `gsd_m_per_px`, `stable_*`, `mag_corr_median_px`, `feature_velocity_m_yr`, `horizontal_m_yr`, `vertical_m_month`, `unc_*` |
| `velocity_windows.csv` | window × ROI | `n_pairs`, value, `unc_*`, `spread_*`, `*_mean_*` |
| `velocity_annual.csv`, `velocity_seasonal.csv` | period × ROI | `*_window_mean`, `*_pairs`, `unc_*` |
| `velocity_seasonal_change.csv` | comparison × ROI × quantity | `change_percent` |
| `velocity_interannual.csv` | comparison × ROI | reference and target values |
| `velocity_daily.csv` | day × ROI | `value`, `unc`, `trend`, `local_max` |
| `velocity_local_maxima.csv` | one per maximum | `date`, `trend_value`, `daily_value` |
| `comparison_field_itslive.csv` | ROI | TLC, ITS_LIVE and GNSS values, differences, ratio |
| `lake_index.csv` | image | `ice_fraction`, `red_blue`, `saturation`, `hue_deg` |

Caches: `.cache/crops/<group>/<image>.npz` holds each ROI's raw crop, enhanced crop and
origin; `.cache/vectors/<group>/<A>__<B>.npz` holds each ROI's vector start positions,
displacements and stage counts. Both are reproducible and may be deleted.

---

## 19. Compute cost and how to reduce it

Measured on a 12-core laptop, three glacier ROIs plus the stable region
(`tracking.rois`), no baseline cap (the default: the full nC2 combination, 28,546 pairs):

| stage | time | notes |
|---|---|---|
| `inventory` | 1 s | EXIF only |
| `quality` | 2.5 min | 10 workers; SIFT on quarter-resolution copies |
| `extract` | 17 s | 10 workers; the only full-resolution decode |
| `track` | ~66 min at 4 workers | pair count does not depend on the ROI count in this table (3 ROIs + stable is fixed); see the worker-count table below |
| `velocity` | ~2 min | scales with pair count, still fast |
| `aggregate`, `compare`, `plots`, `report` | < 15 s | independent of pair count |
| `lake` | 75 s | optional |

`track` is the only stage whose cost scales with the baseline cap, and it parallelises
per pair with no cross-worker communication, so it scales close to linearly with core
count:

| workers | full uncapped run (28,546 pairs) |
|---|---|
| 4 | ~66 min |
| 8 | ~33 min |
| 16 | ~16 min |
| 32 | ~8 min |
| 48 | ~6 min |

See `docs/REMOTE_RUN.md` for a full sizing guide, including how to carry over a partial
`.cache/` cache from one machine to a larger one so only the pairs not yet tracked are
computed.

Levers, in order of effect:

1. **`pairs.max_baseline_days`** — unset (the default) tracks every pair a group's images
   can form. Setting a number caps it; the pair count grows roughly as the square of the
   baseline window, so a 20-day cap on this dataset cuts the 28,546 uncapped pairs to
   7,147. Capping trades window precision for speed — see Section 9's discussion of why a
   capped run shows more spread in the velocity figures.
2. **`tracking.rois`** — cost is linear in the number of ROIs.
3. **`-j`** — worker processes. Match this to the machine: leave a core or two free on a
   shared machine, use every core on a dedicated one.
4. **`--limit N`** — track only the first N pairs, for a smoke test.

Because finished pairs are cached, all of these can be tightened first and relaxed later
without recomputing anything already done.
