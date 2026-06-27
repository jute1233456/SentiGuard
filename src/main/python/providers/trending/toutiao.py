"""头条热榜数据采集器

通过今日头条热榜 JSON API 获取实时热搜数据。
API: https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc
"""
from __future__ import annotations

import logging
import math
from typing import List

import requests

from src.main.python.providers.trending.base import (
    BaseTrendingCollector,
    TrendingItem,
    register_trending_collector,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.toutiao.com/",
}


class ToutiaoCollector(BaseTrendingCollector):
    """头条热榜采集器 — 通过头条 JSON API 获取实时热点"""

    SOURCE_NAME = "toutiao"
    API_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
    DEFAULT_LIMIT = 50

    def fetch(self, limit: int = DEFAULT_LIMIT) -> List[TrendingItem]:
        """
        拉取头条实时热榜。

        Args:
            limit: 返回热搜数量上限（默认50）

        API 返回格式：
            {
                "data": [
                    {
                        "ClusterId": 7655263058239000110,
                        "Title": "高考分数线全部公布",
                        "Label": "hot",         // "hot" | "new" | ""
                        "LabelDesc": "突发",
                        "Url": "https://www.toutiao.com/trending/.../",
                        "HotValue": "25776988",  // 绝对热度值（字符串）
                        "InterestCategory": ["education"],
                        "Image": {...},
                    },
                    ...
                ],
                "fixed_top_data": [...],
                "status": "success"
            }
        """
        try:
            resp = requests.get(self.API_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"❌ 头条热榜请求失败: {e}")
            raise RuntimeError(f"未能从头条热榜获取数据: {e}")
        except ValueError as e:
            logger.error(f"❌ 头条热榜 JSON 解析失败: {e}")
            raise RuntimeError(f"头条热榜返回数据格式异常: {e}")

        if data.get("status") != "success" and "data" not in data:
            logger.error(f"❌ 头条热榜 API 返回异常状态: {data.get('message', '未知错误')}")
            raise RuntimeError(f"头条热榜 API 异常: {data.get('message', '未知错误')}")

        raw_items = data.get("data", [])
        if not raw_items:
            logger.warning("⚠️ 头条热榜返回空数据")
            return []

        items = self._build_trending_items(raw_items, limit)

        logger.info(
            f"✅ 头条热榜采集成功 | 共获取 {len(items)} 条热搜"
        )
        for item in items[:5]:
            logger.info(f"   #{item.rank} {item.title} (热度:{item.heat})")

        return items

    def _build_trending_items(self, raw_items: list, limit: int) -> List[TrendingItem]:
        """将头条 API 原始数据转为统一的 TrendingItem 列表"""
        items: List[TrendingItem] = []

        for idx, raw in enumerate(raw_items[:limit]):
            if not isinstance(raw, dict):
                continue

            # 提取标题
            title = (raw.get("Title") or raw.get("title") or "").strip()
            if not title or len(title) < 2:
                continue

            # 提取 URL
            url = raw.get("Url") or raw.get("url") or ""
            if not url:
                cluster_id = raw.get("ClusterId") or raw.get("ClusterIdStr") or ""
                if cluster_id:
                    url = f"https://www.toutiao.com/trending/{cluster_id}/"
                else:
                    url = f"https://www.toutiao.com/search/?keyword={title}"

            # 提取热度值（HotValue 是字符串形式的绝对数值，如 "25776988"）
            hot_value_raw = raw.get("HotValue") or raw.get("hotValue") or 0
            heat = self._normalize_hot_value(hot_value_raw, idx)

            # 提取摘要
            summary = (
                raw.get("LabelDesc")
                or raw.get("Desc")
                or raw.get("desc")
                or ""
            ).strip()

            # 提取标签和分类
            label = raw.get("Label") or raw.get("label") or ""
            categories = raw.get("InterestCategory") or []

            items.append(TrendingItem(
                rank=idx + 1,
                title=title,
                heat=round(heat, 1),
                url=url,
                summary=summary,
                source_name=self.SOURCE_NAME,
                raw_data={
                    "hot_value_raw": hot_value_raw,
                    "label": label,
                    "cluster_id": raw.get("ClusterId") or raw.get("ClusterIdStr"),
                    "categories": categories,
                },
            ))

        return items

    def _normalize_hot_value(self, raw_value, rank: int) -> float:
        """将头条 HotValue 归一化到 0-100

        头条 HotValue 是绝对数值字符串（如 "25776988" = 约 2577 万），
        使用对数映射到 0-100：
            heat = min(100, (log10(value) - 4.0) * 25)

        映射参考：
            1万   (log10=4.0)  → 0
            10万  (log10=5.0)  → 25
            100万 (log10=6.0)  → 50
            1000万(log10=7.0)  → 75
            1亿   (log10=8.0)  → 100

        如果 raw_value 为 0 或无效，回退到排名估算。
        """
        try:
            value = float(str(raw_value)) if not isinstance(raw_value, (int, float)) else float(raw_value)
        except (ValueError, TypeError):
            return self._estimate_by_rank(rank)

        if value <= 0:
            return self._estimate_by_rank(rank)

        # 如果值已经在 0-100 范围内，直接使用
        if value <= 100:
            return value

        # 对数映射：log10(10000)=4.0 作为基线
        try:
            log_val = math.log10(value)
            heat = min(100.0, max(1.0, (log_val - 4.0) * 25.0))
            return round(heat, 1)
        except (ValueError, TypeError):
            return self._estimate_by_rank(rank)

    def _estimate_by_rank(self, rank: int) -> float:
        """根据排名估算热度分（0-100）— 回退方案"""
        return round(max(100.0 - (rank - 1) * 1.8, 10.0), 1)


# 自注册到全局注册表
register_trending_collector("toutiao", ToutiaoCollector)
