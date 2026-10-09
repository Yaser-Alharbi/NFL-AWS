"""Run the whole pipeline in order, from Dataset/ to export/script_vs_chaos.html.

Each stage is the module's own ``main()``, same as ``python -m src.<module>``.

Run: ``python -m src.run_all``
Resume at a stage (reuses what earlier stages wrote to outputs/):
``python -m src.run_all --from qb_summary``
"""
from __future__ import annotations

import argparse
import time

from . import labels, league, play_context, qb_summary, thresholds, tracking_features, visualiser

STAGES = [
    ("play_context", play_context.main),
    ("tracking_features", tracking_features.main),
    ("thresholds", thresholds.main),
    ("labels", labels.main),
    ("league", league.main),
    ("qb_summary", qb_summary.main),
    ("visualiser", visualiser.main),
]


def main() -> None:
    names = [name for name, _ in STAGES]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start", choices=names, default=names[0],
                        help="first stage to run (default: %(default)s)")
    args = parser.parse_args()

    total = time.perf_counter()
    for name, run in STAGES[names.index(args.start):]:
        print(f"\n=== {name} ===")
        t = time.perf_counter()
        run()
        print(f"=== {name} done in {time.perf_counter() - t:.1f} s ===")
    print(f"\nall stages done in {time.perf_counter() - total:.1f} s")


if __name__ == "__main__":
    main()
