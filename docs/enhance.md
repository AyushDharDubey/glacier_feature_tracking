# Image enhancement and cropping — `utils.enhance`

| | |
| --- | --- |
| **Module** | `glacier_tlc/utils/enhance.py` |
| **Type** | library module (no CLI stage) |
| **Used by** | `extract` (cropping and enhancement of every ROI); `tests/` (enhancer for the synthetic and parity tests) |

## Overview

Three small, pure functions: build the enhancement function selected in
`config.yaml`, expand an ROI rectangle by a margin, and slice a crop out of an image.
They are kept separate from `extract` so that the tests and the MATLAB parity check
can apply exactly the same enhancement to an arbitrary array.

## `matlab_clip_to_opencv(clip_limit_matlab, n_bins=256) -> float`

Converts a MATLAB `adapthisteq` `ClipLimit` into an OpenCV `createCLAHE` `clipLimit`:

```text
c_cv = 1 + c_m · (n_bins − 1)
```

Derivation (N = pixels per tile): MATLAB clips each tile histogram at
`ceil(N/bins) + c_m·(N − ceil(N/bins))`, OpenCV at `c_cv·N/bins`; equating the two
gives the formula above. With `c_m = 0.01` and `bins = 256`, `c_cv = 3.55`.

## `make_enhancer(cfg_enh) -> callable(gray) -> gray`

Returns a function `uint8 grey → uint8 grey` according to `cfg_enh["method"]`:

| `method` | Returned function |
| --- | --- |
| `clahe` (default), `adapthisteq` | `cv2.createCLAHE(clipLimit, tileGridSize=tiles).apply`. `clipLimit` is `clip_limit_opencv` if that key exists, otherwise `matlab_clip_to_opencv(clip_limit_matlab, n_bins)`. `tiles` defaults to `[8, 8]`. |
| `none`, `nofilter` | identity |
| `canny` | `cv2.Canny(gray, canny_low, canny_high)` (defaults 50 / 150); pixels on an edge keep their grey value, all others become 0 |
| anything else | `ValueError` |

The CLAHE object is created once per `make_enhancer` call and captured by the
closure; `extract` calls `make_enhancer` once per image task in the worker, which is
cheap.

## `padded_rect(rect, pad, width, height) -> (x0, y0, w, h)`

Expands `[x, y, w, h]` by `pad` on every side and clips to `[0, width) × [0, height)`.
The result is the **padded crop rectangle** stored as `<roi>_rect` in the crop cache.
Because of the clipping, a crop touching the image border has less than `pad` margin
on that side; the ROI's position *inside* the crop is recovered downstream as
`(rect.x − x0, rect.y − y0)`, which stays correct in that case.

## `crop(img, rect) -> ndarray`

`img[y:y+h, x:x+w]` — a NumPy view. `extract` wraps it in `np.ascontiguousarray`
before saving.

## Configuration

```yaml
enhancement:
  method: clahe            # clahe | none | canny
  clip_limit_matlab: 0.01  # → OpenCV 3.55
  # clip_limit_opencv: 3.55   # alternative: give the OpenCV value directly
  n_bins: 256
  tiles: [8, 8]
  # canny_low: 50, canny_high: 150   # only for method: canny
tracking:
  pad_px: 40               # the margin used by padded_rect (read by extract)
```

## Notes

- Enhancement is applied to the **padded crop**, not to the whole image, so the CLAHE
  tiles are laid over the crop (for example 8 × 8 tiles over a ~730 × 160 px crop).
  This matches the MATLAB prototype, which also called `adapthisteq` on the crop.
- Both raw and enhanced crops are cached; only the enhanced one is tracked.
- Changing any `enhancement` key requires deleting `.cache/crops/` **and**
  `.cache/vectors/` — `extract` skips existing crop files and `track` reuses existing
  vector files; neither checks parameters.

## See also

- [extract.md](extract.md) — the caller.
- [tracking.md](tracking.md) — consumes the enhanced crops.
