"""热点采集与分析管道 — 编排多源采集→存储→聚类→情感分析的完整流程

支持从多个热搜平台（百度、头条、Google Trends）并发采集，
统一聚类后使用多因子热度公式计算事件热度。
"""
from __future__ import annotations

import datetime
import logging
from typing import Dict, List

from src.main.python.providers.trending.base import (
    TrendingItem,
    get_trending_collector,
    list_trending_collectors,
)
from .clusterer import Clusterer
from .db_writer import DbWriter
from .sentiment_analyzer import SentimentAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 来源名称映射：API 参数 → 注册表 key
SOURCE_KEY_MAP = {
    "BAIDU": "baidu",
    "TOUTIAO": "toutiao",
    "GOOGLE_TRENDS": "google_trends",
    "GOOGLE": "google_trends",
}


def _resolve_source_key(source: str) -> str:
    """将 API 参数中的来源名映射到注册表 key"""
    return SOURCE_KEY_MAP.get(source.upper(), source.lower())


class HotspotPipeline:
    """一站式热点采集与分析管道

    使用方式：
        pipeline = HotspotPipeline()
        result = pipeline.run()                          # 默认只用百度
        result = pipeline.run(sources=["baidu", "toutiao"])  # 多源采集
    """

    def __init__(self):
        self.clusterer = Clusterer(similarity_threshold=0.35)
        self.analyzer = SentimentAnalyzer()
        self.writer = DbWriter()

    # ------------------------------------------------------------------
    # 热度计算公式
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_heat(
        cluster_size: int,
        source_heats: List[float],
        pos_ratio: float,
        neg_ratio: float,
        neu_ratio: float,
        num_sources: int = 1,
    ) -> float:
        """多因子热度计算公式

        HEAT = 0.35×SOURCE_HEAT + 0.25×CLUSTER_SIZE + 0.25×CONTROVERSY + 0.15×MULTI_SOURCE

        F1 — SOURCE_HEAT (0-100)：数据源原始热度均值
            聚类内所有条目的 item.heat 取平均
        F2 — CLUSTER_SIZE (0-100)：聚类规模
            min(100, 新闻数 × 12 + 10)
        F3 — CONTROVERSY (0-100)：争议度（情感强度）
            100 × (1 - |pos% - neg%|) × (1 - neu%)
            正负观点越均分，争议度越高
        F4 — MULTI_SOURCE (0-100)：跨平台热度加成
            min(100, (来源数 - 1) × 40)
        """
        # F1: 数据源原始热度均值
        f1 = sum(source_heats) / len(source_heats) if source_heats else 50.0

        # F2: 聚类规模
        f2 = min(100.0, cluster_size * 12.0 + 10.0)

        # F3: 争议度
        opinion_divide = abs(pos_ratio - neg_ratio)
        f3 = 100.0 * (1.0 - opinion_divide) * (1.0 - neu_ratio)

        # F4: 跨平台热度加成
        f4 = min(100.0, (num_sources - 1) * 40.0)

        # 加权组合
        heat = 0.35 * f1 + 0.25 * f2 + 0.25 * f3 + 0.15 * f4
        return round(min(100.0, max(1.0, heat)), 1)

    # ------------------------------------------------------------------
    # 跨源去重
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate_cross_source(items: List[TrendingItem]) -> List[TrendingItem]:
        """跨源去重：标题高度相似的条目仅保留热度最高的一条

        使用简单的标题包含关系检测（比 TF-IDF 快，适合去重场景）。
        如果标题 A 完全包含在标题 B 中，或 B 包含在 A 中，视为重复。
        """
        if len(items) <= 1:
            return items

        # 按热度降序排列，保留热度更高的
        items = sorted(items, key=lambda x: x.heat, reverse=True)
        kept: List[TrendingItem] = []

        for item in items:
            is_dup = False
            for k in kept:
                # 标题包含关系检测
                if item.title in k.title or k.title in item.title:
                    is_dup = True
                    # 合并来源信息
                    if item.source_name != k.source_name:
                        k.raw_data.setdefault("also_from", []).append(item.source_name)
                    break
            if not is_dup:
                kept.append(item)

        return kept

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def run(self, sources: List[str] = None) -> Dict:
        """
        执行一次完整的多源采集→分析→存储流程。

        Args:
            sources: 采集来源列表，如 ["baidu", "toutiao"]。
                     默认 ["baidu"]，保持向后兼容。

        Returns:
            {
                "task_id": int,
                "sources": [...],
                "news_collected": int,
                "news_saved": int,
                "news_skipped": int,
                "hot_events": int,
                "hotspots": [...],
                "generated_at": "...",
            }
        """
        if sources is None:
            sources = ["baidu"]

        logger.info(f"========== 开始多源采集 | 来源: {sources} ==========")

        # ---- 1. 多源采集 ----
        all_items: List[TrendingItem] = []
        source_labels: List[str] = []

        for source_name in sources:
            collector = get_trending_collector(source_name)
            if collector is None:
                logger.warning(f"⚠️ 未知数据源: {source_name}，跳过")
                continue

            try:
                items = collector.fetch(limit=50)
                for item in items:
                    item.source_name = source_name
                all_items.extend(items)
                source_labels.append(source_name)
                logger.info(f"[{source_name}] 采集到 {len(items)} 条热搜")
            except Exception as e:
                logger.error(f"[{source_name}] 采集失败: {e}，继续处理其他来源")

        if not all_items:
            raise RuntimeError("所有来源均采集失败，无数据可处理")

        logger.info(f"总计采集 {len(all_items)} 条热搜（{len(source_labels)} 个来源）")

        # ---- 2. 跨源去重 ----
        unique_items = self._deduplicate_cross_source(all_items)
        dup_count = len(all_items) - len(unique_items)
        if dup_count > 0:
            logger.info(f"跨源去重: 移除 {dup_count} 条重复，保留 {len(unique_items)} 条")

        # ---- 3. 新闻入库 ----
        task_source_label = ",".join(s.upper() for s in source_labels)
        task_id = self.writer.create_collect_task(task_source_label)

        saved = 0
        skipped = 0
        saved_news_ids: List[int] = []
        saved_news_titles: List[str] = []
        saved_news_summaries: List[str] = []
        # 记录每条入库新闻的原始热度，用于后续热度计算
        saved_news_heats: List[float] = []
        saved_news_sources: List[str] = []

        for item in unique_items:
            display_source = f"{item.source_name.upper()}-热搜"
            nid = self.writer.insert_news(
                collect_task_id=task_id,
                title=item.title,
                summary=item.summary or item.title,
                source_name=display_source,
                source_url=item.url or "",
            )
            if nid:
                saved += 1
                saved_news_ids.append(nid)
                saved_news_titles.append(item.title)
                saved_news_summaries.append(item.summary or "")
                saved_news_heats.append(item.heat)
                saved_news_sources.append(item.source_name)
            else:
                skipped += 1

        logger.info(f"新闻入库: 新增 {saved} 条, 跳过(重复) {skipped} 条")
        self.writer.finish_collect_task(task_id, "success", len(unique_items), saved, skipped)

        # ---- 4. 热点聚类 ----
        clusters = self.clusterer.cluster(saved_news_titles, saved_news_summaries)
        logger.info(f"聚类结果: {len(clusters)} 个热点事件")

        # ---- 5. 情感分析 + 热度计算 + 入库 ----
        hotspots = []
        for cluster in clusters:
            cluster_titles = [saved_news_titles[i] for i in cluster.news_indices]

            # 情感分析
            sentiments = [self.analyzer.analyze(t) for t in cluster_titles]
            pos_c = sum(1 for s in sentiments if s["label"] == "pos")
            neg_c = sum(1 for s in sentiments if s["label"] == "neg")
            neu_c = sum(1 for s in sentiments if s["label"] == "neu")
            total = max(pos_c + neg_c + neu_c, 1)
            overall = "neg" if neg_c > pos_c else ("pos" if pos_c > neg_c else "neu")

            # 统计聚类内的来源分布
            cluster_sources: set = set()
            cluster_heats: List[float] = []
            for idx in cluster.news_indices:
                if idx < len(saved_news_sources):
                    cluster_sources.add(saved_news_sources[idx])
                if idx < len(saved_news_heats):
                    cluster_heats.append(saved_news_heats[idx])

            # 新热度公式
            heat_score = self._calculate_heat(
                cluster_size=len(cluster.news_indices),
                source_heats=cluster_heats if cluster_heats else [50.0],
                pos_ratio=pos_c / total,
                neg_ratio=neg_c / total,
                neu_ratio=neu_c / total,
                num_sources=len(cluster_sources),
            )

            # 关键词提取
            keywords = self.clusterer.extract_keywords(cluster_titles, top_k=5)

            # 关联的 news_id
            cluster_news_ids = [saved_news_ids[i] for i in cluster.news_indices]

            # 写入热点事件
            event_id = self.writer.insert_hot_event(
                event_title=cluster.event_name,
                heat_score=heat_score,
                sentiment_label=overall,
                news_count=len(cluster.news_indices),
                news_ids=cluster_news_ids,
            )

            # 写入情感分析
            self.writer.insert_sentiment(event_id, pos_c, neu_c, neg_c, overall)

            # 写入关键词
            self.writer.insert_keywords(event_id, keywords)

            hotspots.append({
                "rank": len(hotspots) + 1,
                "name": cluster.event_name,
                "heat": round(heat_score, 1),
                "news_count": len(cluster.news_indices),
                "source_count": len(cluster_sources),
                "sources": sorted(cluster_sources),
                "sentiment": {
                    "label": overall,
                    "pos_count": pos_c,
                    "neg_count": neg_c,
                    "neu_count": neu_c,
                },
                "keywords": [{"word": w, "weight": wt} for w, wt in keywords],
            })

        logger.info(f"========== 采集完成: {len(hotspots)} 个热点 ==========")
        return {
            "task_id": task_id,
            "sources": source_labels,
            "news_collected": len(unique_items),
            "news_saved": saved,
            "news_skipped": skipped,
            "hot_events": len(hotspots),
            "hotspots": hotspots,
            "generated_at": datetime.datetime.now().isoformat(),
        }
