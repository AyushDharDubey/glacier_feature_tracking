# Stage 1 — `inventory`

| | |
| --- | --- |
| **Module** | `glacier_tlc/inventory.py` |
| **Command** | `python -m glacier_tlc inventory` |
| **Reads** | every `*.jpg` / `*.jpeg` (case-insensitive) in `paths.images` |
| **Writes** | `output/inventory.csv` |

## Overview

Builds the master table of photographs: the capture time from EXIF, the one image
chosen per day, and the camera-position group each image belongs to. Every later
stage selects its images from this table.

## Processing

### `read_exif_datetime(path) -> datetime | None`

1. Open the file with Pillow and call `getexif()`.
2. Look up `DateTimeOriginal` (tag 36867) in the EXIF sub-IFD (`get_ifd(0x8769)`).
3. Fall back to `DateTime` (tag 306) in the main IFD.
4. Parse with the EXIF format `"%Y:%m:%d %H:%M:%S"`.
5. Return `None` if the file is unreadable, the tag is absent or the string does not
   parse. Unreadable files are logged as a warning.

### `build_inventory(cfg) -> DataFrame`

1. **List files**: all files in `paths.images` whose suffix is in
   `inventory.extensions` (default `[.jpg, .jpeg]`), sorted by name. No files →
   `SystemExit`.
2. **Read EXIF** for each file into `file`, `datetime`.
3. **Drop** rows with no datetime (warning listing the first 10 names).
4. **Sort** by datetime; derive `date` (calendar day) and `hour` (decimal hours,
   `hour + minute/60`).
5. **Daily pick**:
   - `hour_offset = |hour − inventory.target_hour|` (default 13.0);
   - `in_hour_window = hour_offset ≤ inventory.hour_window` (default 2.0 h);
   - within each `date`, among rows with `in_hour_window`, the row with the smallest
     `hour_offset` gets `daily_pick = True`; all others `False`;
   - a day whose images all fall outside the window has **no** pick.
6. **Group**: `group = cfg.group_for_date(date).name`, or `""` when the date lies
   outside every group (the snow-burial gaps).
7. `day_index`: fractional days since the earliest datetime in the folder.

### `run(cfg)`

Calls `build_inventory`, creates `paths.output`, writes `inventory.csv` and logs the
counts: total images, daily picks, picks assigned to groups, and picks per group.

## Output — `output/inventory.csv`

One row per image with a readable EXIF time (584 rows on the Drang Drung dataset).

| Column | Type | Meaning |
| --- | --- | --- |
| `file` | str | file name (no directory) |
| `datetime` | ISO datetime | EXIF capture time |
| `date` | date | calendar day |
| `hour` | float | decimal local hour |
| `hour_offset` | float | `abs(hour − target_hour)` |
| `in_hour_window` | bool | `hour_offset ≤ hour_window` |
| `daily_pick` | bool | the chosen image of that day |
| `group` | str | `GRP1` / `GRP2` / `GRP3` / `""` |
| `day_index` | float | days since the first image |

## Configuration

```yaml
inventory:
  extensions: [.jpg, .jpeg]
  target_hour: 13.0
  hour_window: 2.0
groups:            # start/end dates decide the group column
```

## Downstream contract

`quality` keeps rows with `daily_pick == True` **and** a non-empty `group`. An image
that is not the daily pick, or that lies in a gap between groups, therefore never
reaches `quality`, `extract` or `track`, even if it is perfectly good.

## Edge cases

- Two images on the same day equally close to the target hour — `idxmin` picks the
  first in datetime order.
- Images without EXIF are dropped **before** the daily pick, so a day whose only image
  lacks EXIF has no pick.
- Time zone: EXIF times are taken as-is (camera local time); nothing converts them.
- Files are matched by suffix only; a `.JPG` that is not actually a JPEG fails at
  `Image.open` and is dropped with a warning.

## See also

- [config.md](config.md) — `group_for_date`.
- [quality.md](quality.md) — the next consumer.
