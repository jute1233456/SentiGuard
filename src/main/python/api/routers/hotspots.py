"""H1 GET /internal/v1/hotspots — 热点列表接口（MySQL 数据源）"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)

from src.main.python.api.deps import verify_internal_token
from src.main.python.api.schemas import (
    ApiResponse,
    Hotspot,
    HotspotData,
    Keyword,
    Sentiment,
    SentimentDistribution,
)
from src.main.python.services.db import get_connection
from src.main.python.services.pipeline import HotspotPipeline

router = APIRouter(
    prefix="/internal/v1",
    tags=["hotspots"],
    dependencies=[Depends(verify_internal_token)],
)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# GET /hotspots — 从 MySQL 读取热点列表
# ---------------------------------------------------------------------------
@router.get(
    "/hotspots",
    response_model=ApiResponse[HotspotData],
    summary="获取热点列表（按热度排序，从 MySQL 读取）",
)
def list_hotspots(
    limit: int = Query(20, ge=1, le=100, description="返回热点数量上限"),
    from_: str | None = Query(None, alias="from", description="时间窗口起点 ISO8601"),
    to: str | None = Query(None, description="时间窗口终点 ISO8601"),
    topK: int = Query(5, ge=1, le=20, description="每个热点返回前 K 个关键词"),
) -> ApiResponse[HotspotData]:
    now = datetime.now(timezone.utc)
    window_to = _parse_iso(to) if to else now
    window_from = _parse_iso(from_) if from_ else window_to - timedelta(hours=24)

    if window_from >= window_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40001, "message": "`from` must be earlier than `to`"},
        )

    # 从 MySQL 读取热点事件（按热度降序）
    hotspots = _load_hotspots_from_db(window_from, window_to, limit, topK)

    data = HotspotData(
        generatedAt=_iso_utc(now),
        windowFrom=_iso_utc(window_from),
        windowTo=_iso_utc(window_to),
        hotspots=hotspots,
    )
    return ApiResponse[HotspotData](data=data)


# ---------------------------------------------------------------------------
# POST /collect — 手动触发采集
# ---------------------------------------------------------------------------
@router.post(
    "/collect",
    response_model=ApiResponse[dict],
    summary="手动触发多源热搜采集与分析",
)
def trigger_collect(
    sources: str = Query("BAIDU", description="采集来源，逗号分隔：BAIDU,TOUTIAO,GOOGLE_TRENDS"),
) -> ApiResponse[dict]:
    # 解析来源参数
    SOURCE_KEY_MAP = {
        "BAIDU": "baidu",
        "TOUTIAO": "toutiao",
        "GOOGLE_TRENDS": "google_trends",
        "GOOGLE": "google_trends",
    }
    source_list = [
        SOURCE_KEY_MAP.get(s.strip().upper(), s.strip().lower())
        for s in sources.split(",") if s.strip()
    ]

    try:
        pipeline = HotspotPipeline()
        result = pipeline.run(sources=source_list)

        # ── 控制台输出采集简报 ──
        logger.info(
            f"📡 热点采集完成 | 来源: {sources} | "
            f"采集 {result['news_collected']} 条 | "
            f"入库 {result['news_saved']} 条 | "
            f"发现 {result['hot_events']} 个热点"
        )
        for h in result.get("hotspots", []):
            logger.info(
                f"  🔥 #{h['rank']} {h['name']} "
                f"(热度:{h['heat']}, "
                f"情感:{h['sentiment']['label']}, "
                f"关联 {h['news_count']} 条新闻)"
            )

        return ApiResponse[dict](
            code=0,
            message=f"采集完成：新增 {result['news_saved']} 条新闻，发现 {result['hot_events']} 个热点",
            data=result,
        )
    except Exception as e:
        logger.error(f"❌ 热点采集失败: {e}", exc_info=True)
        return ApiResponse[dict](
            code=50001,
            message=f"采集失败: {e}",
            data=None,
        )


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------
def _load_hotspots_from_db(
    window_from: datetime,
    window_to: datetime,
    limit: int,
    top_k: int,
) -> list[Hotspot]:
    """从 MySQL 查询热点事件并组装为 Hotspot 列表"""
    sql_events = """
        SELECT id, event_title, heat_score, risk_level, sentiment_label, news_count
        FROM hot_event
        WHERE is_deleted = 0
          AND create_time >= %s
          AND create_time <= %s
        ORDER BY heat_score DESC
        LIMIT %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_events, (window_from, window_to, limit))
            events = cur.fetchall()

            if not events:
                return []

            hotspots = []
            for rank, row in enumerate(events, start=1):
                event_id = row[0]
                event_title = row[1]
                heat_score = float(row[2])
                sentiment_label = row[4] if row[4] else "neu"

                # 关键词
                keywords = _load_keywords(cur, event_id, top_k)

                # 情感分布
                sentiment = _load_sentiment(cur, event_id, sentiment_label)

                hotspots.append(
                    Hotspot(
                        rank=rank,
                        name=event_title,
                        heat=min(heat_score, 100.0),
                        keywords=keywords,
                        sentiment=sentiment,
                    )
                )
            return hotspots


def _load_keywords(cur, event_id: int, top_k: int) -> list[Keyword]:
    cur.execute(
        "SELECT keyword, weight FROM topic_keyword WHERE hot_event_id=%s ORDER BY rank_no LIMIT %s",
        (event_id, top_k),
    )
    return [Keyword(word=row[0], weight=float(row[1])) for row in cur.fetchall()]


def _load_sentiment(cur, event_id: int, default_label: str) -> Sentiment:
    cur.execute(
        """SELECT positive_count, negative_count, neutral_count,
                  positive_ratio, negative_ratio, neutral_ratio, sentiment_label
           FROM sentiment_analysis WHERE hot_event_id=%s LIMIT 1""",
        (event_id,),
    )
    row = cur.fetchone()
    if row:
        total = max(row[0] + row[1] + row[2], 1)
        pos_ratio = round(row[0] / total, 2) if total else 0.0
        neg_ratio = round(row[1] / total, 2) if total else 0.0
        neu_ratio = round(row[2] / total, 2) if total else 0.0
        label = row[6] or default_label
        score = round(neg_ratio * -1 + pos_ratio, 2)  # -1~1 的综合得分
        return Sentiment(
            label=label if label in ("pos", "neg", "neu") else default_label,
            score=score,
            distribution=SentimentDistribution(pos=pos_ratio, neg=neg_ratio, neu=neu_ratio),
        )

    # 无情感数据时返回默认值
    return Sentiment(
        label=default_label if default_label in ("pos", "neg", "neu") else "neu",
        score=0.0,
        distribution=SentimentDistribution(pos=0.0, neg=0.0, neu=1.0),
    )


def _parse_iso(value: str) -> datetime:
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 40001, "message": f"invalid datetime: {value}"},
        ) from exc
