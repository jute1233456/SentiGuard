"""Simple quick-start script for THUCNews + BERTopic training.

This is a simplified wrapper around the improved training script with
sensible defaults.

Usage:
    python train_thucnews_simple.py --size small    # 10k docs, fast
    python train_thucnews_simple.py --size medium   # 50k docs, recommended
    python train_thucnews_simple.py --size large    # 100k docs, better quality
    python train_thucnews_simple.py --size full     # full dataset
"""
import argparse
import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the module
sys.path.insert(0, str(Path(__file__).parent))

# Set HF mirror
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def main():
    parser = argparse.ArgumentParser(
        description="Quick start: Train BERTopic on THUCNews with sensible defaults"
    )

    parser.add_argument(
        "--size",
        type=str,
        default="medium",
        choices=["small", "medium", "large", "full"],
        help="Dataset size preset (default: %(default)s)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional name for this run",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use smaller embedding model for faster training",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Map presets to parameters
    preset_configs = {
        "small": {
            "sample": 10000,
            "min_topic_size": 20,
            "embedding_model": "BAAI/bge-small-zh-v1.5",
        },
        "medium": {
            "sample": 50000,
            "min_topic_size": 30,
            "embedding_model": "BAAI/bge-large-zh-v1.5",
        },
        "large": {
            "sample": 100000,
            "min_topic_size": 50,
            "embedding_model": "BAAI/bge-large-zh-v1.5",
        },
        "full": {
            "sample": 0,  # full dataset
            "min_topic_size": 100,
            "embedding_model": "BAAI/bge-large-zh-v1.5",
        },
    }

    config = preset_configs[args.size]

    # Apply fast mode
    if args.fast:
        config["embedding_model"] = "BAAI/bge-small-zh-v1.5"

    # Build arguments for the improved trainer
    from hot_topic.scripts.train_thucnews_improved import main as trainer_main

    # Set default name based on size if not provided
    if args.name is None:
        args.name = f"{args.size}"

    # Build argv
    argv = [
        "--sample", str(config["sample"]),
        "--min_topic_size", str(config["min_topic_size"]),
        "--embedding_model", config["embedding_model"],
        "--name", args.name,
    ]
    if args.verbose:
        argv.append("-v")

    print("=" * 80)
    print(f"QUICK START: THUCNEWS + BERTOPIC TRAINING")
    print(f"Preset: {args.size}")
    print(f"Sample size: {config['sample'] if config['sample'] > 0 else 'FULL DATASET'}")
    print(f"Embedding model: {config['embedding_model']}")
    print(f"Run name: {args.name}")
    print("=" * 80)
    print()

    # Run the trainer
    return trainer_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
