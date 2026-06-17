

"""BERTopic-based Chinese topic modeling pipeline.

Uses BAAI/bge-small-zh-v1.5 as the default embedding model for Chinese text.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .. import config

logger = logging.getLogger(__name__)


def build_chinese_bertopic(
    embedding_model: str = "BAAI/bge-small-zh-v1.5",
    min_topic_size: int = 15,
    nr_topics: Optional[int] = None,
    seed: int = 42,
    **bertopic_kwargs: Any,
) -> Any:
    """Build a BERTopic pipeline tailored for Chinese text.

    Args:
        embedding_model: HuggingFace embedding model name for Chinese.
        min_topic_size: HDBSCAN minimum cluster size.
        nr_topics: number of topics to reduce to (None = auto).
        seed: random seed for reproducibili

        ty.
        bertopic_kwargs: extra keyword args passed to BERTopic.

    Returns:
        An initialized BERTopic instance.
    """
    try:
        from bertopic import BERTopic
        from bertopic.representation import KeyBERTInspired
        from hdbscan import HDBSCAN
        from sentence_transformers import SentenceTransformer
        from umap import UMAP
        from sklearn.feature_extraction.text import CountVectorizer
    except ImportError as e:
        raise ImportError(
            "bertopic, sentence-transformers, umap-learn, hdbscan required"
        ) from e

    logger.info("Initializing Chinese BERTopic with embedding model %s", embedding_model)

    # Embedding model
    embedder = SentenceTransformer(embedding_model)

    # UMAP (dimensionality reduction)
    umap_model = UMAP(
        n_neighbors=15,
        n_components=5,
        min_dist=0.0,
        metric="cosine",
        random_state=seed,
    )

    # HDBSCAN (clustering)
    hdbscan_model = HDBSCAN(
        min_cluster_size=min_topic_size,
        metric="euclidean",
        prediction_data=True,
    )

    # Vectorizer for c-TF-IDF (customize later if needed)
    # We use a simple whitespace tokenizer since text is already tokenized
    vectorizer_model = CountVectorizer(token_pattern=r"(?u)\S\S+")

    # Representation model (KeyBERT-inspired for better topic labels)
    representation_model = KeyBERTInspired()

    # Build topic model
    topic_model = BERTopic(
        embedding_model=embedder,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        representation_model=representation_model,
        nr_topics=nr_topics,
        calculate_probabilities=True,
        verbose=True,
        **bertopic_kwargs,
    )
    return topic_model


def train_topic_model(
    topic_model: Any,
    texts: List[str],
    raw_docs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Train the topic model on preprocessed texts.

    Args:
        topic_model: initialized BERTopic instance.
        texts: preprocessed, tokenized text list (space-separated tokens).
        raw_docs: optional original document list for reference.

    Returns:
        dict with topics, probabilities, topic model (fit), and topic info.
    """
    logger.info("Fitting topic model on %d texts...", len(texts))
    topics, probs = topic_model.fit_transform(texts)
    topic_info = topic_model.get_topic_info()

    result = {
        "topic_model": topic_model,
        "topics": topics,
        "probabilities": probs,
        "topic_info": topic_info,
        "num_topics": len(topic_info),
        "num_outliers": int((pd.Series(topics) == -1).sum()),
    }
    logger.info(
        "Topic modeling done: %d topics found, %d outliers",
        result["num_topics"], result["num_outliers"],
    )
    return result


def get_topic_summary(topic_model: Any, top_n: int = 10) -> pd.DataFrame:
    """Return a readable topic summary DataFrame."""
    topic_info = topic_model.get_topic_info().copy()
    # Add readable topic labels
    topic_info["Label"] = topic_info.apply(
        lambda row: _format_topic_label(topic_model, row["Topic"], top_n=top_n),
        axis=1,
    )
    return topic_info


def get_topic_table(
    topic_model: Any,
    topics: List[int],
    raw_docs: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Return a DataFrame with each document's topic assignment."""
    df = pd.DataFrame({"topic": topics})
    if raw_docs is not None:
        df["text"] = raw_docs
    df["topic_name"] = df["topic"].map(
        lambda t: topic_model.generate_topic_labels(t)[0] if t != -1 else "Outlier"
    )
    return df


def save_topic_model(
    topic_model: Any,
    path: Path,
    save_embedding_model: bool = True,
) -> Path:
    """Save a topic model to disk.

    Uses safetensors format for safety when loading later.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Saving topic model to %s", path)
    topic_model.save(
        path,
        serialization="safetensors",
        save_embedding_model=save_embedding_model,
    )
    return path


def load_topic_model(path: Path) -> Any:
    """Load a topic model from disk."""
    from bertopic import BERTopic
    path = Path(path)
    logger.info("Loading topic model from %s", path)
    return BERTopic.load(path)


def _format_topic_label(topic_model: Any, topic: int, top_n: int = 5) -> str:
    """Format topic words into a human-readable label string."""
    if topic == -1:
        return "Outlier"
    words = [w for w, _ in topic_model.get_topic(topic)[:top_n]]
    return " | ".join(words)
