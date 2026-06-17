"""CLI: pull GDELT DOC 2.0 articles into a CSV.

Usage:
    python -m hot_topic.scripts.fetch_gdelt
    python -m hot_topic.scripts.fetch_gdelt --timespan 6h --max 250
    python -m hot_topic.scripts.fetch_gdelt --query "sourcelang:chinese AND (经济 OR 股市)"
    python -m hot_topic.scripts.fetch_gdelt --append   # 增量合并到同一个CSV
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from .. import config
from ..data_source import GDELTClient
from ..storage import write_csv


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch GDELT DOC 2.0 -> CSV")
    parser.add_argument(
        "--query",
        default=config.GDELT_DEFAULT_QUERY,
        help="GDELT query string (default: %(default)s)",
    )
    parser.add_argument(
        "--timespan",
        default=config.GDELT_DEFAULT_TIMESPAN,
        help="e.g. 15min, 1h, 24h, 3d (default: %(default)s)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=config.GDELT_MAX_RECORDS_PER_CALL,
        help="Max records per call, capped at 250 (default: %(default)s)",
    )
    parser.add_argument(
        "--sort",
        default="datedesc",
        choices=["datedesc", "dateasc", "tonedesc", "toneasc", "hybridrel"],
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=None,
        help="Min seconds between calls (default from config, ~5.5). "
             "Bump to 30+ if your egress IP is shared and getting 429s.",
    )
    parser.add_argument(
        "--cool-down",
        type=float,
        default=0,
        help="Sleep N seconds before the FIRST request (helps after a recent 429)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output CSV path. Default: data/hot_topic/gdelt_<YYYYMMDD>.csv",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append + dedupe into the existing CSV instead of overwriting",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.output is None:
        stamp = datetime.utcnow().strftime("%Y%m%d")
        args.output = str(config.DATA_DIR / f"gdelt_{stamp}.csv")

    client_kwargs = {}
    if args.min_interval is not None:
        client_kwargs["min_interval"] = args.min_interval
    client = GDELTClient(**client_kwargs)

    if args.cool_down > 0:
        import time as _t
        print(f"Cooling down {args.cool_down}s before first request...")
        _t.sleep(args.cool_down)

    df = client.to_dataframe(
        query=args.query,
        timespan=args.timespan,
        max_records=args.max,
        sort=args.sort,
    )
    print(f"Fetched {len(df)} articles (query={args.query!r}, timespan={args.timespan})")
    if df.empty:
        print("WARNING: empty result", file=sys.stderr)
        # still write so the file exists; downstream can detect
    write_csv(df, args.output, append=args.append)
    print(f"Saved -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
