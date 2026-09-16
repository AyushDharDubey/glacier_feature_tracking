# Stage 8 — `report`

| | |
| --- | --- |
| **Module** | `glacier_tlc/report.py` |
| **Command** | `python -m glacier_tlc report` |
| **Reads** | every CSV in `output/` that exists, `output/figures/` |
| **Writes** | `output/report.md` |

## Overview

Assembles a single Markdown summary of the run from the CSVs already on disk. It
computes nothing new beyond counts; every table is a rounded projection of an
existing file, so the report is a convenience view, not a source of truth.

## Processing — `run(cfg)`

Each input is read with a helper that returns an empty DataFrame when the file is
missing, so the report degrades gracefully after a partial run. `_md(df, cols, nd)`
renders a DataFrame as a Markdown table (`to_markdown`, which requires `tabulate`),
rounding float columns to `nd` decimals; an empty frame renders as `_no data_`.

Sections, in order:

| # | Heading | Source | Content |
| --- | --- | --- | --- |
| — | title and method line | — | paper citation |
| 1 | Data | `inventory.csv`, `quality.csv` | image count and daily picks; usable / total per group; exclusion-reason counts from the `flags` column (split on `;`, counted over rejected images only) |
| 2 | Camera groups and scaling | `cfg.groups`, `cfg.roi_scale` | table: group, period, ROI, role, rect, distance, GSD (4 decimals); then pair-row counts per group, valid / total, and `flow_sign_x` per group from `pairs_velocity.csv` |
| 3 | Weekly-to-monthly velocities | `velocity_windows.csv` | `window, roi, n_pairs, mean_baseline_days`, feature / horizontal / vertical values and `unc_*` |
| 4 | Annual and seasonal summaries | `velocity_annual.csv`, `velocity_seasonal.csv`, `velocity_seasonal_change.csv`, `velocity_interannual.csv` | window-mean columns and `unc_horizontal_m_yr`; seasonal change; interannual |
| 5 | Short-term maxima | `velocity_local_maxima.csv` | the whole file |
| 6 | Comparison with GNSS and ITS_LIVE | `comparison_field_itslive.csv` | the whole file, 2 decimals; renders `_no data_` unless the file exists (see below) |
| 7 | Figures | `output/figures/*.png` | a bullet list of file names |

## Configuration

None of its own. It uses `cfg.groups` and `cfg.paths.output`.

## Behaviour to be aware of

- The report is fully regenerated on each run; edit the config and re-run rather than
  editing `report.md` by hand.
- `tabulate` must be installed (it is in `requirements.txt`); without it pandas'
  `to_markdown` raises `ImportError`.
- Section 6 was fed by the former `compare` stage, which has been removed. Its
  input file is no longer produced, so the section shows `_no data_` unless a file
  from an earlier run is still present in `output/`.
- `quality.csv` rows with an empty `group` are dropped before counting. They cannot
  occur with the current `quality` stage, which only processes in-group picks, but
  the guard remains.

## See also

- [aggregate.md](aggregate.md), [plots.md](plots.md) — the producers of what it lists.
