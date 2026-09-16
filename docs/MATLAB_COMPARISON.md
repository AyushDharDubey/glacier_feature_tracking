# `glacier_tlc` versus the authors' MATLAB prototype

An exhaustive account of what the Python pipeline **derives** from the authors' MATLAB
script, what it **changes**, and what it **adds**.

### What is being compared

| | |
|---|---|
| **Prototype** | `reprocess.m` (542 lines) and `main_code.m` (3 lines) by Pawan Singh, the paper's first author, together with a user manual; analysed during development, not carried in this repository |
| **Working copy** | a locally-edited copy of `reprocess.m` with four edits already applied before this work began (Part F) |
| **Reference output** | a CSV of six image pairs, ROI4 and the stable region, produced by the authors and used during development as the parity target (not in this repository) |
| **Pipeline** | `glacier_tlc/`, fourteen modules, driven by `config.yaml` |

Paper section numbers in square brackets refer to Singh, Vijay & Azam (2026),
Sci. Remote Sens. 13, 100431. The governing rule throughout: **where the script and the
paper disagree, the paper wins.**

---

## Contents

1. [Summary](#1-summary)
2. [Architecture, side by side](#2-architecture-side-by-side)
3. [Part A — Derived](#3-part-a--derived)
4. [Part B — Changed](#4-part-b--changed)
5. [Part C — Added](#5-part-c--added)
6. [Part D — Defects found in the prototype](#6-part-d--defects-found-in-the-prototype)
7. [Part E — Dead code and abandoned paths](#7-part-e--dead-code-and-abandoned-paths)
8. [Part F — Edits already present in the working copy](#8-part-f--edits-already-present-in-the-working-copy)
9. [Appendix 1 — Numerical parity](#9-appendix-1--numerical-parity)
10. [Appendix 2 — The 48 CSV columns, mapped](#10-appendix-2--the-48-csv-columns-mapped)
11. [Appendix 3 — Function map](#11-appendix-3--function-map)

---

## 1. Summary

The prototype implements **one stage** of the published method: per-pair feature
tracking, from a cropped region to a table of displacement statistics in pixels. It does
that stage well, and the Python tracker reproduces its numbers to within 0.015 px.

Everything the paper describes from Section 3.3 onward — subtracting the stable region,
deriving an uncertainty from its NMAD, converting pixels to metres, splitting horizontal
from vertical, and every temporal analysis built on those — is absent from the script. Its
manual is explicit about the gap, directing the reader to a web depth-of-field calculator
for the metric conversion. The script computes the stable region on every pair and writes
its statistics beside the glacier's, but never uses them: the correction was to be done by
hand, downstream, in some artefact that is not in this repository.

| | prototype | pipeline |
|---|---|---|
| lines of code | 542 | 1730 in 16 files (14 analysis modules plus package entry points), and 185 of tests |
| pairs tracked per group, default | one ROI per invocation, unbounded `nchoosek` | all ROIs in one pass, unbounded by default (B4) |
| stages of the published method covered | feature tracking [3.2.2] | all [3.1]–[5.4] |
| ROIs per run | 1 glacier ROI + stable | all ROIs in one pass |
| parameters exposed | 3 function arguments | one YAML file, no analysis constant in code |
| stable-region correction | computed, never applied | applied per vector |
| uncertainty | none | stable-region NMAD, propagated to every output |
| metric units | none (manual, via a web calculator) | photogrammetric scaling in-pipeline |
| temporal aggregation | none | windows, annual, seasonal, interannual, daily |
| resumable | no | yes, cached per pair |
| tests | none | 4, including parity against the prototype's own output |

---

## 2. Architecture, side by side

```
PROTOTYPE                                    PIPELINE
reprocess(csv, roiName, method)              python -m glacier_tlc <stage>
  |                                            |
  read image-name CSV                        [inventory]  EXIF times, daily pick, group
  nchoosek(N,2)  ── all pairs                             |
  hardcoded ROI table for 3 groups           [quality]    metrics, visibility, overrides
  parfor over pairs:                                      |
    imread A, imread B   (full 24 MP)        [extract]    decode once, crop+enhance, cache
    for stable and motion region:                         |
      imcrop -> adapthisteq                  [track]      per pair x ROI:
      detectSIFTFeatures                                    SIFT -> KLT -> RANSAC -> direction
      vision.PointTracker (bidir 2 px)                      -> vectors + statistics (px)
      estgeotform2d affine, MaxDistance 2000                |
      filterByDirection 30 deg               [velocity]   stable correction, NMAD, scaling
      statistics -> row of 24                             |
      write crops, vector plot, histogram    [aggregate]  windows, annual, seasonal,
      write per-pair text file                            interannual, daily maxima
  Data_filtering: join motion+stable                      |
  write 48-column CSV and .mat              [compare] [lake] [plots] [report]
```

The decisive structural difference is where the loop sits. The prototype loops over
pairs and decodes two full 24-megapixel JPEGs inside every iteration, for one ROI at a
time. The pipeline decodes each photograph exactly once, caches the small enhanced crops
for all ROIs, and then loops over pairs on those crops. For this dataset that is
**171,276 full-resolution decodes against 402**, a factor of 426 (Part B, B6).

---

## 3. Part A — Derived

Carried over from the prototype, deliberately and without alteration in substance.

### A1 · The algorithm chain

The five-step sequence is the prototype's, and it is what the paper describes:

1. SIFT detects keypoints on the enhanced crop of image A; **descriptors are never
   computed or matched**, matching the paper's "these SIFT-derived keypoints served only
   as the initial feature positions" [3.2.2].
2. KLT pyramidal optical flow tracks those points into image B, with a forward–backward
   consistency check.
3. RANSAC with an **affine** motion model rejects outlier correspondences.
4. Vectors whose direction deviates from the median by more than a threshold are
   discarded.
5. Magnitude, direction and component statistics are computed on what survives.

The choice of an affine model, rather than translation or a rigid body, is the
prototype's and the paper's, for the reason the paper states: apparent glacier motion
contains first-order deformation from velocity gradients, surface topography and camera
orientation changes [3.2.2].

### A2 · Parameters

Every tracking constant is the prototype's value, now in `config.yaml` rather than
hard-coded:

| parameter | prototype | pipeline | note |
|---|---|---|---|
| SIFT contrast threshold | MATLAB default 0.0133 | OpenCV 0.04 | identical: OpenCV divides internally by the 3 octave layers |
| SIFT edge threshold | 10 | 10 | |
| SIFT octave layers, σ | 3, 1.6 | 3, 1.6 | |
| KLT window | [31 31] | 31 × 31 | MATLAB default; the script's `BlockSize` variable is never passed (Part E) |
| KLT pyramid levels | 3 | 3 | as above |
| KLT max iterations | 30 | 30 | as above |
| max bidirectional error | 2 px | 2 px | the one tracker option the script does pass |
| RANSAC trials | 5000 | 5000 | |
| RANSAC confidence | 99 % | 99 % | |
| RANSAC max distance | 2000 px | **2 px** | changed — see B1 |
| direction window | 30° | 30° | |
| enhancement | `adapthisteq` defaults | CLAHE, converted clip limit | equivalent — see B8 |

### A3 · The statistics

All 24 per-region statistics the prototype computes are reproduced, with the same
definitions, including two idiosyncratic ones that were kept for comparability:

* **`mag_mean95`**, the prototype's "Mean Magnitude (95%)": the mean of values *strictly
  below* the 95th percentile, not a symmetric trimmed mean.
* **NMAD** as `1.4826 · median(|x − median(x)|)`, matching `1.4826 * mad(x,1)`.

Standard deviations use the sample convention (N − 1), as MATLAB's `std` does.
Appendix 2 maps every column.

### A4 · ROI geometry

The three sets of ROI rectangles hard-coded in the prototype — `GRP1`, `GRP2`, `GRP3`,
each with a stable region and four motion ROIs in full-resolution pixel coordinates — are
carried into `config.yaml` unchanged, down to the pixel. Independent measurement of the
scene shift confirmed which set belongs to which period, and the resulting date ranges
match the group labels in the paper's Figure 2.

### A5 · Numerical equivalence

Configured to match the prototype, the Python tracker reproduces the authors' own output
for all six pairs of 3–6 November 2023 to within 0.015 px on every median displacement.
Full table in Appendix 1.

---

## 4. Part B — Changed

Each change states what the prototype did, what the pipeline does, and why.

### B1 · RANSAC actually rejects outliers

**Prototype** `estgeotform2d(..., 'MaxDistance', 2000)`. The largest ROI is 778 px wide,
and real displacements are 0.3–20 px, so a 2000 px gate admits every correspondence the
tracker produced. The RANSAC step was structurally present but functionally inert.

**Pipeline** 2 px reprojection threshold, configurable.

**Why** The paper states that "outlier correspondences were removed using RANSAC with an
affine transformation as the motion model" [3.2.2]. A threshold that removes nothing does
not implement that sentence. The paper gives no number; 2 px matches the bidirectional
error tolerance already in use, so a correspondence must be self-consistent to the same
precision in both tests.

**Effect, measured.** On five of the six reference pairs the change is invisible in the
medians. On the sixth — the stable region of 3 → 6 November, the longest baseline — it
removes 272 of 1749 vectors and moves the median magnitude from 1.051 to 0.988 px. That
is the intended behaviour: it is the pair where drift had time to accumulate.

### B2 · The direction filter is not applied to the stable region

**Prototype** `filterByDirection` sits inside `analyzeFeatureMotion`, which is called
identically for the glacier and the stable region, so both are filtered to ±30° of their
own median.

**Pipeline** glacier ROIs only; `direction_filter.apply_to_stable` restores the old
behaviour.

**Why** The stable region's displacement is residual camera motion and tracking error.
That has no preferred direction, so filtering it to a ±30° cone around its own median
discards the dispersion that *is* the measurement, shrinking the NMAD and understating
the uncertainty. Since the paper makes the stable-region NMAD the uncertainty measure
[3.3], the estimate must not be pre-narrowed. The paper's own wording ties the filter to
glacier flow: vectors "deviating significantly from the median glacier flow direction".

### B3 · Direction statistics are circular

**Prototype** `mean`, `std` and `prctile` are applied to direction as if it were a linear
quantity.

**Pipeline** circular mean (the angle of the mean unit vector); spread measured as
deviation from the median, wrapped to [0°, 180°]. The meaningless "Mean Direction (95 %)"
is dropped.

**Why, with evidence.** In the authors' own reference CSV, the stable region of the
4 → 5 November pair has a median direction of 165.94°, a mean of **66.35°** and a standard
deviation of **157.81°**. The vectors straddle the ±180° discontinuity, so the linear mean
lands 100° away from the median and the standard deviation inflates to almost half a
circle. Recomputing the same pair here:

| | mean | standard deviation |
|---|---|---|
| prototype (linear) | 66.35° | 157.81° |
| this pipeline, linear formulae | 67.14° | 157.36° |
| this pipeline, circular | **173.85°** | **6.92°** |

The middle row reproduces the failure, confirming it is the formula and not the data; the
bottom row is what the pipeline reports. Across all 28,588 pair-ROI rows of the full run
the median direction spread is 4.5°, with the 99th percentile at 40°, and no wrap-induced
blow-ups.

### B4 · Pair generation is group-aware; the baseline bound is optional

**Prototype** `nchoosek(1:numImages, 2)` over whatever list the CSV contains, with no
baseline bound; the user is responsible for ensuring the list belongs to one camera
position.

**Pipeline** pairs are formed inside a camera group automatically, never across a
boundary. `pairs.max_baseline_days` defaults to unbounded (`null`), reproducing the
prototype's full `nchoosek` exactly — 28,546 pairs for this dataset, the same count
`nchoosek(1:N,2)` per group would give. It can optionally be set to a number to cap the
baseline for a faster, lighter run (20 days gives 7,147 pairs); doing so measurably
increases the spread of the derived window velocities, because it excludes the longest,
lowest-noise pairs — see `docs/PIPELINE.md` Section 9.

**Why** Crossing a group boundary compares different ROI geometry, which the prototype
leaves to the operator to avoid by hand. The baseline bound exists only as an optional
compute-saving escape hatch, not as a change from the prototype's method.

### B5 · Time separation is not rounded

**Prototype** `round(days(dateB - dateA))`, an integer.

**Pipeline** the exact elapsed time as a float.

**Why** The camera's daily images are a few seconds apart from exactly 24 h, so the
difference is small here (0.003 %), but rate computation should not quantise its
denominator, and short-baseline work is where a rounded zero becomes a division by zero
(D3).

### B6 · One pass over the images, all ROIs at once

**Prototype** one motion ROI per invocation, both images decoded in full inside every
pair iteration. For three ROIs across three groups that is **171,276** decodes of a
24-megapixel JPEG, plus roughly 770,000 output files (two crops, a 600 dpi vector plot, a
300 dpi histogram and a text file, per region per pair), which on this dataset would be
tens of gigabytes.

**Pipeline** 402 decodes, once, in `extract`; crops cached at 346 MB; vectors stored as
compressed arrays at 414 MB; figures generated on demand from those arrays.

**Why** It is the difference between a run that takes minutes and one that takes days,
and it is what makes re-running a downstream stage after a parameter change cheap.

### B7 · Missing EXIF time is fatal, not silently replaced

**Prototype** falls back to `datetime('now')` with a warning, which inside a `parfor` is
easily missed.

**Pipeline** the image is dropped and the file named in the log.

**Why** A substituted date does not fail; it produces a plausible-looking velocity from a
baseline of several hundred days. The paper's method depends on true capture times.

### B8 · Enhancement clip limit is converted, not copied

MATLAB's `adapthisteq` normalises its clip limit to [0, 1] with a default of 0.01;
OpenCV's CLAHE expresses it as a multiple of the mean bin count. `glacier_tlc/enhance.py`
derives the exact correspondence, `c_opencv = 1 + c_matlab · (bins − 1)` ≈ 3.55, so the
same contrast limiting is applied rather than a visually similar one. Tile grid (8 × 8)
and bin count (256) are MATLAB's defaults.

### B9 · Crop indexing

MATLAB's `imcrop([x y w h])` returns a `(h+1) × (w+1)` array because the rectangle
boundary pixels are included; Python slicing returns `h × w`. The pipeline uses the
Python convention and adds a 40 px working margin around every ROI, so the tracked area
is defined by the mask rather than by the crop edge. The one-pixel difference has no
measurable effect, as Appendix 1 shows.

### B10 · Output format

The prototype's 48-column CSV pairs the motion and stable regions side by side on one
row, with duplicated date columns and a `_motion` / `_stable` suffix. The pipeline writes
one row per pair **per ROI** in `pairs_raw.csv`, joining to the stable region in the
`velocity` stage. This is what allows any number of ROIs rather than exactly one.

---

## 5. Part C — Added

None of the following exists in the prototype in any form.

### C1 · Stable-region correction  *(paper [3.3])*

The prototype measures the stable region on every pair and writes its statistics, but
never subtracts them. The pipeline subtracts the stable region's median displacement
**from each glacier vector individually**, before any statistic is taken, so that the
corrected magnitude is the magnitude of the corrected vector. This is the step that turns
apparent motion into glacier motion, and it is the single largest functional addition.

### C2 · Uncertainty  *(paper [3.3])*

The NMAD of the stable-region displacement, scaled to the glacier ROI's ground sampling
distance and the pair's baseline, becomes an uncertainty attached to every pair, carried
into every window, and drawn on every figure. The prototype computes stable-region NMAD
as one of 24 numbers in a table and does nothing with it.

### C3 · Photogrammetric scaling  *(paper [3.3])*

`GSD = distance · pixel pitch / focal length`, from the camera block and per-ROI
distances in the configuration, with an override for a surveyed scale. The prototype's
manual delegates this step to an external web calculator.

### C4 · Horizontal and vertical decomposition  *(paper [4.1], Fig. 2)*

Along-flow and surface-normal components in m yr⁻¹ and m month⁻¹, with automatic
detection of the flow sign per camera group.

### C5 · Image inventory and daily selection  *(paper [3.2])*

EXIF reading, one image per day nearest 13:00 local, and automatic assignment to a camera
group by date. The prototype takes a list of file names prepared by hand.

### C6 · Quality screening  *(paper [3.1.2])*

Brightness, contrast, sharpness, saturation and clipping metrics, plus a SIFT-based
scene-visibility test against both a group reference and the temporal neighbours,
with manual override lists. The prototype has no notion of an unusable image.

### C7 · Camera groups as a first-class concept  *(paper [3.2])*

The prototype hard-codes three ROI tables and leaves it to the operator to pass the right
group name on the command line. The pipeline stores each group's date range alongside its
rectangles, assigns images automatically, refuses to pair across a boundary, and splits a
calendar month that contains a camera move into two windows.

### C8 · Temporal aggregation  *(paper Figs. 3, 5, 6)*

Weekly-to-monthly windows with a configurable statistic, a minimum baseline and a minimum
pair count; a measurement uncertainty and a between-pair spread for each.

### C9 · Annual, seasonal and interannual summaries  *(paper [4.1], Table S1)*

Named periods, percentage speed-ups between seasons, and same-month comparisons across
consecutive years.

### C10 · Short-term series and local maxima  *(paper [5.2], Fig. 7)*

Daily velocities from short-baseline pairs, a moving-window trend, and detection of its
local maxima.

### C11 · Comparison with independent data  *(paper [3.4], [5.4])*

TLC velocity against the GNSS ablation-stake value and ITS_LIVE, with differences and
ratios.

### C12 · Proglacial lake index  *(paper [4.2], extended)*

Quantitative ice-fraction, turbidity and colour indices where the paper reports a visual
interpretation.

### C13 · Figures

The prototype emits a vector-quiver plot and a histogram per region per pair, in
per-pair folders, with no time axis anywhere. The pipeline produces the paper's figure
set plus four quality-assurance figures (camera shift, screening metrics, vectors per
pair, per-pair velocity scatter) that exist to diagnose a suspect number.

### C14 · Report

`output/report.md` assembles every table and the figure list into one document.

### C15 · Configuration

No analysis constant is hard-coded. The prototype exposes three function arguments and
requires source edits for everything else, including image paths and ROI coordinates.

### C16 · Caching and resumability

Crops and vectors are cached; an interrupted or widened run reuses everything already
computed. This is what allowed the tracking run here to be stopped, reconfigured and
restarted with 2,300 pairs served from cache in under two seconds.

### C17 · Tests

Four automated checks: sub-pixel shift recovery, direction-filter behaviour, stable-region
correction on a synthetic scene with both camera shake and target motion, and numerical
parity against the authors' own CSV.

### C18 · Structured logging and provenance

Each stage logs counts and timings; every output table carries the identifiers needed to
trace a number back to its image pair.

---

## 6. Part D — Defects found in the prototype

Each is stated with the evidence that establishes it. D1, D2, D3, D6, D8, D9 and D13
were already recorded in the authors' own development notes before this work began; D4, D5, D7, D10, D11 and
D12 are new findings.

### D1 · Image names are parsed into `<missing>`

```matlab
imageNamesRaw = string(imageNamesTable{:,1});
imageNames    = extractBefore(imageNamesRaw, ',');
```
`extractBefore` returns `<missing>` when the delimiter is absent, and a single-column
list of file names contains no comma. Every file name becomes missing and no image is
read. Fixed in the working copy (Part F).

### D2 · The CSV is never written

In the committed script, `Data_filtering` ends after assigning `VariableNames`; there is
no `writetable`. The caller nevertheless prints `Processing complete. Results saved to:
<file>`. The run produces the `.mat` file and the per-pair folders but no CSV, while
reporting success. Fixed in the working copy.

### D3 · Division by zero for same-day pairs

`daysBetween = round(days(dateB - dateA))` is 0 for two images from the same day — which
`nchoosek` will produce, and which this dataset contains for 4 October 2023 — and is then
used as a divisor in both `appendStatistics` and `saveStatistics_pair`. Fixed in the
working copy by guards returning `NaN`.

### D4 · "Mean Magnitude per Week" is per day

`appendStatistics` divides by `daysBetween`; `saveStatistics_pair` divides by
`weeksBetween`. The two outputs of the same run therefore disagree, and the CSV column
labelled "per Week" holds a per-day value.

Verified against the authors' own CSV: for all six rows the column equals
`Mean Magnitude / Days Between` exactly (ratio 1.000), where a true per-week value would
be 4.6–6.2 times larger.

### D5 · RANSAC rejects nothing

`MaxDistance` of 2000 px against displacements of 0.3–20 px. See B1.

### D6 · A missing capture date becomes today

See B7. The warning is emitted inside a `parfor`, where worker output is interleaved and
easily lost.

### D7 · Direction statistics break at the ±180° wrap

Demonstrated in B3 with the authors' own numbers: a mean of 66.35° and a standard
deviation of 157.81° for a distribution whose median is 165.94°.

### D8 · The Canny branch writes an invalid image

```matlab
Crop_edge    = edge(Crop, 'canny', threshold * 0.5);
enhancedImage = double(Crop_edge) .* double(Crop);
```
The result is a `double` array holding 0–255. `imwrite` interprets a `double` image as
being on a 0–1 scale, so the saved crop is clipped to white almost everywhere. It affects
only the saved images, not the statistics, and only when `method = 'canny'`.

### D9 · Full combinatorics, with a cost the prototype does not manage

`nchoosek` over the whole list, with each pair writing its own folder of nine files. At
178 images that is 15,753 pairs for one ROI of one group, each pair decoding two full
24-megapixel JPEGs (B6) and writing two crops, a 600 dpi vector plot, a 300 dpi histogram
and a text file. The combinatorics themselves are not a defect — the paper uses the same
nC2 combination, and the pipeline reproduces it by default (B4) — but the prototype has
no caching, no resumability and no bound on per-pair file output, so the cost of a full
run is unmanaged rather than merely large.

### D10 · The comment contradicts the code

`filterByDirection(inlierMovementDirection, 30); % 10-degree threshold` — the threshold
applied is 30°, and 30° is what the pipeline uses.

### D11 · Region separation depends on alphabetical luck

`Data_filtering` derives the region labels with `unique`, which sorts, then assigns
`regionTypes{1}` to motion and `regionTypes{2}` to stable. It works only because
`'motion_region'` sorts before `'stable_region'`. Renaming either region silently swaps
every motion and stable column in the output.

### D12 · Header comments are inverted

```matlab
header(1:24)  = strcat(header(1:24),  '_motion');  % Add "_stable" suffix to the first 24
header(25:48) = strcat(header(25:48), '_stable');  % Add "_motion" suffix to the next 24
```
The code is correct and the comments are reversed. Cosmetic, but it is the kind of
comment that causes a later reader to "fix" working code.

### D13 · `imageBasePath` in the working copy

The committed script defines `imageBasePath` inside `reprocess.m`. The working copy
removes that line and places it in `main_code.m` at script scope, where a function in a
separate file cannot see it, so the `parfor` body raises an undefined-variable error.
See Part F.

---

## 7. Part E — Dead code and abandoned paths

Not defects, but they show where the prototype was still in flux, and each one was a
decision this pipeline had to make deliberately.

* **A block of tuned parameters that is never used.** `analyzeFeatureMotion` assigns
  `contrastThreshold`, `edgeThreshold`, `numOctaves`, `sigma`, `BlockSize`,
  `FeatureSize`, `NumPyramidLevels`, `MaxIterations`, `MaxNumTrials`, `Confidence` and
  `MaxDistance`, then calls `detectSIFTFeatures(imageA)` with the options commented out
  and `vision.PointTracker('MaxBidirectionalError', 2)` with everything else omitted.
  Only the bidirectional error and the three RANSAC options passed literally at the call
  site take effect. The declared values happen to equal MATLAB's defaults for block size
  (31 × 31), pyramid levels (3) and iterations (30), so behaviour is unaffected — but the
  file reads as if it were configured when it is not. The pipeline passes every one of
  these explicitly.
* **`BlockSize` assigned twice**, first as `11`, then as `[31 31]`.
* **`trackedPoints = 'affine'`** assigned as a leftover before being overwritten by the
  tracker output.
* **`FeatureSize = 64`** — never referenced.
* **`selectROI`** — an interactive rectangle-drawing helper, never called; the manual
  documents it as an option.
* **`csvData` threaded through `processAndSaveStatistics`** as an argument that is always
  `[]` at the call site, so the accumulation it implies never happens; the real
  accumulation is the `parfor` result array.
* **`parpool` commented out** in the working copy, leaving `parfor` to run serially
  unless a pool already exists.

---

## 8. Part F — Edits already present in the working copy

The working copy of `reprocess.m` differed from the original in six places, applied
before this work began. The authors' own development notes recorded the reasoning for most of them:

| # | change | recorded in dev notes | verdict |
|---|---|---|---|
| 1 | `extractBefore` parsing replaced by direct string conversion | recorded, applied | correct fix for D1 |
| 2 | `imageBasePath` removed from `reprocess.m` and placed in `main_code.m` | recorded, applied | **breaks the script**: a function in its own file cannot see a variable defined at script scope elsewhere, so the `parfor` body fails on an undefined variable (D13) |
| 3 | `parpool(8)` commented out, comment changed to 4 cores | not in the notes | `parfor` now runs serially unless a pool already exists |
| 4 | guard against `daysBetween == 0` in `appendStatistics` | recorded, applied | correct fix for D3 |
| 5 | guard against `weeksBetween == 0` in `saveStatistics_pair` | recorded, applied | correct fix for D3 |
| 6 | `writetable` added at the end of `Data_filtering` | listed as *flagged, not yet applied* | correct fix for D2; the notes were out of date with respect to the file |

The Python pipeline was written against the **committed original** and validated against
the authors' reference CSV during development, so none of these edits affect it.

---

## 9. Appendix 1 — Numerical parity

A parity test, run during development against the authors' own reference CSV (not
carried in this repository). The tracker is configured to match the prototype exactly:
RANSAC threshold 2000 px, direction filter applied to the stable region as well. `mat` is
the authors' MATLAB value, `py` this pipeline's.

| pair | region | n mat | n py | Δn % | median magnitude mat → py | Δ | median Δx mat → py | Δ | median Δy mat → py | Δ |
|---|---|---|---|---|---|---|---|---|---|---|
| 03→04 Nov | motion | 1489 | 1584 | +6.4 | 0.8848 → 0.8883 | +0.0035 | −0.7927 → −0.7912 | +0.0014 | −0.3865 → −0.3921 | −0.0055 |
| 03→04 Nov | stable | 1433 | 1519 | +6.0 | 0.7795 → 0.7729 | −0.0066 | −0.3085 → −0.3040 | +0.0046 | −0.6823 → −0.6746 | +0.0077 |
| 03→05 Nov | motion | 1501 | 1597 | +6.4 | 1.5147 → 1.5154 | +0.0007 | −1.4850 → −1.4872 | −0.0023 | −0.2687 → −0.2769 | −0.0082 |
| 03→05 Nov | stable | 1580 | 1689 | +6.9 | 0.9678 → 0.9703 | +0.0026 | −0.6990 → −0.6905 | +0.0085 | −0.6477 → −0.6508 | −0.0031 |
| 03→06 Nov | motion | 1501 | 1597 | +6.4 | 1.9886 → 1.9858 | −0.0028 | −1.9684 → −1.9683 | +0.0001 | 0.2534 → 0.2469 | −0.0065 |
| 03→06 Nov | stable | 1644 | 1749 | +6.4 | 1.0442 → 1.0513 | +0.0070 | −0.7318 → −0.7467 | −0.0150 | 0.6844 → 0.6815 | −0.0029 |
| 04→05 Nov | motion | 1766 | 1764 | −0.1 | 0.6991 → 0.6989 | −0.0002 | −0.6880 → −0.6860 | +0.0020 | 0.1187 → 0.1209 | +0.0022 |
| 04→05 Nov | stable | 1935 | 1954 | +1.0 | 0.3661 → 0.3664 | +0.0004 | −0.3598 → −0.3585 | +0.0013 | 0.0306 → 0.0319 | +0.0014 |
| 04→06 Nov | motion | 1766 | 1764 | −0.1 | 1.3357 → 1.3379 | +0.0022 | −1.1715 → −1.1684 | +0.0031 | 0.6277 → 0.6330 | +0.0053 |
| 04→06 Nov | stable | 2290 | 2349 | +2.6 | 1.4310 → 1.4331 | +0.0021 | −0.4538 → −0.4602 | −0.0065 | 1.3338 → 1.3352 | +0.0014 |
| 05→06 Nov | motion | 1778 | 1806 | +1.6 | 0.6976 → 0.6999 | +0.0023 | −0.4734 → −0.4692 | +0.0042 | 0.5093 → 0.5087 | −0.0006 |
| 05→06 Nov | stable | 2281 | 2379 | +4.3 | 1.3238 → 1.3259 | +0.0021 | −0.1104 → −0.1036 | +0.0068 | 1.3117 → 1.3138 | +0.0020 |

Worst absolute disagreement: median magnitude 0.007 px, mean magnitude 0.007 px,
median Δx 0.015 px, median Δy 0.008 px, median direction 1.26°. Vector counts differ by
−0.1 % to +6.9 %.

**Interpretation.** The two SIFT implementations return slightly different keypoint
lists — a few per cent more in OpenCV — but the median displacement of a population of
1500 to 2400 vectors does not care which particular subset it is measured on. At ROI4's
ground sampling distance of 0.085 m/px, 0.015 px is 0.47 m yr⁻¹ over a one-day baseline
and 0.04 m yr⁻¹ over the twelve-day baselines that dominate the reported windows, an
order of magnitude below the stable-region uncertainty. The direction figure of 1.26° is
on the stable region, where the "direction" is that of about one pixel of residual noise.

---

## 10. Appendix 2 — The 48 CSV columns, mapped

The prototype's CSV carries 24 statistics twice, suffixed `_motion` and `_stable`. The
pipeline writes one row per ROI, so the suffix disappears and the `roi` column takes its
place.

| prototype column | pipeline column, in `pairs_raw.csv` | note |
|---|---|---|
| Region Type | `roi` | the ROI name; `group` identifies the camera period |
| Image Date A / B | `datetime_a`, `datetime_b` | |
| Days Between | `days` | float, not rounded (B5) |
| Number of Vectors | `n_vectors` | joined by `n_sift`, `n_klt`, `n_ransac` — new |
| Mean Magnitude (95%) | `mag_mean95` | same definition, mean below the 95th percentile |
| Mean Magnitude | `mag_mean` | |
| Median Magnitude | `mag_median` | the quantity the paper uses |
| Std Dev Magnitude | `mag_std` | |
| NMAD Magnitude | `mag_nmad` | |
| Mean Direction (95%) | — | dropped: not meaningful on a circular quantity (B3) |
| Mean Direction | `dir_mean` | circular mean (B3) |
| Median Direction | `dir_median` | |
| Std Dev Direction | `dir_std` | deviation from the median, wrapped (B3) |
| NMAD Direction | `dir_nmad` | as above |
| Mean / Median / Std Dev / NMAD Motion X | `dx_mean`, `dx_median`, `dx_std`, `dx_nmad` | the prototype reconstructs X as `magnitude · cos(direction)`; the pipeline uses the vector component directly — identical by construction |
| Mean / Median / Std Dev / NMAD Motion Y | `dy_mean`, `dy_median`, `dy_std`, `dy_nmad` | as above |
| Mean Magnitude per Week | — | dropped: mislabelled and inconsistent (D4). Superseded by the metric rates in `pairs_velocity.csv` |

Columns with no prototype counterpart, added in `pairs_velocity.csv`: the stable-region
displacement and NMAD, the corrected magnitude and components, the ground sampling
distance, the three metric velocities, their uncertainties, the within-ROI spread, the
flow sign and the validity flag.

---

## 11. Appendix 3 — Function map

| prototype function | fate | pipeline location |
|---|---|---|
| `reprocess` | split by concern | `track_stage.run` (orchestration), `config` (ROI tables), `inventory` (image list) |
| `enhanceImage` | derived | `enhance.make_enhancer`, with the clip-limit conversion of B8 |
| `readImageWithMetadata` | derived, fallback removed | `inventory.read_exif_datetime` (B7) |
| `analyzeRegion` | derived | `extract._extract_one` + `tracking.Tracker.track` |
| `analyzeFeatureMotion` | derived, parameters now passed | `tracking.Tracker.track` |
| `filterByDirection` | derived, circular and glacier-only | `tracking.Tracker.track` step 4, `utils.circ_diff_deg` (B2, B3) |
| `calculateStatistics` | derived, circular direction | `tracking.vector_stats`, `utils.nmad`, `utils.mean_below_p95` |
| `appendStatistics` | superseded | `tracking.vector_stats`; the per-week column dropped (D4) |
| `saveStatistics_pair` | superseded | `pairs_raw.csv` |
| `Data_filtering` | superseded | the `velocity` stage joins motion to stable and applies the correction (C1) |
| `assigningHeaderToCsv` | not needed | column names come from the data frame |
| `plotMotionVectors` | derived, aggregated | `plots.fig_vectors` — one figure per season and group, not one per pair |
| `plotHistograms` | dropped | replaced by the quality-assurance figures |
| `selectROI` | dropped | never called; ROIs are configured |
| — | new | `quality`, `velocity`, `aggregate`, `compare`, `lake`, `report` |
