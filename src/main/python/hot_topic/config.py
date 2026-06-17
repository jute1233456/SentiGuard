"""Configuration for hot_topic module.

Centralizes all paths and API parameters so they can be overridden via
environment variables without touching code.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# repo root: SentiGuard/
_THIS = Path(__file__).resolve()
REPO_ROOT = _THIS.parents[4]  # hot_topic -> python -> main -> src -> SentiGuard
DATA_DIR = Path(os.environ.get("HOTTOPIC_DATA_DIR", REPO_ROOT / "data" / "hot_topic"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Unified document schema (every data source must produce these columns)
# ---------------------------------------------------------------------------
DOC_COLUMNS = [
    "doc_id",       # unique id (source-prefixed)
    "title",        # headline / first sentence
    "content",      # body text (may equal title for sources without body)
    "publish_time", # ISO 8601 string in UTC
    "source",       # data source name: "thucnews" / "gdelt"
    "url",          # original url ("" for offline corpora)
    "lang",         # ISO 639-1 code, e.g. "zh"
    "category",     # optional source-provided label ("" if absent)
]

# ---------------------------------------------------------------------------
# THUCNews (HuggingFace datasets)
# ---------------------------------------------------------------------------
# Default to a public mirror of THUCNews on HF.  Override via env if needed.
THUCNEWS_HF_REPO = os.environ.get("THUCNEWS_HF_REPO", "madao33/new-title-chinese")
THUCNEWS_HF_SPLIT = os.environ.get("THUCNEWS_HF_SPLIT", "train")
THUCNEWS_DEFAULT_SAMPLE = int(os.environ.get("THUCNEWS_DEFAULT_SAMPLE", "10000"))
THUCNEWS_OUTPUT = DATA_DIR / "thucnews_sample.csv"

# ---------------------------------------------------------------------------
# GDELT DOC 2.0
# ---------------------------------------------------------------------------
GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_DEFAULT_QUERY = os.environ.get("GDELT_DEFAULT_QUERY", "sourcelang:chinese")
GDELT_DEFAULT_TIMESPAN = os.environ.get("GDELT_DEFAULT_TIMESPAN", "24h")
GDELT_MAX_RECORDS_PER_CALL = 250  # API hard cap
GDELT_REQUEST_TIMEOUT = 30
GDELT_RETRY_ATTEMPTS = 3
GDELT_RETRY_BACKOFF = 2.0  # seconds, exponential
# GDELT enforces ~1 req / 5 s; we keep a small safety margin.
GDELT_MIN_INTERVAL = float(os.environ.get("GDELT_MIN_INTERVAL", "5.5"))
GDELT_USER_AGENT = "SentiGuard-HotTopic/0.1 (+research)"

# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------
# UTF-8-SIG so Excel can open without garbled characters.
CSV_ENCODING = "utf-8-sig"
