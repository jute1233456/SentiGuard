#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜索服务模块 — 统一封装两种搜索策略。

遵循开闭原则：
- 新增搜索引擎 → 只需在 search_anspire.py 中注册（register_search_engine）
- 新增搜索策略 → 只需在本模块新增函数
- 不修改 BaseSearchEngine / SearchEngineRetriever 等既有代码

两种策略：
1. search_summary()  — 摘要搜索，直接调搜索引擎取全部结果的 title/snippet，快（无 Selenium）
2. search_fulltext() — 全文搜索，对每条结果用 Selenium 抓取正文 + LLM 抽取，慢但详细
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from src.main.python.tools.search_base import get_search_engine, list_search_engines

logger = logging.getLogger("search_service")


def _normalize_score_value(value) -> Optional[int]:
    """将分数归一化到 0-100 整数。"""
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number <= 1:
            number *= 100
        return max(0, min(100, round(number)))
    except (TypeError, ValueError):
        return None


def _get_engine():
    """获取当前注册的第一个可用搜索引擎实例（兜底：遍历全部注册引擎）。"""
    available = list_search_engines()
    if not available:
        logger.warning("无可用搜索引擎（注册表为空）")
        return None

    for name in available:
        engine = get_search_engine(name)
        if engine and engine.is_available():
            return engine
        logger.debug("搜索引擎 '%s' 不可用，尝试下一个", name)

    logger.warning("所有搜索引擎均不可用（共 %d 个: %s）", len(available), available)
    return None


# ======================================================================
# SearchEngineRetriever 缓存 — 避免重复创建 Selenium WebDriver
# ======================================================================

_RETRIEVER_CACHE: dict[str, "SearchEngineRetriever"] = {}


def _get_retriever(dataset: str) -> "SearchEngineRetriever":
    """获取或创建 SearchEngineRetriever 缓存实例（按 dataset 缓存）。"""
    if dataset not in _RETRIEVER_CACHE:
        from src.main.python.tools.retrieve import SearchEngineRetriever
        _RETRIEVER_CACHE[dataset] = SearchEngineRetriever(dataset)
    return _RETRIEVER_CACHE[dataset]


# ======================================================================
# 摘要搜索模式
# ======================================================================

def search_summary(query: str, num_results: int = 10) -> list:
    """摘要搜索模式：直接调搜索引擎，取全部结果的 title/snippet → F3EvidenceItem 列表。

    快（无 Selenium），适合标准 FactAgent 的 LangGraph @tool 使用。

    Args:
        query: 搜索查询语句。
        num_results: 返回结果数量，默认 10。

    Returns:
        List[dict]: 每项含 title/url/snippet/content/source/score 的 dict 列表。
                    失败时返回空列表。
    """
    from src.main.python.api.schemas import F3EvidenceItem

    engine = _get_engine()
    if not engine:
        return []

    try:
        results = engine.search(query, num_results=num_results)
    except Exception as e:
        logger.warning("摘要搜索失败: %s", e)
        return []

    if not results:
        return []

    seen_urls: set = set()
    items = []

    for r in results:
        url = r.url or ""
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        content = r.content or r.snippet or ""
        if not content:
            continue

        items.append(F3EvidenceItem(
            claimOrder=1,
            evidenceTitle=str(r.title or f"检索问题：{query}")[:200],
            evidenceContent=str(content)[:500],
            evidenceUrl=url,
            sourceName=str(r.source or "搜索检索结果")[:100],
            evidenceType="web",
            relationType="neutral",
            credibilityScore=_normalize_score_value(r.score),
        ))

    return items


# ======================================================================
# 全文搜索模式
# ======================================================================

def search_fulltext(query: str, dataset: str = "fever", num_results: int = 10,
                    default_relation: str = "neutral") -> list:
    """全文搜索模式：对每一条搜索结果都提取全文，转成 F3EvidenceItem 列表。

    复用 SearchEngineRetriever 的 Selenium 抓取 + LLM 抽取能力：
    - 先用搜索引擎拿到全部结果
    - 对每条结果用 Selenium 抓取网页正文
    - 用 LLM 抽取与查询相关的内容
    - 如果某条 URL 抓取失败或 LLM 抽取返回空，回退使用 snippet

    慢但详细，适合 ReflectiveFactAgent 的补充搜索。

    Args:
        query: 搜索查询语句。
        dataset: 数据集名称（用于日期限制），默认 "fever"。
        num_results: 返回结果数量，默认 10。
        default_relation: 证据 relationType 默认值，"neutral"/"support"/"attack"。

    Returns:
        List[F3EvidenceItem]: 证据列表。失败时返回空列表。
    """
    from src.main.python.api.schemas import F3EvidenceItem

    engine = _get_engine()
    if not engine:
        return []

    # 1. 先用搜索引擎拿原始结果
    try:
        raw_results = engine.search(query, num_results=num_results)
    except Exception as e:
        logger.warning("全文搜索-引擎查询失败: %s", e)
        return []

    if not raw_results:
        return []

    # 2. 复用 SearchEngineRetriever（模块级缓存，避免重复创建 Selenium WebDriver）
    retriever = _get_retriever(dataset)

    seen_urls: set = set()
    items: list = []

    for r in raw_results:
        url = r.url or ""
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        title = r.title or f"检索问题：{query}"
        snippet = r.snippet or ""

        # 尝试 Selenium 抓取 + LLM 抽取
        extracted_text = ""
        try:
            # 复用 URL 校验（retriever._check_valid_url）
            if retriever._check_valid_url(url):
                # 复用 Selenium 抓取
                content_sentences = retriever.get_details(url)
                if len(content_sentences) > 1:
                    article_content = (
                        f"Article Title: {title} \n"
                        f"Snippet: {snippet}\n"
                        f"Article Content: \n{content_sentences}"
                    )
                    extracted_text = retriever._process_content(query, article_content)
                if not extracted_text:
                    article_content = f"Article Title: {title} \nSnippet: {snippet}"
                    extracted_text = retriever._process_content(query, article_content)
        except Exception as e:
            logger.debug("  全文抓取失败 %s: %s", url, e)

        # 如果抓取/抽取失败，回退使用 snippet
        evidence_content = extracted_text or snippet
        if not evidence_content:
            continue

        items.append(F3EvidenceItem(
            claimOrder=1,
            evidenceTitle=str(title)[:200],
            evidenceContent=str(evidence_content)[:500],
            evidenceUrl=url,
            sourceName=str(r.source or "搜索检索结果")[:100],
            evidenceType="web",
            relationType=default_relation if default_relation in ("support", "attack", "neutral") else "neutral",
            credibilityScore=_normalize_score_value(r.score),
        ))

    logger.info("  全文搜索完成: %s → %d 条证据", query, len(items))
    return items


__all__ = ["search_summary", "search_fulltext"]
