"""百度热搜数据采集器"""
from __future__ import annotations

import json
import logging
import re
from typing import List

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://top.baidu.com/board?tab=realtime",
}


class BaiduHotItem:
    """百度热搜单条数据"""

    def __init__(self, rank: int, title: str, heat: float, url: str = "", summary: str = ""):
        self.rank = rank
        self.title = title
        self.heat = heat
        self.url = url
        self.summary = summary

    def __repr__(self) -> str:
        return f"#{self.rank} {self.title} (热度:{self.heat})"


class BaiduCollector:
    """百度热搜采集器 — 通过百度内部 API 提取实时热点"""

    API_URL = "https://top.baidu.com/api/board?platform=wise&tab=realtime"

    def fetch(self) -> List[BaiduHotItem]:
        """
        拉取百度实时热搜榜单。

        优先使用 API JSON 接口，失败时回退到页面 HTML 解析。
        """
        # 方式 1: API JSON 接口
        try:
            resp = requests.get(self.API_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            items = self._parse_api_json(resp.text)
            if items:
                logger.info(
                    f"✅ 百度热搜采集成功 | API JSON 接口 | "
                    f"共获取 {len(items)} 条热搜"
                )
                for item in items[:5]:
                    logger.info(f"   #{item.rank} {item.title} (热度:{item.heat})")
                return items
            logger.warning("⚠️ API JSON 接口返回空数据，尝试 HTML 回退方案")
        except requests.RequestException as e:
            logger.warning(f"⚠️ API JSON 接口请求失败: {e}，尝试 HTML 回退方案")

        # 方式 2: 回退到 HTML 页面解析
        try:
            resp = requests.get(
                "https://top.baidu.com/board?tab=realtime",
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            items = self._parse_html(resp.text)
            if items:
                logger.info(
                    f"✅ 百度热搜采集成功 | HTML 回退方案 | "
                    f"共获取 {len(items)} 条热搜"
                )
                for item in items[:5]:
                    logger.info(f"   #{item.rank} {item.title} (热度:{item.heat})")
                return items
            logger.warning("⚠️ HTML 回退方案也未获取到数据")
        except requests.RequestException as e:
            logger.error(f"❌ HTML 回退方案请求也失败: {e}")

        logger.error("❌ 百度热搜采集彻底失败：所有方式均未获取到数据")
        raise RuntimeError("未能从百度热搜获取到任何数据")

    def _parse_api_json(self, text: str) -> List[BaiduHotItem]:
        """解析 API JSON 返回格式"""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        if not data.get("success") or "data" not in data:
            return []

        # 找到包含热搜词的 cards
        cards = data["data"].get("cards", [])
        items: List[BaiduHotItem] = []

        for card in cards:
            content_list = card.get("content", [])
            for content_block in content_list:
                for item in content_block.get("content", []):
                    word = item.get("word", "").strip()
                    if not word or len(word) < 2:
                        continue
                    url = item.get("url", "")
                    # 提取热度标签：hotTag 表示热度等级，"1"=热，"2"=爆
                    hot_tag = item.get("hotTag", "0")
                    # 基于 hotTag 和 index 计算热度分
                    index = item.get("index", len(items) + 1)
                    heat = self._estimate_heat(index, hot_tag)

                    # 提取摘要（如果有 desc 字段）
                    desc = item.get("desc", "")

                    items.append(BaiduHotItem(
                        rank=len(items) + 1,
                        title=word,
                        heat=heat,
                        url=url if url else f"https://www.baidu.com/s?wd={word}",
                        summary=desc,
                    ))

        return items[:50]

    def _estimate_heat(self, index: int, hot_tag: str) -> float:
        """根据排名和热度标签估算热度分（0-100）"""
        base = max(100.0 - (index - 1) * 1.8, 10.0)
        if hot_tag == "2":
            base = min(base * 1.3, 100.0)
        elif hot_tag == "1":
            base = min(base * 1.1, 100.0)
        return round(base, 1)

    def _parse_html(self, html: str) -> List[BaiduHotItem]:
        """回退方案：解析 HTML 中的嵌入 JSON 数据"""
        items: List[BaiduHotItem] = []

        # 尝试找 window.__PRELOADED_STATE__
        match = re.search(
            r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});',
            html, re.DOTALL
        )
        if match:
            try:
                data = json.loads(match.group(1))
                cards = data.get("data", {}).get("cards", [])
                for card in cards:
                    for content_block in card.get("content", []):
                        for item in content_block.get("content", []):
                            word = item.get("word", "").strip()
                            if not word:
                                continue
                            idx = item.get("index", len(items) + 1)
                            hot_tag = item.get("hotTag", "0")
                            items.append(BaiduHotItem(
                                rank=len(items) + 1,
                                title=word,
                                heat=self._estimate_heat(idx, hot_tag),
                                url=item.get("url", ""),
                                summary=item.get("desc", ""),
                            ))
                return items[:50]
            except (json.JSONDecodeError, KeyError):
                pass

        # 尝试找其他 JSON 数据模式
        for pattern in [r'<!--\s*s-data\s*-->\s*<script[^>]*>\s*(\{.*?\})\s*</script>']:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    cards = data.get("data", {}).get("cards", [])
                    for card in cards:
                        for content in card.get("content", []):
                            word = content.get("word", "") or content.get("query", "")
                            if not word:
                                continue
                            items.append(BaiduHotItem(
                                rank=len(items) + 1,
                                title=word,
                                heat=float(content.get("hotScore", 50)),
                                url=content.get("url", ""),
                                summary=content.get("desc", ""),
                            ))
                    return items[:50]
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        return []
