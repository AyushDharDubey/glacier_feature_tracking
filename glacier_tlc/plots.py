"""Stage 8: figures. Paper-style result figures plus QA figures."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import Config
from .extract import crop_path
from .utils import DAYS_PER_MONTH, ensure_dir, log

COLORS = {"ROI1": "#e4572e", "ROI2": "#2ca25f", "ROI3": "#3b7dd8", "ROI4": "#9467bd"}


def _c(roi):
    return COLORS.get(roi, "#555555")


def _bars(ax, w: pd.DataFrame, col: str, unc_col: str, roi: str, label=None, alpha_box=0.25):
    for r in w.itertuples(index=False):
        s, e = pd.Timestamp(r.date_start), pd.Timestamp(r.date_end)
        v, u = getattr(r, col), getattr(r, unc_col)
        if not np.isfinite(v):
            continue
        ax.plot([s, e], [v, v], color=_c(roi), lw=2.5, solid_capstyle="butt", label=label)
        label = None
        if np.isfinite(u):
            ax.fill_between([s, e], v - u, v + u, color=_c(roi), alpha=alpha_box, lw=0)


def fig_windows(cfg: Config, win: pd.DataFrame, figdir: Path, rois):
    # Fig. 3: feature velocity, one panel per ROI
    fig, axes = plt.subplots(len(rois), 1, figsize=(9, 2.4 * len(rois)), sharex=True)
    for ax, roi in zip(np.atleast_1d(axes), rois):
        _bars(ax, win[win.roi == roi], "feature_velocity_m_yr", "unc_feature_velocity_m_yr", roi, roi)
        ax.legend(loc="upper right"); ax.grid(alpha=0.3); ax.set_ylabel("m yr$^{-1}$")
    np.atleast_1d(axes)[0].set_title("Glacier feature velocity (median corrected vector magnitude) per window")
    np.atleast_1d(axes)[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%Y"))
    fig.tight_layout(); fig.savefig(figdir / "fig3_feature_velocity.png", dpi=160); plt.close(fig)

    # Fig. 5: horizontal velocity, all ROIs + references
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for roi in rois:
        _bars(ax, win[win.roi == roi], "horizontal_m_yr", "unc_horizontal_m_yr", roi, roi)
    ref = cfg.reference
    for roi, v in ref.get("its_live_m_yr", {}).items():
        if roi in rois:
            ax.axhline(v, color=_c(roi), ls=":", lw=1.2, label=f"{roi} ITS_LIVE")
    fo = ref.get("field_observation", {})
    if fo.get("velocity_m_yr"):
        ax.axhline(fo["velocity_m_yr"], color="k", ls="--", lw=1.2, label=f"Field observation ({fo.get('roi', '')})")
    ax.set_ylabel("Horizontal velocity (m yr$^{-1}$)"); ax.grid(alpha=0.3); ax.legend(ncol=2, fontsize=8)
    ax.set_title("Horizontal glacier surface velocity per window (+/- stable-region NMAD)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.tight_layout(); fig.savefig(figdir / "fig5_horizontal_velocity.png", dpi=160); plt.close(fig)

    # Fig. 6: vertical motion
    fig, axes = plt.subplots(len(rois), 1, figsize=(9, 2.4 * len(rois)), sharex=True)
    for ax, roi in zip(np.atleast_1d(axes), rois):
        _bars(ax, win[win.roi == roi], "vertical_m_month", "unc_vertical_m_month", roi, roi)
        ax.axhline(0, color="k", lw=0.6); ax.legend(loc="lower right"); ax.grid(alpha=0.3); ax.set_ylabel("m month$^{-1}$")
    np.atleast_1d(axes)[0].set_title("Vertical motion (positive up) per window")
    np.atleast_1d(axes)[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%Y"))
    fig.tight_layout(); fig.savefig(figdir / "fig6_vertical_motion.png", dpi=160); plt.close(fig)


def fig_short_term(cfg: Config, daily: pd.DataFrame, figdir: Path):
    aux = cfg.raw.get("auxiliary", {})
    era = None
    p = aux.get("era5_daily_csv")
    if p and (Path(p).exists() or (cfg.paths.images.parent / p).exists()):
        era = pd.read_csv(p if Path(p).exists() else cfg.paths.images.parent / p, parse_dates=["date"])
    for period, d in daily.groupby("period"):
        rois = sorted(d.roi.unique())
        fig, axes = plt.subplots(len(rois), 1, figsize=(9, 3.2 * len(rois)), sharex=True, squeeze=False)
        for ax, roi in zip(axes[:, 0], rois):
            s = d[d.roi == roi]
            ax.errorbar(s.date, s.value, yerr=s.unc, fmt="o", ms=4, color=_c(roi), ecolor="#bbbbbb", elinewidth=0.8, label="daily median velocity")
            ax.plot(s.date, s.trend, color=_c(roi), lw=1.5, label="moving-window trend")
            m = s[s.local_max]
            ax.plot(m.date, m.trend, "*", ms=13, color="#d62728", label="local maxima (trend)", zorder=5)
            for r in m.itertuples(index=False):
                ax.annotate(f"{r.trend:.1f}\n{pd.Timestamp(r.date):%d-%b}", (r.date, r.trend), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=7)
            ax.set_ylabel("m yr$^{-1}$"); ax.grid(alpha=0.3); ax.set_title(f"{roi}: short-term horizontal velocity, {period}")
            if era is not None and "net_radiation" in era.columns:
                ax2 = ax.twinx(); ax2.plot(era.date, era.net_radiation, ".", color="grey", ms=3, alpha=0.6); ax2.set_ylabel("ERA5 net radiation (W m$^{-2}$)")
            ax.legend(fontsize=8, loc="upper left")
        axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
        fig.tight_layout(); fig.savefig(figdir / f"fig7_short_term_{period}.png", dpi=160); plt.close(fig)


def fig_vectors(cfg: Config, pv: pd.DataFrame, figdir: Path):
    """Fig. 4-style overlays: motion vectors of a long-baseline pair on the raw crop of image B."""
    specs = cfg.plots.get("vector_overlays", [])
    if not specs:
        return
    vec_dir = cfg.paths.cache / "vectors"
    for spec in specs:
        s, e = pd.Timestamp(spec["start"]), pd.Timestamp(spec["end"]) + pd.Timedelta(days=1)
        for gname, g in cfg.groups.items():
            sel = pv[(pv.group == gname) & pv.valid & (pv.datetime_a >= s) & (pv.datetime_b < e)]
            tracked = set(sel.roi.unique())
            rois = [r for r in g.motion_rois if r.name in spec.get("rois", cfg.plots.get("rois", [r.name for r in g.motion_rois])) and r.name in tracked]
            if sel.empty:
                continue
            # pick the pair with the longest baseline that is valid for all requested ROIs
            cnt = sel.groupby(["file_a", "file_b", "days"]).roi.nunique().reset_index()
            cnt = cnt[cnt.roi >= len(rois)].sort_values("days", ascending=False)
            if cnt.empty:
                continue
            fa, fb, days = cnt.iloc[0].file_a, cnt.iloc[0].file_b, float(cnt.iloc[0].days)
            z = np.load(vec_dir / gname / f"{Path(fa).stem}__{Path(fb).stem}.npz")
            B = np.load(crop_path(cfg, gname, fb))
            srow = sel[(sel.file_a == fa) & (sel.file_b == fb)].iloc[0]
            sdx, sdy = float(srow.stable_dx_px), float(srow.stable_dy_px)
            fig, axes = plt.subplots(len(rois), 1, figsize=(10, 2.6 * len(rois)), squeeze=False)
            vmax = float(spec.get("vmax_m_month", 3.5))
            for ax, roi in zip(axes[:, 0], rois):
                img = B[f"{roi.name}_raw"]; x0, y0 = B[f"{roi.name}_rect"][:2]
                p0, vec = z[f"{roi.name}_p0"], z[f"{roi.name}_vec"] - np.array([sdx, sdy])
                nmax = int(spec.get("max_vectors", 400))  # thin for readability
                if len(vec) > nmax:
                    keep = np.random.default_rng(0).choice(len(vec), nmax, replace=False); p0, vec = p0[keep], vec[keep]
                gsd = cfg.roi_scale(roi); mag = np.hypot(vec[:, 0], vec[:, 1]) * gsd / days * DAYS_PER_MONTH
                ax.imshow(img, cmap="gray", vmin=0, vmax=255)
                q = ax.quiver(p0[:, 0] - x0, p0[:, 1] - y0, vec[:, 0], vec[:, 1], mag, cmap="jet", angles="xy", scale_units="xy",
                              scale=1.0 / float(spec.get("arrow_scale", 5.0)), width=0.003, clim=(0, vmax))
                ax.set_title(f"{roi.name}  {pd.Timestamp(srow.datetime_a):%d %b %Y} - {pd.Timestamp(srow.datetime_b):%d %b %Y}  (showing {len(vec)} vectors, arrows x{spec.get('arrow_scale', 5.0)})", fontsize=9)
                ax.set_xticks([]); ax.set_yticks([])
            fig.colorbar(q, ax=axes[:, 0].tolist(), label="feature velocity (m month$^{-1}$)", shrink=0.8)
            fig.savefig(figdir / f"fig4_vectors_{spec.get('label', spec['start'])}_{gname}.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def fig_qa(cfg: Config, pv: pd.DataFrame, q: pd.DataFrame, figdir: Path):
    # camera shift: stable-region displacement of 1-day pairs through time
    s = pv[(pv.days <= 1.5)].drop_duplicates(["file_a", "file_b"])
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax[0].plot(s.datetime_b, s.stable_dx_px, ".", ms=3, label="dx"); ax[0].plot(s.datetime_b, s.stable_dy_px, ".", ms=3, label="dy")
    ax[0].set_ylabel("stable-region shift (px / day)"); ax[0].legend(); ax[0].grid(alpha=0.3)
    ax[0].set_title("Camera motion diagnostic: median stable-region displacement of consecutive-day pairs")
    ax[1].plot(s.datetime_b, s.stable_nmad_mag_px, ".", ms=3, color="k"); ax[1].set_ylabel("stable NMAD (px)"); ax[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(figdir / "qa_camera_shift.png", dpi=150); plt.close(fig)

    # quality metrics
    if not q.empty:
        qq = q.copy(); qq["datetime"] = pd.to_datetime(qq.datetime)
        fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        for a, col in zip(ax, ["sharpness", "vis_inliers", "brightness"]):
            a.scatter(qq.datetime, qq[col], c=np.where(qq.usable, "tab:green", "tab:red"), s=8)
            a.set_ylabel(col); a.grid(alpha=0.3)
        ax[0].set_title("Image quality screening (green = usable, red = excluded)")
        fig.tight_layout(); fig.savefig(figdir / "qa_image_quality.png", dpi=150); plt.close(fig)

    # vectors per pair through time
    fig, ax = plt.subplots(figsize=(10, 3.5))
    for roi, s in pv.groupby("roi"):
        ax.plot(s.date_mid, s.n_vectors, ".", ms=2, label=roi, color=_c(roi))
    ax.set_yscale("log"); ax.set_ylabel("final vectors per pair"); ax.legend(ncol=4, fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(figdir / "qa_vectors_per_pair.png", dpi=150); plt.close(fig)

    # pair scatter: per-pair velocity vs date, coloured by baseline
    fig, axes = plt.subplots(len(pv.roi.unique()), 1, figsize=(10, 2.6 * len(pv.roi.unique())), sharex=True, squeeze=False)
    for ax, (roi, s) in zip(axes[:, 0], pv[pv.valid].groupby("roi")):
        sc = ax.scatter(s.date_mid, s.horizontal_m_yr, c=s.days, s=6, cmap="viridis", vmin=0, vmax=float(cfg.pairs.get("max_baseline_days", 35)))
        ax.set_ylabel(f"{roi}\nhorizontal m/yr"); ax.set_ylim(-40, 80); ax.grid(alpha=0.3)
    fig.colorbar(sc, ax=axes[:, 0].tolist(), label="baseline (days)")
    axes[0, 0].set_title("Per-pair horizontal velocity (all valid pairs)")
    fig.savefig(figdir / "qa_pair_velocities.png", dpi=150, bbox_inches="tight"); plt.close(fig)


def fig_lake(cfg: Config, figdir: Path):
    p = cfg.paths.output / "lake_index.csv"
    if not p.exists():
        return
    d = pd.read_csv(p, parse_dates=["datetime"])
    if d.empty:
        return
    fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    ax[0].plot(d.datetime, d.ice_fraction, ".", ms=3); ax[0].set_ylabel("ice fraction")
    ax[1].plot(d.datetime, d.red_blue, ".", ms=3, color="tab:brown"); ax[1].axhline(1, color="k", lw=0.5); ax[1].set_ylabel("R / B (turbidity proxy)")
    ax[2].plot(d.datetime, d.saturation, ".", ms=3, color="tab:cyan"); ax[2].set_ylabel("saturation")
    for a in ax: a.grid(alpha=0.3)
    ax[0].set_title("Proglacial lake colour indices from the TLC images")
    fig.tight_layout(); fig.savefig(figdir / "lake_indices.png", dpi=150); plt.close(fig)


def run(cfg: Config) -> None:
    o = cfg.paths.output
    figdir = ensure_dir(o / "figures")
    pv = pd.read_csv(o / "pairs_velocity.csv", parse_dates=["datetime_a", "datetime_b", "date_mid"])
    win = pd.read_csv(o / "velocity_windows.csv", parse_dates=["date_start", "date_end"])
    q = pd.read_csv(o / "quality.csv") if (o / "quality.csv").exists() else pd.DataFrame()
    rois = cfg.plots.get("rois") or sorted(win.roi.unique())
    if not win.empty:
        fig_windows(cfg, win, figdir, rois)
    if (o / "velocity_daily.csv").exists():
        daily = pd.read_csv(o / "velocity_daily.csv", parse_dates=["date"])
        daily = daily[daily.roi.isin(rois)]
        if not daily.empty:
            fig_short_term(cfg, daily, figdir)
    fig_vectors(cfg, pv, figdir)
    fig_qa(cfg, pv, q, figdir)
    fig_lake(cfg, figdir)
    log.info("plots -> %s", figdir)
