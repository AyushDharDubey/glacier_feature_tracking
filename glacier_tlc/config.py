"""Configuration loading and validation (YAML -> dataclasses)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Paths:
    images: Path
    cache: Path
    output: Path


@dataclass
class Camera:
    model: str
    sensor_width_mm: float
    sensor_height_mm: float
    image_width_px: int
    image_height_px: int
    focal_length_mm: float

    @property
    def pixel_pitch_mm(self) -> float:
        return self.sensor_width_mm / self.image_width_px

    def gsd_m_per_px(self, distance_m: float) -> float:
        """Ground sampling distance (m per pixel) for an object at `distance_m`
        along the optical axis: GSD = D * pixel_pitch / focal_length."""
        return distance_m * self.pixel_pitch_mm / self.focal_length_mm


@dataclass
class Roi:
    name: str
    rect: tuple[int, int, int, int]  # x, y, w, h (full-resolution pixels)
    distance_m: float
    scale_m_per_px: float | None = None  # explicit override of the GSD
    role: str = "motion"  # "motion" | "stable"
    label: str = ""


@dataclass
class Group:
    name: str
    start: dt.date
    end: dt.date
    rois: dict[str, Roi]
    reference_image: str | None = None
    flow_sign_x: int | str = "auto"  # +1 / -1 / "auto"

    @property
    def stable(self) -> Roi:
        for r in self.rois.values():
            if r.role == "stable":
                return r
        raise KeyError(f"group {self.name}: no ROI with role 'stable'")

    @property
    def motion_rois(self) -> list[Roi]:
        return [r for r in self.rois.values() if r.role == "motion"]


@dataclass
class Window:
    label: str
    start: dt.date
    end: dt.date


@dataclass
class Config:
    raw: dict[str, Any]
    paths: Paths
    camera: Camera
    groups: dict[str, Group]

    # convenience accessors into raw sections (validated lightly)
    @property
    def inventory(self) -> dict:
        return self.raw.get("inventory", {})

    @property
    def quality(self) -> dict:
        return self.raw.get("quality", {})

    @property
    def enhancement(self) -> dict:
        return self.raw.get("enhancement", {})

    @property
    def tracking(self) -> dict:
        return self.raw.get("tracking", {})

    @property
    def pairs(self) -> dict:
        return self.raw.get("pairs", {})

    @property
    def velocity(self) -> dict:
        return self.raw.get("velocity", {})

    @property
    def aggregation(self) -> dict:
        return self.raw.get("aggregation", {})

    @property
    def short_term(self) -> dict:
        return self.raw.get("short_term", {})

    @property
    def reference(self) -> dict:
        return self.raw.get("reference", {})

    @property
    def lake(self) -> dict:
        return self.raw.get("lake", {})

    @property
    def plots(self) -> dict:
        return self.raw.get("plots", {})

    def windows(self) -> list[Window]:
        """Aggregation windows. mode: 'monthly' (calendar months spanning the
        groups) or 'custom' (explicit list)."""
        agg = self.aggregation
        mode = agg.get("mode", "monthly")
        if mode == "custom":
            return [Window(w["label"], _date(w["start"]), _date(w["end"])) for w in agg["custom"]]
        out: list[Window] = []
        for g in self.groups.values():
            d = dt.date(g.start.year, g.start.month, 1)
            while d <= g.end:
                nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
                s, e = max(d, g.start), min(nxt - dt.timedelta(days=1), g.end)
                label = d.strftime("%Y-%m")
                if any(w.label == label for w in out):  # month split by a camera move
                    out[-1].label = f"{out[-1].label}a"; label = f"{label}b"
                out.append(Window(label, s, e))
                d = nxt
        return out

    def group_for_date(self, d: dt.date | dt.datetime) -> Group | None:
        if isinstance(d, dt.datetime):
            d = d.date()
        for g in self.groups.values():
            if g.start <= d <= g.end:
                return g
        return None

    def roi_scale(self, roi: Roi) -> float:
        return roi.scale_m_per_px if roi.scale_m_per_px else self.camera.gsd_m_per_px(roi.distance_m)


def _date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def load_config(path: str | Path) -> Config:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    base = path.parent

    def p(x):
        x = Path(x)
        return x if x.is_absolute() else (base / x)

    paths = Paths(p(raw["paths"]["images"]), p(raw["paths"].get("cache", ".cache")), p(raw["paths"].get("output", "output")))
    cam = Camera(**raw["camera"])
    dist_defaults = raw.get("distances_m", {})
    groups: dict[str, Group] = {}
    for gname, g in raw["groups"].items():
        rois: dict[str, Roi] = {}
        for rname, r in g["rois"].items():
            if isinstance(r, list):
                r = {"rect": r}
            rect = tuple(int(v) for v in r["rect"])
            if len(rect) != 4:
                raise ValueError(f"{gname}/{rname}: rect must be [x, y, w, h]")
            role = r.get("role", "stable" if rname.lower().startswith("stable") else "motion")
            dist = r.get("distance_m", dist_defaults.get(rname))
            if dist is None and not r.get("scale_m_per_px"):
                raise ValueError(f"{gname}/{rname}: need distance_m (or scale_m_per_px)")
            rois[rname] = Roi(rname, rect, float(dist or 0), r.get("scale_m_per_px"), role, r.get("label", rname))
        if sum(r.role == "stable" for r in rois.values()) != 1:
            raise ValueError(f"group {gname}: exactly one ROI must have role 'stable'")
        groups[gname] = Group(
            gname, _date(g["start"]), _date(g["end"]), rois, g.get("reference_image"),
            g.get("flow_sign_x", raw.get("velocity", {}).get("flow_sign_x", "auto")),
        )
    return Config(raw, paths, cam, groups)
