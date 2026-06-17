"""Base classes and helpers for data sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Iterator

import pandas as pd

from ..config import DOC_COLUMNS


class BaseDataSource(ABC):
    """Every data source produces an iterable of dicts conforming to DOC_COLUMNS."""

    name: str = "base"

    @abstractmethod
    def iter_docs(self, **kwargs) -> Iterator[dict]:
        """Yield documents one by one as dicts with keys = DOC_COLUMNS."""
        raise NotImplementedError

    def to_dataframe(self, **kwargs) -> pd.DataFrame:
        """Materialize all documents into a DataFrame with the unified schema."""
        rows = list(self.iter_docs(**kwargs))
        df = pd.DataFrame(rows, columns=DOC_COLUMNS)
        return _normalize(df)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Force schema, fill missing columns with empty strings, deduplicate by doc_id."""
    for col in DOC_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[DOC_COLUMNS].copy()
    # cast everything except publish_time to str so CSV round-trips cleanly
    for col in DOC_COLUMNS:
        if col == "publish_time":
            continue
        df[col] = df[col].fillna("").astype(str)
    df["publish_time"] = df["publish_time"].fillna("").astype(str)
    df = df.drop_duplicates(subset=["doc_id"], keep="first").reset_index(drop=True)
    return df


def merge_sources(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate multiple source frames into one normalized frame."""
    df = pd.concat(list(frames), ignore_index=True)
    return _normalize(df)
