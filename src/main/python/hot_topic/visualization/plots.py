"""Visualization utilities for BERTopic results (Plotly-based)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def visualize_topics(
    topic_model: Any,
    width: int = 1000,
    height: int = 800,
) -> Any:
    """2D projection of topics (uses UMAP from topic model)."""
    fig = topic_model.visualize_topics(width=width, height=height)
    return fig


def visualize_topic_barchart(
    topic_model: Any,
    topics: Optional[List[int]] = None,
    top_n_topics: Optional[int] = 10,
    n_words: int = 10,
    width: int = 800,
    height: int = 500,
) -> Any:
    """Horizontal bar charts of top topic words."""
    fig = topic_model.visualize_barchart(
        topics=topics,
        top_n_topics=top_n_topics,
        n_words=n_words,
        width=width,
        height=height,
    )
    return fig


def visualize_heatmap(
    topic_model: Any,
    topics: Optional[List[int]] = None,
    top_n_topics: Optional[int] = 20,
    width: int = 900,
    height: int = 900,
) -> Any:
    """Heatmap of topic similarity."""
    fig = topic_model.visualize_heatmap(
        topics=topics,
        top_n_topics=top_n_topics,
        width=width,
        height=height,
    )
    return fig


def visualize_documents(
    topic_model: Any,
    docs: List[str],
    topics: Optional[List[int]] = None,
    width: int = 1200,
    height: int = 800,
) -> Any:
    """Plot documents in 2D with topic labels."""
    fig = topic_model.visualize_documents(
        docs,
        topics=topics,
        width=width,
        height=height,
    )
    return fig


def save_figure(fig: Any, path: Path) -> Path:
    """Save a Plotly figure to HTML (interactive)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path))
    logger.info("Saved figure to %s", path)
    return path


def save_figure_png(fig: Any, path: Path, scale: int = 2) -> Path:
    """Save a Plotly figure to static PNG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(path), scale=scale)
    logger.info("Saved figure PNG to %s", path)
    return path
