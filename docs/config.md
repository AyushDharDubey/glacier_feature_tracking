# Configuration

| | |
| --- | --- |
| **Module** | `glacier_tlc/config.py` |
| **File** | `config.yaml` |
| **Used by** | every stage (`cfg` is the first argument of every `run()`) |

## Overview

`config.py` turns `config.yaml` into typed Python objects, validates the parts every
stage relies on, and provides the derived quantities that more than one stage needs:
the ground sampling distance (GSD) of an ROI, the camera group a date belongs to, and
the list of aggregation windows. No analysis constant is hard-coded in the source;
anything tunable is a key in the YAML file.

## Data model

```text
Config
 ├─ raw: dict               the YAML as loaded (section accessors read from here)
 ├─ paths: Paths            images / cache / output  (absolute Path objects)
 ├─ camera: Camera          sensor and lens parameters; gsd_m_per_px()
 └─ groups: {name: Group}   camera-position periods
       ├─ start, end: date
       ├─ rois: {name: Roi} rect, distance_m, scale_m_per_px, role, label
       ├─ reference_image   optional file name for the quality check
       └─ flow_sign_x       +1 / -1 / "auto"
```

| Class | Fields | Notes |
| --- | --- | --- |
| `Paths` | `images`, `cache`, `output` | relative paths are resolved against the config file's directory |
| `Camera` | `model`, `sensor_width_mm`, `sensor_height_mm`, `image_width_px`, `image_height_px`, `focal_length_mm` | `pixel_pitch_mm = sensor_width / image_width`; `gsd_m_per_px(D) = D · pixel_pitch / focal_length` |
| `Roi` | `name`, `rect (x, y, w, h)`, `distance_m`, `scale_m_per_px`, `role`, `label` | `role` is `"stable"` or `"motion"` |
| `Group` | `name`, `start`, `end`, `rois`, `reference_image`, `flow_sign_x` | `.stable` → the one stable ROI; `.motion_rois` → the others |
| `Window` | `label`, `start`, `end` | an aggregation window (inclusive dates) |

## Loading — `load_config(path)`

1. `yaml.safe_load` the file; remember its parent directory as `base`.
2. **Paths**: `paths.images` is required; `cache` defaults to `.cache` and `output` to
   `output`. Each is made absolute relative to `base` unless already absolute.
3. **Camera**: `Camera(**raw["camera"])` — every key in the YAML block must match a
   dataclass field exactly.
4. **Groups** — for every entry under `groups:`:
   - for every ROI under `rois:`
     - a bare list `[x, y, w, h]` is accepted as shorthand for `{rect: [...]}`;
     - the rect must have exactly four integers, otherwise `ValueError`;
     - `role` defaults to `"stable"` if the ROI name starts with `stable`
       (case-insensitive), otherwise `"motion"`; an explicit `role:` wins;
     - `distance_m` is taken from the ROI entry, falling back to the top-level
       `distances_m:` map by ROI name; if neither exists **and** no `scale_m_per_px`
       is given → `ValueError`;
     - `label` defaults to the ROI name;
   - exactly one ROI in the group must have `role: stable`, otherwise `ValueError`;
   - `flow_sign_x` comes from the group, else from `velocity.flow_sign_x`, else `"auto"`.
5. Return `Config(raw, paths, camera, groups)`.

Section accessors (`cfg.inventory`, `cfg.quality`, `cfg.enhancement`, `cfg.tracking`,
`cfg.pairs`, `cfg.velocity`, `cfg.aggregation`, `cfg.short_term`, `cfg.reference`,
`cfg.plots`, …) return the raw dictionary of that section, or `{}` if it is absent.
Individual stages apply their own defaults with `.get()`.

Dates in the YAML may be written as ISO strings or as bare YAML dates; `_date()`
normalises both (and `datetime` values) to `datetime.date`.

## Derived quantities

### `cfg.roi_scale(roi)` — metres per pixel

```text
scale_m_per_px if set on the ROI, otherwise camera.gsd_m_per_px(roi.distance_m)
```

