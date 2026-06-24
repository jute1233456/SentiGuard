"""报告头章节：标题、结论、置信度"""
from __future__ import annotations

from ..models import ReportData, SectionOutput
from .base import BaseSection, register_section


class HeaderSection(BaseSection):
    """报告头 — 展示标题、结论摘要和置信度"""

    def render(self) -> SectionOutput:
        lines: list[str] = []
        result = self.data.result

        # 标题
        claim_preview = (self.data.claim or "").strip()
        title = f"事实核查报告"
        if claim_preview:
            title += f" — {claim_preview[:60]}"
        lines.append(f"# {title}\n")

        # 结论
        if result and result.conclusion:
            lines.append(f"**核查结论**：{result.conclusion}\n")

        # 置信度
        if result and result.confidenceScore is not None:
            score = result.confidenceScore
            label = self._confidence_label(score)
            lines.append(f"**置信度**：{score}/100（{label}）\n")
        else:
            lines.append(f"**置信度**：N/A\n")

        # 标签
        if result and result.resultLabel:
            label_map = {
                "supported": "✅ 支持（声明为真）",
                "not_supported": "❌ 不支持（声明为假）",
                "insufficient_evidence": "⚠️ 证据不足",
                "partly_supported": "🔶 部分支持",
            }
            label_text = label_map.get(result.resultLabel, result.resultLabel)
            lines.append(f"**判定标签**：{label_text}\n")

        # 支持/反驳计数
        if result:
            lines.append(
                f"**证据统计**：{result.supportCount} 条支持 / {result.attackCount} 条反驳 / {result.neutralCount} 条中性\n"
            )

        lines.append("---\n")
        return SectionOutput(title="报告摘要", content="".join(lines), order=1)

    @staticmethod
    def _confidence_label(score: int) -> str:
        if score >= 80:
            return "高置信度"
        elif score >= 60:
            return "中等置信度"
        elif score >= 40:
            return "低置信度"
        return "极低置信度"


register_section("header", HeaderSection)
