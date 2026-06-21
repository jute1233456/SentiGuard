"""Pydantic 数据模型，对应 docs/api/internal-api.md 中定义的请求 / 响应结构。

字段定义与文档保持一一对应；后续如需扩展字段，请同步修改文档与本文件。
"""
from __future__ import annotations

from typing import Any, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 通用响应包装
# ---------------------------------------------------------------------------
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


# ---------------------------------------------------------------------------
# H1 GET /internal/v1/hotspots
# ---------------------------------------------------------------------------
class Keyword(BaseModel):
    word: str
    weight: float = Field(..., ge=0.0, le=1.0)


class SentimentDistribution(BaseModel):
    pos: float = Field(..., ge=0.0, le=1.0)
    neg: float = Field(..., ge=0.0, le=1.0)
    neu: float = Field(..., ge=0.0, le=1.0)


class Sentiment(BaseModel):
    label: Literal["pos", "neg", "neu"]
    score: float = Field(..., ge=-1.0, le=1.0)
    distribution: SentimentDistribution


class Hotspot(BaseModel):
    rank: int = Field(..., ge=1)
    name: str
    heat: float = Field(..., ge=0.0, le=100.0)
    keywords: List[Keyword]
    sentiment: Sentiment


class HotspotData(BaseModel):
    generatedAt: str
    windowFrom: str
    windowTo: str
    hotspots: List[Hotspot]


# ---------------------------------------------------------------------------
# F1 POST /internal/v1/fact-check
# ---------------------------------------------------------------------------
class FactCheckRequest(BaseModel):
    claim: str = Field(..., min_length=1, max_length=2000)


class FactCheckData(BaseModel):
    isTrue: bool
    conclusion: str
    explanation: str


# ---------------------------------------------------------------------------
# F2 POST /internal/v1/fact-check/detail（详细版，含推理过程与证据）
# ---------------------------------------------------------------------------
class EvidenceItem(BaseModel):
    """单条证据：子声明 → 搜索查询 → 选中 URL → 证据摘要"""
    subclaim: str = ""
    query: str = ""
    chosenUrl: str = ""
    evidenceSnippet: str = ""


class TraceStep(BaseModel):
    """单个推理步骤（节点名 + 结构化输出）"""
    node: str
    output: Any  # structured_response，dict 或 list


class TraceRoute(BaseModel):
    """Supervisor 路由记录"""
    graph: str
    next: str


class FactCheckTrace(BaseModel):
    """完整推理路径"""
    runId: str = ""
    claim: str = ""
    route: List[TraceRoute] = []
    steps: List[TraceStep] = []
    searches: List[EvidenceItem] = []
    verdict: Optional[dict] = None


class FactCheckDetailData(BaseModel):
    """F2 响应 data — 含 F1 三字段 + 推理过程 + 证据"""
    isTrue: bool
    conclusion: str
    explanation: str
    trace: FactCheckTrace
    evidenceItems: List[EvidenceItem] = []
