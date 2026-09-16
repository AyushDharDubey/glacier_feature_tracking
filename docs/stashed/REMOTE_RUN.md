# Running the uncapped tracking stage on a remote compute server

The baseline cap (`pairs.max_baseline_days`) that limited pair generation to a 20-day
window was a compute-saving deviation from both the paper and the MATLAB prototype,
neither of which bounds it. It is now removed by default (`config.yaml` sets
`max_baseline_days: null`), which restores the true nC2 combination the paper's Figure 2
and the MATLAB script's `nchoosek(1:numImages, 2)` both use.

This is the sizing and execution guide for running that full combination on a server
instead of a laptop.

## What changes

| | 20-day cap (previous default) | uncapped (current default) |
|---|---|---|
| pairs (stable + ROI1–3) | 7,147 | **28,546** |
| longest baseline tracked | 20 days | up to 188 days (GRP3's full span) |
| `.cache/vectors/` cache | 414 MB | ~1.6 GB (projected, linear in pair count) |
| `.cache/crops/` cache | 346 MB | 346 MB (unchanged — one crop set per image, not per pair) |

Nothing else in the pipeline changes: `velocity`, `aggregate`, `compare`, `plots` and
`report` all run in seconds regardless of pair count, and every stage before `track`
(`inventory`, `quality`, `extract`) is already done and cached.

## Time estimate

Measured throughput on this machine was 7,147 pairs in 988 s with 4 worker processes
(≈7.2 pairs/sec, CPU-bound). The tracking stage parallelises per-pair with no
inter-worker communication, so it scales close to linearly with core count up to the
point I/O on `.cache/crops/` becomes the bottleneck (unlikely below ~64 workers given the
crops total 346 MB and fit in page cache after the first pass).

| workers | full run (28,546 pairs) | reusing this machine's cache, new pairs only (21,399) |
|---|---|---|
| 4 | ~66 min | ~49 min |
| 8 | ~33 min | ~25 min |
| 16 | ~16 min | ~12 min |
| 32 | ~8 min | ~6 min |
| 48 | ~6 min | ~4 min |

Use `-j <workers>` to set the count; default is `CPUs − 1`.

## Two ways to run it

### A. Fresh checkout on the server (simplest)

```bash
git clone <this repo> && cd glacier_tracking
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# copy input/ (the 584 JPEGs) onto the server, or re-extract from the zip
python -m glacier_tlc all -j <workers>          # runs every stage, uncapped by default
```

This recomputes everything, including `inventory`, `quality` and `extract`, which
together take under 3 minutes and give a clean audit trail on the server.

### B. Carry over this machine's cache (saves the 7,147 already-tracked pairs)

The `track` stage checks for a cached `.npz` per pair before doing any work, so copying
`.cache/` over lets the server pick up exactly where this machine left off — only the
21,399 pairs beyond the old 20-day cap need computing.

```bash
# from this machine
rsync -avz output/ .cache/ input/ user@server:/path/to/glacier_tracking/

# on the server, after cloning the repo and installing requirements.txt into the same paths
python -m glacier_tlc track -j <workers>         # reuses cached pairs, computes the rest
python -m glacier_tlc velocity
python -m glacier_tlc aggregate
python -m glacier_tlc compare
python -m glacier_tlc lake       # optional
python -m glacier_tlc plots
python -m glacier_tlc report
```

Either way, `.cache/` and `output/` are reproducible and disposable — if anything looks
wrong, delete and re-run rather than trying to patch a partial result by hand.

## After the run

Re-check the things that motivated the discussion that led here: `fig3_feature_velocity.png`
and `fig5_horizontal_velocity.png` should show visibly tighter shaded bands, since the
long-baseline pairs the cap had excluded are exactly the ones with the lowest velocity
noise (documented in `docs/PIPELINE.md`, Section 9, "Windows"). Compare
`velocity_windows.csv`'s `spread_horizontal_m_yr` column before and after — it should
fall by roughly half in most windows, based on the 14–20-day-only subsample tested on
this machine.

## Reverting to a capped run

To go back to a lighter, faster run — for iterating on a parameter before committing to
the full recompute — set `pairs.max_baseline_days` back to a number in `config.yaml`
(20 was used here). Nothing needs to be deleted: the resumable cache serves whichever
subset of pairs the current cap asks for.
