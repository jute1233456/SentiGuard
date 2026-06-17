"""THUCNews loader (via HuggingFace datasets).

THUCNews itself is a static corpus of ~740k Chinese news articles in 14
categories.  We pull it from a HuggingFace mirror so users don't have to
download the original ~2GB tarball manually.

The HF mirror's column names vary across community uploads.  We probe a small
set of common names and map whichever exists into our unified schema.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional

from .base import BaseDataSource

logger = logging.getLogger(__name__)

# column-name candidates seen across THUCNews HF mirrors
_TITLE_KEYS = ("title", "headline", "sentence", "text")
_CONTENT_KEYS = ("content", "article", "body", "text", "sentence")
_LABEL_KEYS = ("label", "category", "class", "label_text")


def _pick(record: dict, keys) -> str:
    for k in keys:
        if k in record and record[k] is not None:
            return str(record[k])
    return ""


class THUCNewsLoader(BaseDataSource):
    """Loads THUCNews from a HuggingFace dataset repo, with optional sampling."""

    name = "thucnews"

    def __init__(
        self,
        hf_repo: Optional[str] = None,
        split: Optional[str] = None,
    ):
        from .. import config

        self.hf_repo = hf_repo or config.THUCNEWS_HF_REPO
        self.split = split or config.THUCNEWS_HF_SPLIT

    def iter_docs(
        self,
        sample_size: Optional[int] = None,
        seed: int = 42,
        streaming: bool = False,
    ) -> Iterator[dict]:
        """Yield up to `sample_size` documents.

        If `streaming=True`, uses HF streaming (no full download); otherwise
        downloads to local cache once and shuffles in memory.
        """
        try:
            from datasets import load_dataset
        except ImportError as e:
            raise ImportError(
                "datasets is required for THUCNewsLoader. "
                "Install with: pip install datasets"
            ) from e

        # Use HF mirror for China
        import os
        if "HF_ENDPOINT" not in os.environ:
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
            logger.info("Using HF mirror: https://hf-mirror.com")

        logger.info(
            "Loading %s [split=%s, streaming=%s]",
            self.hf_repo, self.split, streaming,
        )
        ds = load_dataset(self.hf_repo, split=self.split, streaming=streaming)

        if not streaming and sample_size is not None:
            n = min(sample_size, len(ds))
            ds = ds.shuffle(seed=seed).select(range(n))

        count = 0
        for i, rec in enumerate(ds):
            title = _pick(rec, _TITLE_KEYS).strip()
            content = _pick(rec, _CONTENT_KEYS).strip()
            # if content missing, fall back to title (some THUCNews mirrors
            # only ship headlines)
            if not content:
                content = title
            if not title and not content:
                continue
            yield {
                "doc_id": f"thucnews-{i:08d}",
                "title": title,
                "content": content,
                "publish_time": "",  # THUCNews has no per-article timestamp
                "source": "thucnews",
                "url": "",
                "lang": "zh",
                "category": _pick(rec, _LABEL_KEYS),
            }
            count += 1
            if streaming and sample_size is not None and count >= sample_size:
                break

        logger.info("THUCNews yielded %d docs", count)
