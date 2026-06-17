"""CLI: pull THUCNews from HuggingFace into a CSV.

Usage:
    python -m hot_topic.scripts.fetch_thucnews                 # 1万条默认
    python -m hot_topic.scripts.fetch_thucnews -n 50000        # 5万条
    python -m hot_topic.scripts.fetch_thucnews -n 0            # 全量
    python -m hot_topic.scripts.fetch_thucnews --streaming     # HF流式
"""
from __future__ import annotations

import argparse
import logging
import sys

from .. import config
from ..data_source import THUCNewsLoader
from ..storage import write_csv


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fetch THUCNews -> CSV")
    parser.add_argument(
        "-n", "--num",
        type=int,
        default=config.THUCNEWS_DEFAULT_SAMPLE,
        help="Sample size; 0 = full dataset (default: %(default)s)",
    )
    parser.add_argument(
        "--repo",
        default=config.THUCNEWS_HF_REPO,
        help="HuggingFace repo id (default: %(default)s)",
    )
    parser.add_argument(
        "--split",
        default=config.THUCNEWS_HF_SPLIT,
        help="Dataset split (default: %(default)s)",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Use HF streaming mode (no full download)",
    )
    parser.add_argument(
        "-o", "--output",
        default=str(config.THUCNEWS_OUTPUT),
        help="Output CSV path (default: %(default)s)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sample_size = None if args.num == 0 else args.num
    loader = THUCNewsLoader(hf_repo=args.repo, split=args.split)
    df = loader.to_dataframe(
        sample_size=sample_size,
        seed=args.seed,
        streaming=args.streaming,
    )
    print(f"Loaded {len(df)} rows")
    if df.empty:
        print("ERROR: empty result", file=sys.stderr)
        return 1
    write_csv(df, args.output, append=False)
    print(f"Saved -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