With the shipped camera (22.3 mm sensor, 6000 px, 24 mm lens): 900 m → 0.1394 m/px,
700 m → 0.1084 m/px, 450 m → 0.0697 m/px. Used by `velocity`, `plots` and `report`.

### `cfg.group_for_date(d)`

Returns the first `Group` whose `start ≤ d ≤ end`, or `None`. Used by `inventory` to
label each image. Dates between groups (the snow-burial gaps) get `None`, and those
images are excluded from every later stage.

### `cfg.windows()` — aggregation windows

- `aggregation.mode: custom` → one `Window` per entry in `aggregation.custom`
  (`label`, `start`, `end`).
- `aggregation.mode: monthly` (default) → for each group, one window per calendar
  month, clipped to the group's `[start, end]`. Labels are `YYYY-MM`. If a month is
  already present from an earlier group (a camera move mid-month), the earlier window
  is relabelled `YYYY-MMa` and the new one `YYYY-MMb` — for example `2024-08a`
  (GRP2, 1–18 Aug) and `2024-08b` (GRP3, 19–31 Aug).

## `config.yaml` reference

| Section | Read by | Key parameters |
| --- | --- | --- |
| `paths` | all | `images`, `cache`, `output` |
| `camera` | `velocity`, `extract` (size check), `report` | sensor and lens parameters |
| `distances_m` | `load_config` | default camera-to-target distance per ROI name |
| `inventory` | `inventory` | `extensions`, `target_hour`, `hour_window` |
| `groups` | all | date ranges, ROI rectangles, optional `reference_image`, `flow_sign_x` |
| `quality` | `quality` | `static_fraction`, `neighbour_images`, `thresholds.*`, `exclude_list`, `include_list` |
| `enhancement` | `extract` (via `utils.enhance`) | `method`, `clip_limit_matlab` / `clip_limit_opencv`, `n_bins`, `tiles` |
| `tracking` | `extract` (`pad_px`), `track`, `velocity` (`min_vectors` fallback) | `rois`, `pad_px`, `min_vectors`, `sift.*`, `klt.*`, `ransac.*`, `direction_filter.*` |
| `pairs` | `track` | `min_baseline_days`, `max_baseline_days` |
| `velocity` | `velocity` | `min_vectors`, `min_vectors_stable`, `flow_sign_x`, `flow_sign_min_days` |
| `aggregation` | `aggregate`, `config.windows()` | `mode`, `stat`, `min_days`, `min_pairs`, `annual_periods`, `seasons`, `season_comparisons`, `interannual` |
| `short_term` | `aggregate` | `quantity`, `max_baseline_days`, `smoothing_window_days`, `periods` |
| `auxiliary` | `plots` | `era5_daily_csv` |
| `plots` | `plots` | `rois`, `vector_overlays` |
| `reference` | `plots` | optional; `its_live_m_yr`, `field_observation` draw reference lines on Fig. 5 |

Per-group `lake_rect` entries from earlier versions are ignored.

## Failure modes

| Symptom | Cause |
| --- | --- |
| `KeyError: 'paths'` / `'camera'` / `'groups'` | a required top-level section is missing |
| `TypeError: Camera.__init__() got an unexpected keyword` | extra or misspelt key under `camera:` |
| `ValueError: GRPx/ROIy: rect must be [x, y, w, h]` | a rectangle with ≠ 4 elements |
| `ValueError: GRPx/ROIy: need distance_m (or scale_m_per_px)` | ROI name not in `distances_m` and no per-ROI distance |
| `ValueError: group GRPx: exactly one ROI must have role 'stable'` | zero or several stable ROIs |
| `KeyError` later in `aggregate` | `mode: custom` without an `aggregation.custom` list |

## Adding a camera period

Add a `groups:` entry with `start`, `end`, one `stable` ROI and the motion ROIs in the
new camera position's coordinates. Nothing else needs to change: `inventory` labels
the dates, `windows()` produces the months, and every downstream stage iterates over
`cfg.groups`.

## See also

- [velocity.md](velocity.md) — how `roi_scale` and `flow_sign_x` are consumed.
- [aggregate.md](aggregate.md) — how `windows()` is consumed.
