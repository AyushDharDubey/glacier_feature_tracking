# Shared utilities

| | |
| --- | --- |
| **Module** | `glacier_tlc/utils/__init__.py` |
| **Used by** | every module |

## Overview

Small helpers with no pipeline state. They are documented here because their exact
definitions determine the numbers in the output files. The `utils` package also
contains the two algorithmic library modules, [`enhance`](enhance.md) and
[`tracking`](tracking.md).

## Logging — `log`, `setup_logging(verbose)`

`log = logging.getLogger("glacier_tlc")` is the one logger used throughout.
`setup_logging` is called once by the CLI: `basicConfig` at INFO (or DEBUG with `-v`)
with the format `HH:MM:SS LEVEL glacier_tlc: message`. Worker processes started by
`ProcessPoolExecutor` inherit nothing from this and do not log.

## `ensure_dir(p) -> Path`

`mkdir(parents=True, exist_ok=True)` and return the `Path`. Used for `output/`,
`.cache/crops/`, `.cache/vectors/` and `output/figures/`.

## `nmad(x, axis=None) -> float`

Normalised median absolute deviation:

```text
NMAD(x) = 1.4826 · median(|x − median(x)|)
```

NaN-aware (`nanmedian`); returns `nan` for an empty input. The constant 1.4826 makes
NMAD equal to the standard deviation for normally distributed data. It is **the**
uncertainty statistic of the pipeline, applied to stable-region displacements per pair
(`tracking.vector_stats`), to corrected magnitudes within an ROI (`velocity`), and to
per-pair velocities within a window (`aggregate`, the `spread_*` columns).

With `axis` given, the reduction is along that axis and an array is returned; every
call in the pipeline uses the scalar form.

## `circ_diff_deg(a, b)`

Smallest absolute angular difference between two angles (or arrays) in degrees:

```text
d = |a − b| mod 360;   return d if d ≤ 180 else 360 − d
```

The result lies in `[0, 180]`. Used by the direction filter in `Tracker.track` and
for the direction-spread statistics in `vector_stats`. It makes the ±30° window behave
correctly for directions near ±180° (image −x, which is the actual flow direction at
Drang Drung).

## `mean_below_p95(x) -> float`

Mean of the values **strictly below** the 95th percentile (NaNs removed first). If no
value lies strictly below it (for example when all values are identical), the plain
mean is returned. Reproduces the MATLAB prototype's "Mean Magnitude (95%)" column and
is stored as `mag_mean95` in `pairs_raw.csv`. It is carried for parity with the
prototype and is not used by any later stage.

## Time constants

```python
DAYS_PER_YEAR  = 365.25
DAYS_PER_MONTH = 365.25 / 12   # 30.4375
```

Used by `velocity` (px/day → m/yr and m/month) and `plots` (vector-overlay colour
scale).

## See also

- [tracking.md](tracking.md) — where `nmad`, `circ_diff_deg` and `mean_below_p95`
  feed the per-pair statistics.
- [velocity.md](velocity.md) — the uncertainty chain built on `nmad`.
