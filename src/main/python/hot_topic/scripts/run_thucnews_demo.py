"""End-to-end demo: THUCNews → BERTopic modeling → visualizations.

Run this script from src/main/python:

    python -m hot_topic.scripts.run_thucnews_demo --sample 10000
"""
from __future__ import annotations

import os
import sys

# Set HF mirror BEFORE ANYTHING ELSE
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import argparse
import logging
from pathlib import Path

import pandas as pd

from .. import config
from ..data_source import THUCNewsLoader
from ..modeling import (
    build_chinese_bertopic,
    train_topic_model,
    save_topic_model,
    get_topic_summary,
)
from ..preprocessing import preprocess_for_bertopic, build_stopwords
from ..visualization import (
    visualize_topics,
    visualize_topic_barchart,
    visualize_heatmap,
    save_figure,
)
from ..storage.csv_writer import write_csv


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="THUCNews + BERTopic end-to-end demo")
    parser.add_argument(
        "--sample",
        type=int,
        default=10000,
        help="Number of THUCNews documents to sample (default 10000)",
    )
    parser.add_argument(
        "--min-topic-size",
        type=int,
        default=20,
        help="HDBSCAN min cluster size (default 20)",
    )
    parser.add_argument(
        "--nr-topics",
        type=int,
        default=None,
        help="Number of topics to reduce to (auto if not given)",
    )
    parser.add_argument(
        "--embedding-model",
        default="BAAI/bge-small-zh-v1.5",
        help="HuggingFace embedding model for Chinese (default BAAI/bge-small-zh-v1.5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default 42)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.DATA_DIR / "thucnews_demo",
        help="Output directory (default data/hot_topic/thucnews_demo)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    # Logging setup
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger = logging.getLogger(__name__)

    # Output directory
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load THUCNews
    logger.info("Step 1: Loading THUCNews (sample=%d)", args.sample)
    loader = THUCNewsLoader()
    docs_df = loader.to_dataframe(sample_size=args.sample, seed=args.seed, streaming=False)
    if docs_df.empty:
        print("ERROR: no data loaded", file=sys.stderr)
        return 1

    # Save raw data
    docs_csv = out_dir / "thucnews_sample.csv"
    write_csv(docs_df, docs_csv, append=False)

    raw_texts = (docs_df["title"] + " " + docs_df["content"]).tolist()

    # 2. Preprocess text
    logger.info("Step 2: Preprocessing Chinese text")
    stopwords = build_stopwords()
    tokenized_texts = preprocess_for_bertopic(raw_texts, stopwords=stopwords)
    if not tokenized_texts:
        print("ERROR: no valid texts left after preprocessing", file=sys.stderr)
        return 1

    # 3. Build topic model
    logger.info("Step 3: Building and training BERTopic model")
    topic_model = build_chinese_bertopic(
        embedding_model=args.embedding_model,
        min_topic_size=args.min_topic_size,
        nr_topics=args.nr_topics,
        seed=args.seed,
    )

    result = train_topic_model(topic_model, tokenized_texts, raw_docs=raw_texts)

    # 4. Save model and outputs
    model_path = out_dir / "bertopic_model"
    save_topic_model(topic_model, model_path, save_embedding_model=True)

    topic_summary_df = get_topic_summary(topic_model)
    topic_summary_csv = out_dir / "topic_summary.csv"
    topic_summary_df.to_csv(topic_summary_csv, index=False, encoding="utf-8-sig")
    logger.info("Saved topic summary: %s", topic_summary_csv)

    # Assign topics to docs and save
    docs_with_topics_df = docs_df.copy()
    docs_with_topics_df = docs_with_topics_df.iloc[: len(result["topics"])].copy()
    docs_with_topics_df["topic"] = result["topics"]
    docs_topics_csv = out_dir / "thucnews_with_topics.csv"
    docs_with_topics_df.to_csv(docs_topics_csv, index=False, encoding="utf-8-sig")

    # 5. Generate visualizations
    logger.info("Step 5: Generating visualizations")
    try:
        fig_topics = visualize_topics(topic_model, width=1200, height=900)
        save_figure(fig_topics, out_dir / "topics_2d.html")
    except Exception as e:
        logger.warning("Could not generate 2D topic plot: %s", e)

    try:
        fig_bars = visualize_topic_barchart(topic_model, top_n_topics=10)
        save_figure(fig_bars, out_dir / "topic_barchart.html")
    except Exception as e:
        logger.warning("Could not generate barchart: %s", e)

    try:
        fig_heat = visualize_heatmap(topic_model, top_n_topics=20)
        save_figure(fig_heat, out_dir / "topic_heatmap.html")
    except Exception as e:
        logger.warning("Could not generate heatmap: %s", e)

    # Done
    print("\n" + "=" * 80)
    print("DEMO DONE!")
    print(f"Outputs written to: {out_dir.resolve()}")
    print(f"- Model: {model_path.resolve()}")
    print(f"- Topic summary: {topic_summary_csv.resolve()}")
    print("=" * 80 + "\n")
    print("Top topics:")
    print(topic_summary_df[["Topic", "Count", "Label"]].head(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
