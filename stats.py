"""Daily YouTube stats snapshot CLI.

Usage:
    ./venv/bin/python stats.py            # pull today's snapshot, print summary
    ./venv/bin/python stats.py --no-fetch # just print the latest snapshot, no API call

Cron (later):
    0 10 * * * cd /path/to/Youtube && ./venv/bin/python stats.py >> logs/stats.log 2>&1
"""
from __future__ import annotations

import argparse

from pipeline import stats as stats_mod


def main(no_fetch: bool) -> None:
    if no_fetch:
        snaps = sorted(stats_mod.STATS_DIR.glob("*.json"))
        if not snaps:
            raise SystemExit("No snapshots yet. Run without --no-fetch.")
        path = snaps[-1]
    else:
        path = stats_mod.record_snapshot()
    print(stats_mod.render_summary(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fetch", action="store_true",
                        help="Don't hit the API; just summarize the latest snapshot.")
    args = parser.parse_args()
    main(no_fetch=args.no_fetch)
