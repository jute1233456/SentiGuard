"""报告模块数据模型。

将 F3 接口的 FactCheckDetailDBData 适配为报告模块内部使用的 ReportData，
各 Section 和 Renderer 只依赖 ReportData，不直接依赖 API schema。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaimItem:
    """单条可核查声明"""
    claimOrder: int
    claimText: str
    claimType: str = "verifiable"


@dataclass
class EvidenceItem:
    """单条证据"""
    claimOrder: int
    evidenceTitle: str = ""
    evidenceContent: str = ""
    evidenceUrl: str = ""
    sourceName: str = ""
    evidenceType: str = "web"
    relationType: str = "neutral"
    credibilityScore: Optional[int] = None
    publishTime: Optional[str] = None


@dataclass
class ResultItem:
    """核查结果"""
    resultLabel: str = "insufficient_evidence"
    confidenceScore: Optional[int] = None
    conclusion: str = ""
    analysisDetail: str = ""
    supportCount: int = 0
    attackCount: int = 0
    neutralCount: int = 0


@dataclass
class ReportData:
    """报告模块内部使用的完整数据"""
    claim: str
    claims: List[ClaimItem] = field(default_factory=list)
    evidences: List[EvidenceItem] = field(default_factory=list)
    result: Optional[ResultItem] = None
    run_id: str = ""
    generated_at: str = ""

    @classmethod
    def from_f3_data(cls, f3_data: Any, run_id: str = "",
                     generated_at: str = "") -> "ReportData":
        """从 F3 接口的 FactCheckDetailDBData 创建 ReportData"""
        return cls(
            claim="",
            claims=cls._convert_claims(f3_data.claims if f3_data else None),
            evidences=cls._convert_evidences(f3_data.evidences if f3_data else None),
            result=ResultItem(
                resultLabel=f3_data.result.resultLabel if f3_data and f3_data.result else "insufficient_evidence",
                confidenceScore=f3_data.result.confidenceScore if f3_data and f3_data.result else None,
                conclusion=f3_data.result.conclusion if f3_data and f3_data.result else "",
                analysisDetail=f3_data.result.analysisDetail if f3_data and f3_data.result else "",
                supportCount=f3_data.result.supportCount if f3_data and f3_data.result else 0,
                attackCount=f3_data.result.attackCount if f3_data and f3_data.result else 0,
                neutralCount=f3_data.result.neutralCount if f3_data and f3_data.result else 0,
            ) if f3_data and f3_data.result else None,
            run_id=run_id,
            generated_at=generated_at,
        )

    @staticmethod
    def _convert_claims(raw_claims: Any) -> list:
        """将任意类型的声明列表转换为 ClaimItem 列表（字段名映射）"""
        if not raw_claims:
            return []
        result = []
        for c in raw_claims:
            result.append(ClaimItem(
                claimOrder=getattr(c, "claimOrder", 0) or 0,
                claimText=getattr(c, "claimText", "") or "",
                claimType=getattr(c, "claimType", "verifiable") or "verifiable",
            ))
        return result

    @staticmethod
    def _convert_evidences(raw_evidences: Any) -> list:
        """将任意类型的证据列表转换为 EvidenceItem 列表（字段名映射）"""
        if not raw_evidences:
            return []
        result = []
        for e in raw_evidences:
            result.append(EvidenceItem(
                claimOrder=getattr(e, "claimOrder", 1) or 1,
                evidenceTitle=getattr(e, "evidenceTitle", "") or "",
                evidenceContent=getattr(e, "evidenceContent", "") or "",
                evidenceUrl=getattr(e, "evidenceUrl", "") or "",
                sourceName=getattr(e, "sourceName", "") or "",
                evidenceType=getattr(e, "evidenceType", "web") or "web",
                relationType=getattr(e, "relationType", "neutral") or "neutral",
                credibilityScore=getattr(e, "credibilityScore", None),
                publishTime=getattr(e, "publishTime", None),
            ))
        return result


@dataclass
class SectionOutput:
    """单个章节的渲染输出"""
    title: str
    content: str
    order: int = 0


@dataclass
class ReportResult:
    """最终报告"""
    title: str
    sections: List[SectionOutput]
    content: str  # 渲染后的完整内容
    format: str = "markdown"
