"""Chinese text preprocessing for BERTopic.

- Clean text (remove noise, deduplicate spaces)
- Jieba tokenization with optional user-defined dictionaries
- Stopword handling
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Basic Chinese stopwords (you can extend this with a custom list)
_DEFAULT_CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "他", "她", "他们", "我们", "什么", "吗", "呢", "吧", "啊",
    "把", "被", "从", "到", "对", "对于", "关于", "跟", "和", "与", "同", "给",
    "让", "叫", "请", "把", "比", "像", "似的", "跟", "一样", "差不多",
    "个", "位", "件", "份", "条", "根", "块", "片", "页", "题", "行", "列",
    "是", "有", "在", "来", "去", "上", "下", "左", "右", "前", "后", "里",
    "将", "已经", "正在", "就要", "刚刚", "忽然", "突然", "刚刚", "终于",
    "但是", "可是", "不过", "然而", "因此", "所以", "于是", "结果",
    "啊", "哦", "嗯", "唉", "哇", "哈", "嘿", "哎呀",
}

# Regex patterns for cleaning
_WHITESPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_HTML_RE = re.compile(r"<[^>]+>")
_PUNC_RE = re.compile(r"[^\w一-鿿]+")


def clean_text(text: str) -> str:
    """Basic text cleaning: remove URLs, HTML tags, extra whitespace."""
    if not text or not isinstance(text, str):
        return ""
    text = _URL_RE.sub(" ", text)
    text = _HTML_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def chinese_tokenize(
    text: str,
    jieba_dict: Optional[Path] = None,
    stopwords: Optional[Set[str]] = None,
) -> str:
    """Tokenize Chinese text with jieba, keep only useful tokens."""
    try:
        import jieba
    except ImportError as e:
        raise ImportError("jieba is required for Chinese tokenization") from e

    if jieba_dict and jieba_dict.exists():
        jieba.load_userdict(str(jieba_dict))

    text = clean_text(text)
    if not text:
        return ""

    # Tokenize
    tokens = jieba.lcut(text)

    # Filter short tokens, stopwords, non-Chinese/non-alphanumeric
    if stopwords is None:
        stopwords = set()
    filtered: List[str] = []
    for token in tokens:
        token = token.strip()
        if len(token) < 1:
            continue
        if token in stopwords:
            continue
        # Keep either Chinese characters or alphanumeric (but not pure punctuation)
        if re.match(r"^[一-鿿]+$", token):
            filtered.append(token)
        elif re.match(r"^[a-zA-Z0-9]{2,}$", token):
            filtered.append(token.lower())

    return " ".join(filtered)


def build_stopwords(
    extra_stopwords: Optional[List[str]] = None,
    stopwords_path: Optional[Path] = None,
) -> Set[str]:
    """Build a stopword set from defaults + optional extra list/ file."""
    stops = set(_DEFAULT_CHINESE_STOPWORDS)
    if extra_stopwords:
        stops.update(extra_stopwords)
    if stopwords_path and stopwords_path.exists():
        with open(stopwords_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    stops.add(line)
    return stops


def preprocess_for_bertopic(
    texts: List[str],
    stopwords: Optional[Set[str]] = None,
    jieba_dict: Optional[Path] = None,
    min_len: int = 10,
) -> List[str]:
    """Preprocess a list of texts into tokenized strings for BERTopic.

    Args:
        texts: list of raw text strings.
        stopwords: set of stopwords to remove.
        jieba_dict: optional path to jieba custom dict.
        min_len: drop texts that result in tokenized string shorter than this.

    Returns:
        list of preprocessed, tokenized strings (space-separated tokens).
    """
    if stopwords is None:
        stopwords = build_stopwords()

    processed: List[str] = []
    skipped = 0
    for idx, text in enumerate(texts):
        tokenized = chinese_tokenize(text, jieba_dict=jieba_dict, stopwords=stopwords)
        if len(tokenized) < min_len:
            skipped += 1
            continue
        processed.append(tokenized)

    logger.info(
        "Preprocessed %d texts (%d skipped due to short length)",
        len(processed), skipped,
    )
    return processed
