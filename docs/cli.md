# Command-line interface

| | |
| --- | --- |
| **Modules** | `glacier_tlc/__main__.py`, `glacier_tlc/__init__.py` |
| **Usage** | `python -m glacier_tlc <stage> [options]` |

## Overview

`__main__.py` is the single entry point of the pipeline. It parses the command line,
loads and validates the configuration, and runs one stage — or every stage in order —
by importing the matching module and calling its `run()` function. It contains no
analysis logic.

The package docstring in `__init__.py` is the `--help` text; it lists every stage
with a one-line summary.

## Stages

```python
STAGES = ["inventory", "quality", "extract", "track", "velocity",
          "aggregate", "plots", "report"]
```

`all` runs the stages in exactly this order. The order matters because each stage
reads the files written by the previous ones (see the data-flow diagram in the
[README](../README.md#data-flow)).

## Options

| Option | Applies to | Meaning | Default |
| --- | --- | --- | --- |
| `stage` | — | one of the eight stage names, or `all` | required |
| `--config`, `-c` | all | path to the YAML configuration | `config.yaml` |
| `--workers`, `-j` | `quality`, `extract`, `track` | worker processes; `0` lets each stage use `CPUs − 1` | `0` |
| `--limit N` | `track` | track only the first N pairs (smoke test) | none |
| `-v`, `--verbose` | all | DEBUG-level logging | INFO |
| `--skip-lake` | — | accepted for backwards compatibility; has no effect (see [Legacy options](#legacy-options)) | off |

Relative paths inside the configuration are resolved against the **directory that
contains the config file**, not the current working directory, so
`-c some/dir/config.yaml` works from anywhere (see [config.md](config.md)).

## Execution

`main()` performs the following steps:

1. Parse the arguments with `argparse`.
2. Configure logging (`utils.setup_logging`): timestamps, level, logger name.
3. Load the configuration (`config.load_config`). Structural errors in `config.yaml`
   — a missing stable ROI, a malformed rectangle, a missing distance — raise here,
   before any stage runs.
4. Build the stage list: `[stage]`, or all eight for `all`.
5. For each stage, import `glacier_tlc.<stage>` and call `run(cfg, ...)` with the
   arguments the stage accepts: `quality` and `extract` receive `workers`; `track`
   receives `workers` and `limit`; every other stage receives only `cfg`. The stage is
   bracketed by `=== stage X ===` and `done in N s` log lines.
6. Return `0`.

There is no exception handling around a stage: the first stage that raises aborts the
run with a traceback and later stages do not run. Stages that already completed keep
their outputs.

## Behaviour to be aware of

- **Dispatch is by dynamic import.** A stage whose module is missing fails with
  `ModuleNotFoundError` when it is reached, not at start-up. `argparse` restricts
  `stage` to the names in `STAGES`, so unknown stage names are rejected on the command
  line.
- **`--workers` is ignored** by the stages that are not parallel (`inventory`,
  `velocity`, `aggregate`, `plots`, `report`).
- **`--limit` truncates the pair list after it is built** and sorted by group and
  date, so `--limit 50` always tracks the first 50 pairs of the first group.
- The exit code is `0` on success; any exception propagates as a non-zero exit.

## Legacy options

Earlier versions included two optional stages, `compare` (annual velocity versus GNSS
and ITS_LIVE references) and `lake` (colour indices over the proglacial lake). Both
have been removed. The `--skip-lake` flag is still accepted so that existing scripts
do not break, but it does nothing; `config.yaml` may still contain `lake_rect` entries,
which are ignored.

## Typical invocations

```bash
python -m glacier_tlc all -j 10                                  # full run
python -m glacier_tlc track --limit 50                           # smoke-test the tracker
python -m glacier_tlc track -j 16                                # resume / extend tracking (cached pairs reused)
python -m glacier_tlc aggregate && python -m glacier_tlc plots   # re-aggregate after a config edit
python -m glacier_tlc -c runs/2024/config.yaml velocity          # alternative configuration
```

## See also

- [config.md](config.md) — what `load_config` validates.
- [track.md](track.md) — the only stage that honours `--limit`.
