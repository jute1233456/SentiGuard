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


# ---------------------------------------------------------------------------
# F3 POST /internal/v1/fact-check/detail/db — 数据库对齐版
# ---------------------------------------------------------------------------
class F3ClaimItem(BaseModel):
    """单条可核查声明，对应 fact_claim 表"""
    claimOrder: int = Field(..., ge=1, description="声明顺序，从 1 递增")
    claimText: str = Field(..., description="拆解后的可核查声明文本")
    claimType: str = Field(default="verifiable", description="声明类型：verifiable / non-verifiable")


class F3EvidenceItem(BaseModel):
    """单条证据，对应 evidence 表"""
    claimOrder: int = Field(..., ge=1, description="关联声明的 claimOrder")
    evidenceTitle: str = Field(default="", description="证据标题")
    evidenceContent: str = Field(default="", description="证据摘要或原文片段")
    evidenceUrl: str = Field(default="", description="证据来源链接")
    sourceName: str = Field(default="", description="来源名称/域名")
    evidenceType: str = Field(default="web", description="证据类型：web/news/official/model_generated")
    relationType: str = Field(default="support", description="论辩关系：support/attack/neutral")
    credibilityScore: Optional[int] = Field(default=None, ge=0, le=100, description="可信度评分 0-100")
    publishTime: Optional[str] = Field(default=None, description="发布时间，格式 yyyy-MM-dd")


class F3Result(BaseModel):
    """核查结果，对应 fact_check_result 表"""
    resultLabel: str = Field(default="insufficient_evidence", description="核查标签：supported / not_supported / partly_supported / insufficient_evidence")
    confidenceScore: Optional[int] = Field(default=None, ge=0, le=100, description="置信度评分 0-100")
    conclusion: str = Field(default="", description="面向用户展示的简洁核查结论")
    analysisDetail: str = Field(default="", description="基于证据的简要分析说明")
    supportCount: int = Field(default=0, ge=0, description="支持证据数量")
    attackCount: int = Field(default=0, ge=0, description="反驳证据数量")


class F3Report(BaseModel):
    """分析报告，对应 analysis_report 表"""
    reportTitle: str = Field(default="", description="报告标题")
    reportContent: str = Field(default="", description="完整 Markdown 格式报告")
    reportFormat: str = Field(default="markdown", description="报告格式：markdown / html / pdf / docx")


class FactCheckDetailDBData(BaseModel):
    """F3 响应 data — 数据库对齐版，含 claims / evidences / result / report"""
    claims: List[F3ClaimItem] = []
    evidences: List[F3EvidenceItem] = []
    result: F3Result
    report: F3Report
