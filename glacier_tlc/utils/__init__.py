from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

log = logging.getLogger("glacier_tlc")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def ensure_dir(p: str | os.PathLike) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def nmad(x, axis=None) -> float:
    """Normalised median absolute deviation (Hoehle & Hoehle 2009):
    1.4826 * median(|x - median(x)|). NaN-aware."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return float("nan")
    med = np.nanmedian(x, axis=axis, keepdims=axis is not None)
    return float(1.4826 * np.nanmedian(np.abs(x - med), axis=axis)) if axis is None else 1.4826 * np.nanmedian(np.abs(x - med), axis=axis)


def circ_diff_deg(a, b):
    """Smallest absolute angular difference in degrees, wrapped to [0, 180]."""
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) % 360.0
    return np.where(d > 180.0, 360.0 - d, d)


def mean_below_p95(x) -> float:
    """MATLAB script's 'Mean Magnitude (95%)': mean of values strictly below the 95th percentile."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return float("nan")
    p95 = np.percentile(x, 95)
    sel = x[x < p95]
    return float(sel.mean()) if sel.size else float(x.mean())


DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = 365.25 / 12.0
