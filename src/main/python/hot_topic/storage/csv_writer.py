"""CSV writer with append + de-dup semantics.

Why a small helper?  GDELT runs are incremental (every N minutes) and we want
to merge new pulls into the existing CSV without losing rows or creating
duplicates.  Pandas' to_csv has no built-in upsert, so we wrap it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import pandas as pd

from ..config import CSV_ENCODING, DOC_COLUMNS

logger = logging.getLogger(__name__)


def write_csv(df: pd.DataFrame, path: Union[str, Path], append: bool = False) -> Path:
    """Write `df` to `path`.

    * `append=False` (default): overwrite.
    * `append=True`: read existing, concat, drop_duplicates on doc_id, then
      write back.  Robust to missing/empty target file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # enforce schema column order
    for col in DOC_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[DOC_COLUMNS]

    if append and path.exists() and path.stat().st_size > 0:
        try:
            existing = pd.read_csv(path, encoding=CSV_ENCODING, dtype=str).fillna("")
            combined = pd.concat([existing, df], ignore_index=True)
            before = len(combined)
            combined = combined.drop_duplicates(subset=["doc_id"], keep="last")
            after = len(combined)
            logger.info(
                "append: existing=%d new=%d merged=%d deduped=%d",
                len(existing), len(df), before, before - after,
            )
            df = combined
        except Exception as e:
            logger.warning("failed to read existing %s (%s); overwriting", path, e)

    df.to_csv(path, index=False, encoding=CSV_ENCODING)
    logger.info("wrote %d rows -> %s", len(df), path)
    return path
