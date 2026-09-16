# Stage 3 — `extract`

| | |
| --- | --- |
| **Module** | `glacier_tlc/extract.py` |
| **Command** | `python -m glacier_tlc extract [-j N]` |
| **Reads** | `output/images_used.csv`, the full-resolution images |
| **Writes** | `.cache/crops/<group>/<image stem>.npz` |

## Overview

Decodes each usable 24-megapixel JPEG exactly **once**, cuts out every ROI of the
image's group with a margin, enhances each crop and stores the result. All tracking
then runs on these small cached arrays. This is what makes the pair stage cheap:
402 full-resolution decodes instead of two per pair.

## Processing

### `run(cfg, workers)`

1. Load `images_used.csv`.
2. `pad = tracking.pad_px` (default 40); `size = (camera.image_width_px,
   camera.image_height_px)`.
3. For every group and every usable image of that group, build a task
   `(image path, crop path, {roi name: rect}, pad, enhancement cfg, size)`.
   **All** ROIs of the group are extracted, including the stable region and any ROI
   not listed in `tracking.rois` — that key only restricts what `track` tracks.
4. Create `.cache/crops/`; `workers` defaults to `CPUs − 1`.
5. Map `_extract_one` over the tasks in a `ProcessPoolExecutor` (chunksize 2); count
   statuses, warn on anything other than `ok` / `cached`, and log progress every
   100 images.

### `_extract_one(args)` — per image, in a worker

1. If the crop file already exists → return `"cached"` **without reading the image**.
2. `cv2.imread(..., IMREAD_GRAYSCALE)`; unreadable → `"unreadable"`.
3. If the decoded size differs from `camera.image_*_px` → `"size_mismatch WxH"` and
   no crop is written. ROI rectangles are in full-resolution coordinates; a resized
   image would silently misplace them.
4. `enhance = make_enhancer(enhancement cfg)`.
5. For every ROI: `prect = padded_rect(rect, pad, w, h)`; `raw = crop(img, prect)`;
   store `raw`, `enhance(raw)` and `prect`.
6. `np.savez_compressed` to the crop path; return `"ok"`.

### `crop_path(cfg, group, file) -> Path`

`paths.cache / "crops" / group / (stem + ".npz")`. Imported by `track` and `plots`
so that all three modules agree on the location.

## Cache file layout

`.cache/crops/<group>/<image stem>.npz`, with three arrays per ROI of the group:

| Key | dtype / shape | Content |
| --- | --- | --- |
| `<roi>_raw` | uint8, (h + 2·pad, w + 2·pad) | grey padded crop (used for figure overlays) |
| `<roi>_enh` | uint8, same | enhanced padded crop (input to tracking) |
| `<roi>_rect` | int32, (4,) | `[x0, y0, w, h]` of the padded crop in full-resolution coordinates |

Example keys on the Drang Drung dataset: `stable_raw, stable_enh, stable_rect,
ROI1_raw, …, ROI4_rect`. The cache totals ≈ 346 MB for 402 images × 5 ROIs.

## Configuration

```yaml
paths: {images, cache}
camera: {image_width_px: 6000, image_height_px: 4000}   # size check
tracking: {pad_px: 40}
enhancement: {...}                                        # see enhance.md
groups: GRPx.rois.*.rect
```

## Cache invalidation

`_extract_one` returns `"cached"` on the mere existence of the file. After changing
**any** of the ROI rectangles, `pad_px`, the `enhancement` section, or the image
files themselves, delete `.cache/crops/` (and `.cache/vectors/`, which derives from
it). Adding an ROI to a group also requires deletion, because an existing crop file
lacks the new keys and `track` will raise `KeyError` on `<newroi>_rect`.

Adding *images* (for example after editing `include_images.txt`) needs no deletion:
only the missing crop files are computed.

## Failure modes

| Status / error | Meaning |
| --- | --- |
| `unreadable` warning | `cv2.imread` returned `None` (corrupt file) |
| `size_mismatch WxH` warning | image is not 6000 × 4000; no crop written, and `track` will later fail to load this image's crops |
| `FileNotFoundError: images_used.csv` | `quality` has not run |

Images that end with a warning are absent from the cache; `track` then reports
`load error` for every pair involving them (see [track.md](track.md)).

## See also

- [enhance.md](enhance.md) — `make_enhancer`, `padded_rect`, `crop`.
- [track.md](track.md) — consumer of the `_enh` and `_rect` arrays.
- [plots.md](plots.md) — consumer of the `_raw` arrays for the Fig. 4 overlays.
