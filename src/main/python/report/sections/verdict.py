"""判定与解释章节"""
from __future__ import annotations

from ..models import ReportData, SectionOutput
from .base import BaseSection, register_section


class VerdictSection(BaseSection):
    """展示最终判定结果和详细解释"""

    def render(self) -> SectionOutput:
        lines: list[str] = []
        lines.append("## 最终判定\n")

        result = self.data.result
        if not result:
            lines.append("（无判定结果）\n")
            return SectionOutput(title="最终判定", content="".join(lines), order=4)

        label_map = {
            "supported": "✅ 支持（声明为真）",
            "not_supported": "❌ 不支持（声明为假）",
            "insufficient_evidence": "⚠️ 证据不足",
            "partly_supported": "🔶 部分支持",
        }
        label_text = label_map.get(result.resultLabel, result.resultLabel)
        lines.append(f"**判定**：{label_text}\n\n")

        if result.analysisDetail:
            lines.append(f"**分析说明**：\n\n{result.analysisDetail}\n\n")

        if result.supportCount > 0 or result.attackCount > 0 or result.neutralCount > 0:
            lines.append(f"**证据权衡**：{result.supportCount} 条支持，{result.attackCount} 条反驳，{result.neutralCount} 条中性\n")

        if result.confidenceScore is not None:
            lines.append(f"**综合置信度**：{result.confidenceScore}/100\n")

        return SectionOutput(title="最终判定", content="".join(lines), order=4)


register_section("verdict", VerdictSection)
