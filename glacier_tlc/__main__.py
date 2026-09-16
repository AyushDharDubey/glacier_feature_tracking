"""Command-line entry point: python -m glacier_tlc <stage> [--config config.yaml]"""
from __future__ import annotations

import argparse
import sys
import time

from . import __doc__ as DOC
from .config import load_config
from .utils import log, setup_logging

STAGES = ["inventory", "quality", "extract", "track", "velocity", "aggregate", "plots", "report"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="glacier_tlc", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=STAGES + ["all"], help="stage to run ('all' runs every stage in order)")
    ap.add_argument("--config", "-c", default="config.yaml")
    ap.add_argument("--workers", "-j", type=int, default=0, help="worker processes (default: CPUs-1)")
    ap.add_argument("--limit", type=int, default=None, help="track: only the first N pairs (smoke test)")
    ap.add_argument("--skip-lake", action="store_true", help="'all': skip the optional lake stage")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    setup_logging(a.verbose)
    cfg = load_config(a.config)
    stages = STAGES if a.stage == "all" else [a.stage]
    for st in stages:
        t0 = time.time()
        log.info("=== stage %s ===", st)
        mod = __import__(f"glacier_tlc.{ {'track': 'track'}.get(st, st) }", fromlist=["run"])
        if st in ("quality", "extract"):
            mod.run(cfg, workers=a.workers)
        elif st == "track":
            mod.run(cfg, workers=a.workers, limit=a.limit)
        else:
            mod.run(cfg)
        log.info("=== stage %s done in %.1f s ===", st, time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
