"""Google Trends 热搜数据采集器

Google Trends 有两种获取方式：
    1. RSS Feed（公开，无需 key）: https://trends.google.com/trending/rss?geo=US
       返回 XML 格式，包含每日/实时热搜词
    2. pytrends 库（非官方，需要 auth）

这里使用 RSS Feed 方式，简单可靠，无需认证。
支持通过 geo 参数切换区域：US / CN / JP / GB 等。
"""
from __future__ import annotations

import logging
import re
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
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 常用区域代码
GEO_MAP = {
    "us": "US",
    "cn": "CN",
    "jp": "JP",
    "gb": "GB",
    "global": "US",  # global defaults to US
}


class GoogleTrendsCollector(BaseTrendingCollector):
    """Google Trends 采集器 — 通过 RSS Feed 提取热门搜索词"""

    SOURCE_NAME = "google_trends"
    RSS_URL = "https://trends.google.com/trending/rss"
    DEFAULT_GEO = "US"
    DEFAULT_LIMIT = 100

    # 已知不可用的区域（RSS 直接拒接 400/404），遇这些区自动回退 US
    UNSUPPORTED_GEOS = {"CN", "IR", "KP", "CU", "SY", "SD"}

    def __init__(self, geo: str = DEFAULT_GEO):
        geo = GEO_MAP.get(geo.lower(), geo.upper())
        if geo in self.UNSUPPORTED_GEOS:
            logger.warning(
                "Google Trends RSS 不支持 geo=%s（Google 服务不可达），自动回退 US", geo
            )
            geo = "US"
        self.geo = geo

    def fetch(self, limit: int = DEFAULT_LIMIT) -> List[TrendingItem]:
        """拉取 Google Trends 热门搜索 RSS feed。

        Args:
            limit: 返回热搜数量上限（默认100）
        """
        # 方式 1: RSS feed
        try:
            resp = requests.get(
                self.RSS_URL,
                params={"geo": self.geo},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            items = self._parse_rss(resp.text, limit)
            if items:
                logger.info(
                    f"✅ Google Trends 采集成功 | geo={self.geo} | "
                    f"共获取 {len(items)} 条热搜"
                )
                for item in items[:5]:
                    logger.info(f"   #{item.rank} {item.title} (热度:{item.heat})")
                return items
            logger.warning("⚠️ Google Trends RSS 返回空数据")
        except requests.RequestException as e:
            logger.error(f"❌ Google Trends RSS 请求失败: {e}")

        # 方式 2: 尝试 daily trends RSS
        try:
            daily_url = "https://trends.google.com/trends/trendingsearches/daily/rss"
            resp = requests.get(
                daily_url,
                params={"geo": self.geo},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            items = self._parse_rss(resp.text, limit)
            if items:
                logger.info(
                    f"✅ Google Trends (daily) 采集成功 | geo={self.geo} | "
                    f"共获取 {len(items)} 条热搜"
                )
                return items
        except requests.RequestException as e:
            logger.error(f"❌ Google Trends daily RSS 也失败: {e}")

        raise RuntimeError(f"未能从 Google Trends (geo={self.geo}) 获取数据")

    def _parse_rss(self, xml_text: str, limit: int) -> List[TrendingItem]:
        """解析 Google Trends RSS XML 响应。

        RSS 结构：
            <rss>
              <channel>
                <item>
                  <title>热门搜索词</title>
                  <ht:approx_traffic>5000+</ht:approx_traffic>
                  <ht:news_item_url>https://...</ht:news_item_url>
                  <description>相关新闻...</description>
                </item>
              </channel>
            </rss>
        """
        items: List[TrendingItem] = []

        item_blocks = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)
        for i, block in enumerate(item_blocks[:limit]):
            # 提取标题
            title_match = re.search(r'<title>(.*?)</title>', block)
            if not title_match:
                continue
            title = title_match.group(1).strip()

            # 跳过 "Daily Search Trends" 这种头部项
            if "daily" in title.lower() or "trend" in title.lower():
                if i == 0:
                    continue

            # 提取热度（approx_traffic）
            traffic_match = re.search(
                r'<ht:approx_traffic>(.*?)</ht:approx_traffic>',
                block,
            )
            traffic_raw = traffic_match.group(1) if traffic_match else ""
            heat = self._parse_traffic(traffic_raw, i + 1)

            # 提取新闻链接
            url_match = re.search(r'<ht:news_item_url>(.*?)</ht:news_item_url>', block)
            url = url_match.group(1).strip() if url_match else ""
            if not url:
                url = f"https://trends.google.com/trends/explore?q={title}&geo={self.geo}"

            # 提取摘要
            desc_match = re.search(r'<description>(.*?)</description>', block)
            summary = desc_match.group(1).strip() if desc_match else ""

            items.append(TrendingItem(
                rank=i + 1,
                title=title,
                heat=heat,
                url=url,
                summary=summary,
                source_name=self.SOURCE_NAME,
                raw_data={"geo": self.geo, "traffic_raw": traffic_raw},
            ))

        return items

    def _parse_traffic(self, traffic_text: str, rank: int) -> float:
        """从 approx_traffic 文本解析热度分（0-100）。

        Google Trends 的 traffic 格式：
            "10,000+"  → 多热度
            "5,000+"   → 中等热度
            "2,000+"   → 一般热度
            "500+"     → 低热度
        """
        if not traffic_text:
            return self._estimate_by_rank(rank)

        cleaned = traffic_text.replace(",", "").replace("+", "").strip()
        try:
            raw = int(cleaned)
        except ValueError:
            return self._estimate_by_rank(rank)

        # 映射到 0-100
        if raw >= 10000:
            return round(min(100.0, 75.0 + (raw - 10000) / 10000 * 25), 1)
        elif raw >= 5000:
            return round(50.0 + (raw - 5000) / 5000 * 25.0, 1)
        elif raw >= 2000:
            return round(30.0 + (raw - 2000) / 3000 * 20.0, 1)
        else:
            return round(max(10.0, raw / 2000.0 * 30.0), 1)

    def _estimate_by_rank(self, rank: int) -> float:
        """根据排名估算热度分（0-100）"""
        return round(max(100.0 - (rank - 1) * 2.0, 10.0), 1)


# 自注册到全局注册表
register_trending_collector("google_trends", GoogleTrendsCollector)
