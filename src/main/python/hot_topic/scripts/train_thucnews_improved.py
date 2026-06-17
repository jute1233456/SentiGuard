"""Enhanced THUCNews + BERTopic training script.

Features:
- Larger dataset support (50k-100k+)
- Better preprocessing and stopword handling
- Optimized model parameters
- Comprehensive visualizations
- Model evaluation metrics
- Incremental training support

Usage:
    python -m hot_topic.scripts.train_thucnews_improved --sample 50000
    python -m hot_topic.scripts.train_thucnews_improved --sample 0  # full dataset
    python -m hot_topic.scripts.train_thucnews_improved --help
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import numpy as np

# Set HF mirror first
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from .. import config
from ..data_source import THUCNewsLoader
from ..modeling import (
    build_chinese_bertopic,
    train_topic_model,
    save_topic_model,
    load_topic_model,
    get_topic_summary,
)
from ..preprocessing import preprocess_for_bertopic, build_stopwords, chinese_tokenize
from ..visualization import (
    visualize_topics,
    visualize_topic_barchart,
    visualize_heatmap,
    save_figure,
)
from ..storage.csv_writer import write_csv

logger = logging.getLogger(__name__)

# Extended Chinese stopwords for better topic modeling
_EXTENDED_CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "他", "她", "它们", "我们", "什么", "吗", "呢", "吧", "啊",
    "把", "被", "从", "到", "对", "对于", "关于", "跟", "与", "同", "给", "让",
    "个", "位", "件", "份", "条", "根", "块", "片", "页", "题", "行", "列",
    "是", "有", "在", "来", "去", "上", "下", "左", "右", "前", "后", "里", "外",
    "将", "已经", "正在", "就要", "刚刚", "忽然", "突然", "终于", "其实",
    "但是", "可是", "不过", "然而", "因此", "所以", "于是", "结果", "因为",
    "可以", "能够", "应该", "会", "要", "想", "希望", "愿意", "打算",
    "这个", "那个", "这些", "那些", "这样", "那样", "怎么", "如何", "为什么",
    "中国", "新闻", "报道", "记者", "表示", "称", "说", "指出", "认为", "透露",
    "日", "月", "年", "今天", "昨天", "明天", "近日", "日前", "目前", "至今",
    "已", "已经", "曾", "曾经", "将", "即将", "正在", "正", "在", "中",
    "为", "为了", "由于", "因为", "所以", "因此", "因而", "于是", "从而",
    "并", "并且", "而", "而且", "同时", "此外", "另外", "还有", "再者",
    "或", "或者", "还是", "亦", "也", "又", "再", "更", "最", "太", "很",
    "非常", "特别", "十分", "尤其", "格外", "相当", "比较", "几乎", "简直",
    "我们", "咱们", "大家", "各位", "诸位", "同志", "先生", "女士", "朋友",
    "它", "它们", "这", "那", "这里", "那里", "这儿", "那儿", "这边", "那边",
    "来", "来的", "来着", "起来", "出来", "下来", "过来", "回来",
    "去", "出去", "下去", "过去", "回去", "上去", "进去",
    "是", "就是", "还是", "倒是", "真是", "只是", "还是", "就是",
    "与", "和", "及", "以及", "包括", "包含", "有", "具有", "拥有",
    "进行", "开展", "推进", "推动", "促进", "加强", "深化", "提高",
    "工作", "任务", "项目", "计划", "方案", "措施", "政策", "规定",
    "问题", "情况", "状况", "状态", "形势", "局面", "局面", "局势",
    "时候", "时间", "时期", "阶段", "期间", "过程", "过程中",
    "方面", "领域", "行业", "系统", "体系", "机制", "体制", "制度",
    "发展", "建设", "建立", "构建", "打造", "培育", "培养", "提高",
    "服务", "管理", "监督", "监管", "检查", "调查", "研究", "分析",
    "相关", "有关", "相应", "相应的", "对应的", "相关的", "有关的",
    "需要", "要求", "需求", "必要", "必须", "务必", "一定", "必定",
    "可能", "也许", "或许", "大概", "大约", "左右", "上下", "前后",
    "然后", "接着", "随后", "随即", "立即", "立刻", "马上", "很快",
    "通过", "经过", "经历", "历经", "历经", "通过", "借助", "利用",
    "根据", "依据", "按照", "遵照", "依照", "根据", "基于", "鉴于",
    "主要", "重要", "关键", "核心", "根本", "基本", "基础", "首要",
    "部分", "其中", "之一", "之一", "一些", "一定", "不少", "很多",
    "并", "并且", "同时", "与此同时", "同期", "同年", "同月", "同日",
    "另", "另外", "此外", "再者", "而且", "还有", "更进一步",
    "等", "等等", "诸如此类", "之类", "之类的", "以及", "等等",
    "记者", "通讯员", "报道", "报导", "消息", "新闻", "资讯", "信息",
    "电", "讯", "专电", "特稿", "专访", "专刊", "专题", "特刊",
    "本报讯", "本报记者", "特约记者", "通讯员", "报道", "发", "发稿",
}


def build_extended_stopwords(
    extra_stopwords: Optional[List[str]] = None,
    stopwords_path: Optional[Path] = None,
) -> Set[str]:
    """Build an extended stopword set for better Chinese topic modeling."""
    stops = set(_EXTENDED_CHINESE_STOPWORDS)
    if extra_stopwords:
        stops.update(extra_stopwords)
    if stopwords_path and stopwords_path.exists():
        with open(stopwords_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    stops.add(line)
    return stops


def build_improved_chinese_bertopic(
    embedding_model: str = "BAAI/bge-large-zh-v1.5",
    min_topic_size: int = 30,
    nr_topics: Optional[int] = None,
    seed: int = 42,
    n_neighbors: int = 15,
    n_components: int = 5,
    use_keybert: bool = True,
    **bertopic_kwargs: Any,
) -> Any:
    """Build an improved BERTopic pipeline for Chinese text.

    Args:
        embedding_model: HuggingFace embedding model name for Chinese.
        min_topic_size: HDBSCAN minimum cluster size.
        nr_topics: number of topics to reduce to (None = auto).
        seed: random seed for reproducibility.
        n_neighbors: UMAP n_neighbors parameter.
        n_components: UMAP n_components parameter.
        use_keybert: whether to use KeyBERT-inspired representation.
        bertopic_kwargs: extra keyword args passed to BERTopic.

    Returns:
        An initialized BERTopic instance.
    """
    try:
        from bertopic import BERTopic
        from bertopic.representation import KeyBERTInspired, MaximalMarginalRelevance
        from hdbscan import HDBSCAN
        from sentence_transformers import SentenceTransformer
        from umap import UMAP
        from sklearn.feature_extraction.text import CountVectorizer
    except ImportError as e:
        raise ImportError(
            "bertopic, sentence-transformers, umap-learn, hdbscan required"
        ) from e

    logger.info("Initializing improved Chinese BERTopic with embedding model %s", embedding_model)

    # Embedding model
    embedder = SentenceTransformer(embedding_model)

    # UMAP (dimensionality reduction) - optimized for Chinese
    umap_model = UMAP(
        n_neighbors=n_neighbors,
        n_components=n_components,
        min_dist=0.0,
        metric="cosine",
        random_state=seed,
        verbose=True,
    )

    # HDBSCAN (clustering) - more aggressive for larger datasets
    hdbscan_model = HDBSCAN(
        min_cluster_size=min_topic_size,
        min_samples=max(5, min_topic_size // 3),
        metric="euclidean",
        prediction_data=True,
        cluster_selection_method="eom",  # Excess of Mass
        core_dist_n_jobs=-1,
    )

    # Vectorizer for c-TF-IDF with n-grams
    vectorizer_model = CountVectorizer(
        token_pattern=r"(?u)\S\S+",
        ngram_range=(1, 2),  # Include bigrams for better Chinese topic labeling
        min_df=2,
    )

    # Representation models - combine KeyBERT and MMR for better labels
    representation_models = {}
    if use_keybert:
        representation_models["KeyBERT"] = KeyBERTInspired()
        representation_models["MMR"] = MaximalMarginalRelevance(diversity=0.3)

    # Build topic model
    topic_model = BERTopic(
        embedding_model=embedder,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        representation_model=representation_models if use_keybert else None,
        nr_topics=nr_topics,
        top_n_words=10,
        n_gram_range=(1, 2),
        calculate_probabilities=True,
        verbose=True,
        **bertopic_kwargs,
    )
    return topic_model


def calculate_topic_coherence(
    topic_model: Any,
    texts: List[str],
    top_n: int = 10,
) -> Dict[int, float]:
    """Calculate simple topic coherence based on word co-occurrence."""
    from collections import defaultdict

    # Get vocabulary and word frequencies
    vocab = defaultdict(int)
    for text in texts:
        for word in text.split():
            vocab[word] += 1

    total_texts = len(texts)

    # Calculate document-word presence
    word_in_docs = defaultdict(set)
    for doc_idx, text in enumerate(texts):
        words = set(text.split())
        for word in words:
            word_in_docs[word].add(doc_idx)

    coherence_scores = {}
    topic_info = topic_model.get_topic_info()

    for topic_idx in topic_info["Topic"]:
        if topic_idx == -1:
            continue

        topic_words = [word for word, _ in topic_model.get_topic(topic_idx)[:top_n]]

        # Calculate pairwise co-occurrence
        score = 0.0
        pair_count = 0

        for i in range(len(topic_words)):
            for j in range(i + 1, len(topic_words)):
                w1, w2 = topic_words[i], topic_words[j]
                s1 = word_in_docs.get(w1, set())
                s2 = word_in_docs.get(w2, set())

                if s1 and s2:
                    co_occurrence = len(s1.intersection(s2))
                    if co_occurrence > 0:
                        score += np.log((co_occurrence + 1) / (len(s1) * len(s2) / total_texts))
                        pair_count += 1

        coherence_scores[topic_idx] = score / pair_count if pair_count > 0 else 0.0

    return coherence_scores


def generate_evaluation_report(
    topic_model: Any,
    texts: List[str],
    topics: List[int],
    output_dir: Path,
) -> pd.DataFrame:
    """Generate a comprehensive evaluation report."""
    logger.info("Generating evaluation report...")

    topic_info = topic_model.get_topic_info().copy()

    # Add topic size percentage
    total_docs = len(topics)
    topic_info["Percentage"] = topic_info["Count"] / total_docs * 100

    # Add coherence scores
    try:
        coherence_scores = calculate_topic_coherence(topic_model, texts)
        topic_info["Coherence"] = topic_info["Topic"].map(
            lambda t: coherence_scores.get(t, 0.0)
        )
    except Exception as e:
        logger.warning(f"Could not calculate coherence: {e}")
        topic_info["Coherence"] = 0.0

    # Add readable labels
    topic_info["Label"] = topic_info.apply(
        lambda row: " | ".join([w for w, _ in topic_model.get_topic(row["Topic"])[:5]])
        if row["Topic"] != -1
        else "Outlier",
        axis=1,
    )

    # Reorder columns
    columns = ["Topic", "Count", "Percentage", "Coherence", "Label", "Name"]
    available_cols = [c for c in columns if c in topic_info.columns]
    topic_info = topic_info[available_cols]

    # Save
    report_path = output_dir / "evaluation_report.csv"
    topic_info.to_csv(report_path, index=False, encoding="utf-8-sig")
    logger.info(f"Evaluation report saved to: {report_path}")

    return topic_info


def create_extra_visualizations(
    topic_model: Any,
    output_dir: Path,
    top_n_topics: int = 20,
):
    """Create additional visualizations beyond the default ones."""
    logger.info("Creating extra visualizations...")

    try:
        # Topic hierarchy
        try:
            hierarchical_topics = topic_model.hierarchical_topics()
            fig_tree = topic_model.visualize_hierarchy(hierarchical_topics=hierarchical_topics)
            save_figure(fig_tree, output_dir / "topic_hierarchy.html")
        except Exception as e:
            logger.warning(f"Could not create hierarchy visualization: {e}")

        # Topic similarity heatmap
        try:
            fig_sim = topic_model.visualize_heatmap(top_n_topics=top_n_topics)
            save_figure(fig_sim, output_dir / "topic_similarity_heatmap.html")
        except Exception as e:
            logger.warning(f"Could not create similarity heatmap: {e}")

        # Topic term score decline
        try:
            fig_terms = topic_model.visualize_term_rank(top_n_topics=top_n_topics)
            save_figure(fig_terms, output_dir / "term_rank.html")
        except Exception as e:
            logger.warning(f"Could not create term rank visualization: {e}")

        # Topic distribution
        try:
            fig_dist = topic_model.visualize_distribution(top_n_topics=top_n_topics)
            save_figure(fig_dist, output_dir / "topic_distribution.html")
        except Exception as e:
            logger.warning(f"Could not create distribution visualization: {e}")

    except Exception as e:
        logger.warning(f"Error in extra visualizations: {e}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Enhanced THUCNews + BERTopic training with large dataset support"
    )

    # Data parameters
    parser.add_argument(
        "--sample",
        type=int,
        default=50000,
        help="Number of THUCNews documents to sample; 0 = full dataset (default: %(default)s)",
    )
    parser.add_argument(
        "--repo",
        default=config.THUCNEWS_HF_REPO,
        help="HuggingFace repo id for THUCNews (default: %(default)s)",
    )
    parser.add_argument(
        "--split",
        default=config.THUCNEWS_HF_SPLIT,
        help="Dataset split (default: %(default)s)",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Use HF streaming mode for very large datasets",
    )

    # Model parameters
    parser.add_argument(
        "--embedding_model",
        default="BAAI/bge-large-zh-v1.5",
        help="Embedding model (default: %(default)s); consider 'BAAI/bge-small-zh-v1.5' for speed",
    )
    parser.add_argument(
        "--min_topic_size",
        type=int,
        default=30,
        help="HDBSCAN min cluster size (default: %(default)s)",
    )
    parser.add_argument(
        "--nr_topics",
        type=int,
        default=None,
        help="Number of topics to reduce to (auto if not given)",
    )
    parser.add_argument(
        "--n_neighbors",
        type=int,
        default=15,
        help="UMAP n_neighbors (default: %(default)s)",
    )
    parser.add_argument(
        "--n_components",
        type=int,
        default=5,
        help="UMAP n_components (default: %(default)s)",
    )

    # Preprocessing
    parser.add_argument(
        "--min_text_len",
        type=int,
        default=15,
        help="Minimum tokenized text length (default: %(default)s)",
    )
    parser.add_argument(
        "--use_extended_stopwords",
        action="store_true",
        default=True,
        help="Use extended stopword list (default: %(default)s)",
    )

    # Output
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=config.DATA_DIR / "thucnews_improved",
        help="Output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional name for this run (creates subdirectory)",
    )

    # Other
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    # Logging setup
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Setup output directory
    output_dir = args.output_dir
    if args.name:
        output_dir = output_dir / args.name
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("ENHANCED THUCNEWS + BERTOPIC TRAINING")
    logger.info("=" * 80)
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Sample size: {args.sample if args.sample > 0 else 'FULL DATASET'}")
    logger.info(f"Embedding model: {args.embedding_model}")

    # -----------------------------------------------------------------------
    # Step 1: Load THUCNews
    # -----------------------------------------------------------------------
    logger.info("\n[1/7] Loading THUCNews dataset...")
    start_time = time.time()

    sample_size = None if args.sample == 0 else args.sample
    loader = THUCNewsLoader(hf_repo=args.repo, split=args.split)
    docs_df = loader.to_dataframe(
        sample_size=sample_size,
        seed=args.seed,
        streaming=args.streaming,
    )

    if docs_df.empty:
        print("ERROR: no data loaded", file=sys.stderr)
        return 1

    logger.info(f"Loaded {len(docs_df):,} documents in {time.time() - start_time:.1f}s")

    # Save raw data
    raw_data_path = output_dir / "thucnews_raw.csv"
    write_csv(docs_df, raw_data_path, append=False)
    logger.info(f"Raw data saved to: {raw_data_path}")

    # Combine title and content
    raw_texts = (docs_df["title"] + " " + docs_df["content"]).tolist()

    # -----------------------------------------------------------------------
    # Step 2: Preprocess text
    # -----------------------------------------------------------------------
    logger.info("\n[2/7] Preprocessing Chinese text...")
    start_time = time.time()

    if args.use_extended_stopwords:
        stopwords = build_extended_stopwords()
        logger.info(f"Using {len(stopwords):,} extended stopwords")
    else:
        stopwords = build_stopwords()

    tokenized_texts = preprocess_for_bertopic(
        raw_texts,
        stopwords=stopwords,
        min_len=args.min_text_len,
    )

    if not tokenized_texts:
        print("ERROR: no valid texts left after preprocessing", file=sys.stderr)
        return 1

    logger.info(f"Preprocessed {len(tokenized_texts):,} texts in {time.time() - start_time:.1f}s")

    # Save preprocessed texts
    preprocessed_path = output_dir / "preprocessed_texts.txt"
    with open(preprocessed_path, "w", encoding="utf-8") as f:
        for text in tokenized_texts:
            f.write(text + "\n")
    logger.info(f"Preprocessed texts saved to: {preprocessed_path}")

    # -----------------------------------------------------------------------
    # Step 3: Build and train topic model
    # -----------------------------------------------------------------------
    logger.info("\n[3/7] Building BERTopic model...")
    start_time = time.time()

    topic_model = build_improved_chinese_bertopic(
        embedding_model=args.embedding_model,
        min_topic_size=args.min_topic_size,
        nr_topics=args.nr_topics,
        seed=args.seed,
        n_neighbors=args.n_neighbors,
        n_components=args.n_components,
    )

    logger.info("Training topic model...")
    result = train_topic_model(topic_model, tokenized_texts, raw_docs=raw_texts)

    logger.info(f"Training completed in {time.time() - start_time:.1f}s")
    logger.info(f"Found {result['num_topics']} topics")
    logger.info(f"Outliers: {result['num_outliers']:,} ({result['num_outliers']/len(tokenized_texts)*100:.1f}%)")

    # -----------------------------------------------------------------------
    # Step 4: Save model
    # -----------------------------------------------------------------------
    logger.info("\n[4/7] Saving model...")
    model_path = output_dir / "bertopic_model"
    save_topic_model(topic_model, model_path, save_embedding_model=True)
    logger.info(f"Model saved to: {model_path}")

    # -----------------------------------------------------------------------
    # Step 5: Evaluation report
    # -----------------------------------------------------------------------
    logger.info("\n[5/7] Generating evaluation report...")
    eval_report = generate_evaluation_report(
        topic_model, tokenized_texts, result["topics"], output_dir
    )

    # -----------------------------------------------------------------------
    # Step 6: Topic summary
    # -----------------------------------------------------------------------
    logger.info("\n[6/7] Generating topic summary...")
    topic_summary = get_topic_summary(topic_model)
    topic_summary_path = output_dir / "topic_summary.csv"
    topic_summary.to_csv(topic_summary_path, index=False, encoding="utf-8-sig")
    logger.info(f"Topic summary saved to: {topic_summary_path}")

    # Save document-topic assignments
    docs_with_topics = docs_df.iloc[: len(result["topics"])].copy()
    docs_with_topics["topic"] = result["topics"]
    docs_topics_path = output_dir / "thucnews_with_topics.csv"
    docs_with_topics.to_csv(docs_topics_path, index=False, encoding="utf-8-sig")
    logger.info(f"Document-topic assignments saved to: {docs_topics_path}")

    # -----------------------------------------------------------------------
    # Step 7: Visualizations
    # -----------------------------------------------------------------------
    logger.info("\n[7/7] Generating visualizations...")

    # Basic visualizations
    try:
        fig_topics = visualize_topics(topic_model, width=1200, height=900)
        save_figure(fig_topics, output_dir / "topics_2d.html")
        logger.info("2D topic visualization saved")
    except Exception as e:
        logger.warning(f"Could not create 2D topic plot: {e}")

    try:
        fig_bars = visualize_topic_barchart(topic_model, top_n_topics=15)
        save_figure(fig_bars, output_dir / "topic_barchart.html")
        logger.info("Topic barchart saved")
    except Exception as e:
        logger.warning(f"Could not create barchart: {e}")

    # Extra visualizations
    create_extra_visualizations(topic_model, output_dir, top_n_topics=20)

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TRAINING COMPLETE!")
    print("=" * 80)
    print(f"\nOutput directory: {output_dir.resolve()}")
    print(f"\nKey files:")
    print(f"  - Model:                {model_path.resolve()}")
    print(f"  - Raw data:             {raw_data_path.resolve()}")
    print(f"  - Evaluation report:    {output_dir / 'evaluation_report.csv'}")
    print(f"  - Topic summary:        {topic_summary_path.resolve()}")
    print(f"  - Topics 2D:            {output_dir / 'topics_2d.html'}")

    print(f"\nTop topics (by size):")
    top_topics = eval_report[eval_report["Topic"] != -1].head(10)
    for _, row in top_topics.iterrows():
        print(f"  Topic {row['Topic']:3d}: {row['Count']:5d} docs ({row['Percentage']:4.1f}%) - {row['Label'][:50]}...")

    avg_coherence = eval_report[eval_report["Topic"] != -1]["Coherence"].mean()
    print(f"\nAverage topic coherence: {avg_coherence:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
