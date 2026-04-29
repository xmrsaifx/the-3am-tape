"""Weekly channel-performance digest CLI.

Builds a markdown report comparing the latest stats snapshot to the snapshot
~7 days ago. Output is printed to stdout (so the workflow can capture it and
post as a GitHub Issue body) and also saved to outputs/stats/digests/<date>.md.

Usage:
    ./venv/bin/python digest.py                  # write digest from existing snapshots
    ./venv/bin/python digest.py --fetch          # take a fresh stats snapshot first
    ./venv/bin/python digest.py --lookback 14    # compare vs 14 days ago instead of 7
    ./venv/bin/python digest.py --out report.md  # write to a custom path

In the GitHub Actions workflow this is what gets posted as the Issue body each
Sunday — title goes "Channel digest — YYYY-MM-DD", body is the markdown.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from pipeline import stats as stats_mod


def main(fetch: bool, lookback: int, out_path: Path | None) -> None:
    if fetch:
        snapshot_path = stats_mod.record_snapshot()
    else:
        snaps = sorted(stats_mod.STATS_DIR.glob("*.json"))
        if not snaps:
            raise SystemExit("No stats snapshots yet. Run `python stats.py` first or pass --fetch.")
        snapshot_path = snaps[-1]

    digest = stats_mod.weekly_digest(snapshot_path, lookback_days=lookback)
    print(digest)

    digest_dir = stats_mod.STATS_DIR / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    target = out_path or (digest_dir / f"{date.today().isoformat()}.md")
    target.write_text(digest)
    # stderr-style notice so stdout stays purely the digest body
    import sys
    print(f"\n(digest also saved to {target})", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true",
                        help="Take a fresh stats snapshot before building the digest.")
    parser.add_argument("--lookback", type=int, default=7,
                        help="Days to compare against (default 7).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Custom output path for the digest markdown.")
    args = parser.parse_args()
    main(fetch=args.fetch, lookback=args.lookback, out_path=args.out)
