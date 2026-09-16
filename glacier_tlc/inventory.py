"""Stage 1: image inventory.

Reads EXIF DateTimeOriginal of every JPEG, keeps one image per day closest to the
target local hour (the paper uses the ~13:00 image of each day), and assigns each
image to a camera-position group (the paper processes three groups
independently because the camera moved slightly at every data retrieval).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from PIL import Image

from .config import Config
from .utils import ensure_dir, log

EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306


def read_exif_datetime(path: Path) -> dt.datetime | None:
    """EXIF capture time. Returns None when missing (the MATLAB script silently
    substituted the current date here, which corrupts the time baseline; the
    paper's method needs true capture times, so we refuse instead)."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            val = None
            try:
                val = exif.get_ifd(0x8769).get(EXIF_DATETIME_ORIGINAL)
            except Exception:
                pass
            val = val or exif.get(EXIF_DATETIME)
    except Exception as e:  # unreadable file
        log.warning("cannot read %s: %s", path, e)
        return None
    if not val:
        return None
    try:
        return dt.datetime.strptime(str(val).strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def build_inventory(cfg: Config) -> pd.DataFrame:
    inv_cfg = cfg.inventory
    exts = tuple(e.lower() for e in inv_cfg.get("extensions", [".jpg", ".jpeg"]))
    files = sorted(p for p in cfg.paths.images.iterdir() if p.suffix.lower() in exts)
    if not files:
        raise SystemExit(f"no images found in {cfg.paths.images}")
    rows = []
    for p in files:
        t = read_exif_datetime(p)
        rows.append({"file": p.name, "datetime": t})
    df = pd.DataFrame(rows)
    n_missing = int(df["datetime"].isna().sum())
    if n_missing:
        log.warning("%d images without EXIF time are dropped: %s", n_missing, ", ".join(df.loc[df.datetime.isna(), "file"].head(10)))
        df = df.dropna(subset=["datetime"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour + df["datetime"].dt.minute / 60.0

    # one image per day, closest to the target hour and within the window
    target = float(inv_cfg.get("target_hour", 13.0))
    half = float(inv_cfg.get("hour_window", 2.0))
    df["hour_offset"] = (df["hour"] - target).abs()
    df["in_hour_window"] = df["hour_offset"] <= half
    df["daily_pick"] = False
    for _, idx in df[df.in_hour_window].groupby("date").groups.items():
        best = df.loc[idx, "hour_offset"].idxmin()
        df.loc[best, "daily_pick"] = True

    # group assignment
    df["group"] = [g.name if (g := cfg.group_for_date(d)) else "" for d in df["date"]]
    df["day_index"] = (df["datetime"] - df["datetime"].min()).dt.total_seconds() / 86400.0
    return df


def run(cfg: Config) -> pd.DataFrame:
    df = build_inventory(cfg)
    ensure_dir(cfg.paths.output)
    out = cfg.paths.output / "inventory.csv"
    df.to_csv(out, index=False)
    n_pick = int(df.daily_pick.sum())
    log.info("inventory: %d images, %d daily picks, %d assigned to groups (%s) -> %s",
             len(df), n_pick, int((df.daily_pick & (df.group != "")).sum()),
             ", ".join(f"{g}={int(((df.group == g) & df.daily_pick).sum())}" for g in cfg.groups), out)
    return df
