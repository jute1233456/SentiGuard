"""报告生成器 — 支持数据驱动和 LLM 叙事两种模式。

数据驱动模式（原有）：
    将数据填入模板章节，适合快速生成结构化报告。

LLM 叙事模式（增强版，借鉴 BettaFish）：
    1. 调用 LLM 设计布局（标题、摘要、KPI、关键发现、章节指导）
    2. 逐章调用 LLM 生成结构化 IR JSON（blocks 数组）
    3. 组装文档 IR
    4. 用 HTML 渲染器输出（按 block type 分派渲染）
    5. 失败时自动降级为原有 Markdown 模式
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .ir import (
    ALL_BLOCK_TYPES,
    BLOCK_CALLOUT,
    BLOCK_EVIDENCE_CARD,
    BLOCK_HEADING,
    BLOCK_HR,
    BLOCK_KPI_GRID,
    BLOCK_LIST,
    BLOCK_PARAGRAPH,
    BLOCK_TABLE,
    build_document_ir,
    validate_chapter_ir,
)
from .llms.client import get_report_llm
from .models import ReportData, ReportResult, SectionOutput
from .prompts.prompts import (
    SYSTEM_PROMPT_CHAPTER_IR,
    SYSTEM_PROMPT_REPORT_LAYOUT,
)
from .sections.base import get_section
from .templates.base import get_template
from .renderers.base import get_renderer

logger = logging.getLogger("report.generator")

# 预定义的报告章节
CHAPTER_DEFINITIONS = [
    {"id": "summary", "title": "报告摘要", "anchor": "section-summary"},
    {"id": "claims", "title": "声明拆解", "anchor": "section-claims"},
    {"id": "evidence", "title": "证据分析", "anchor": "section-evidence"},
    {"id": "verdict", "title": "综合判定", "anchor": "section-verdict"},
    {"id": "appendix", "title": "报告附注", "anchor": "section-appendix"},
]


class ReportGenerator:
    """报告主编排器（数据驱动模式 — 原有）"""

    def __init__(self, data: ReportData):
        self.data = data

    def generate(
        self,
        template_name: str = "standard",
        renderer_name: str = "markdown",
    ) -> ReportResult:
        template_cls = get_template(template_name)
        template = template_cls(self.data)
        section_names = template.get_section_names()

        section_outputs: List[SectionOutput] = []
        for name in section_names:
            section_cls = get_section(name)
            section = section_cls(self.data)
            output = section.render()
            section_outputs.append(output)

        renderer_cls = get_renderer(renderer_name)
        renderer = renderer_cls()
        content = renderer.render(section_outputs, template.get_title())

        return ReportResult(
            title=template.get_title(),
            sections=section_outputs,
            content=content,
            format=renderer_name,
        )


class LLMReportGenerator:
    """报告生成器（LLM 叙事模式 — 增强版）

    流程：
        1. LLM 设计布局（标题、摘要、KPI、关键发现）
        2. 逐章调用 LLM 生成结构化 IR JSON
        3. 组装文档 IR → HTML 渲染
        4. 失败时降级为原有模式
    """

    def __init__(self, data: ReportData):
        self.data = data
        self.llm = get_report_llm()

    def generate(self, renderer_name: str = "html") -> ReportResult:
        """生成 LLM 叙事报告"""
        # 1. 设计布局
        layout = self._design_layout()

        # 2. 逐章生成结构化 IR（单章失败不影响其他章）
        try:
            document_ir = self._generate_structured_report(layout)
            # 3. 用 IR 感知的渲染器输出
            renderer_cls = get_renderer(renderer_name)
            renderer = renderer_cls()
            content = renderer.render_ir(document_ir)
        except Exception as e:
            logger.warning("结构化 IR 生成失败，降级为 Markdown 模式: %s", e)
            # 降级：调用一次 LLM 生成完整 Markdown
            full_payload = self._build_full_payload(layout)
            try:
                report_content = self._generate_report_markdown(full_payload)
            except Exception as md_e:
                logger.warning("Markdown 降级也失败: %s", md_e)
                report_content = self._generate_report_fallback_text(layout)
            renderer_cls = get_renderer(renderer_name)
            renderer = renderer_cls()
            content = renderer.render_llm(report_content, layout)

        sections = [
            SectionOutput(
                title=layout.get("title", "事实核查报告"),
                content=content,
                order=1,
            )
        ]

        return ReportResult(
            title=layout.get("title", "事实核查报告"),
            sections=sections,
            content=content,
            format=renderer_name,
        )

    # ================================================================
    # 阶段 A：布局设计
    # ================================================================

    def _design_layout(self) -> Dict[str, Any]:
        """调用 LLM 设计报告布局"""
        data = self.data
        result = data.result

        # 构建 KPIs
        kpis = self._build_kpis(result)

        user_prompt = json.dumps({
            "claim": data.claim,
            "resultLabel": result.resultLabel if result else "N/A",
            "confidenceScore": result.confidenceScore if result else None,
            "conclusion": result.conclusion if result else "",
            "analysisDetail": result.analysisDetail if result else "",
            "supportCount": result.supportCount if result else 0,
            "attackCount": result.attackCount if result else 0,
            "evidenceCount": len(data.evidences),
            "claimCount": len(data.claims),
            "kpis": kpis,
        }, ensure_ascii=False, indent=2)

        response = self.llm.generate(SYSTEM_PROMPT_REPORT_LAYOUT, user_prompt)
        try:
            layout = json.loads(response)
            # 确保关键字段存在
            layout.setdefault("keyFindings", [])
            layout.setdefault("kpis", kpis)
            layout.setdefault("chapterGuidance", {})
            return layout
        except (json.JSONDecodeError, TypeError):
            return {
                "title": f"事实核查报告",
                "summary": "",
                "keyFindings": [],
                "kpis": kpis,
                "chapterGuidance": {},
            }

    # ================================================================
    # 阶段 B：逐章结构化 IR 生成
    # ================================================================

    def _generate_structured_report(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        """逐章调用 LLM 生成结构化 IR，组装为文档 IR

        单章失败不影响其他章——失败章节使用 fallback blocks。
        """
        data = self.data
        result = data.result
        chapter_guidance = layout.get("chapterGuidance", {})

        # 构建每章对应的数据子集
        chapter_data = self._build_chapter_data_packets()

        chapters: List[Dict[str, Any]] = []
        for chapter_def in CHAPTER_DEFINITIONS:
            chap_id = chapter_def["id"]
            chap_title = chapter_def["title"]
            chap_anchor = chapter_def["anchor"]

            # 获取该章的数据子集和写作指导
            data_packet = chapter_data.get(chap_id, {})
            guidance = chapter_guidance.get(chap_id, "")

            # 调用 LLM 生成该章的 blocks（失败不抛异常，用 fallback）
            blocks = None
            try:
                blocks = self._generate_chapter_blocks(
                    chap_title, chap_id, data_packet, guidance, layout
                )
            except Exception as e:
                logger.warning("章节 '%s' IR 生成失败: %s", chap_title, e)

            if blocks:
                chapter_ir = {
                    "chapterId": f"S{CHAPTER_DEFINITIONS.index(chapter_def) + 1}",
                    "title": chap_title,
                    "anchor": chap_anchor,
                    "blocks": blocks,
                }
                errors = validate_chapter_ir(chapter_ir)
                if errors:
                    logger.warning("章节 %s 校验警告: %s", chap_title, errors)
                chapters.append(chapter_ir)
            else:
                # 该章生成失败，用 fallback blocks
                chapters.append(self._build_fallback_chapter(chap_title, chap_anchor, data_packet))

        return build_document_ir(
            title=layout.get("title", "事实核查报告"),
            summary=layout.get("summary", ""),
            kpis=layout.get("kpis", []),
            key_findings=layout.get("keyFindings", []),
            chapters=chapters,
        )

    def _build_fallback_chapter(self, title: str, anchor: str, data_packet: Dict[str, Any]) -> Dict[str, Any]:
        """当某章 IR 生成失败时，构造 fallback 章节"""
        blocks: List[Dict[str, Any]] = [
            {"type": "heading", "level": 2, "text": title, "anchor": anchor},
        ]
        # 尝试从数据包中提取内容生成 fallback paragraph
        if data_packet.get("claim"):
            blocks.append({"type": "paragraph", "inlines": [{"text": data_packet["claim"]}]})
        if data_packet.get("claims"):
            items = []
            for c in data_packet["claims"]:
                items.append([{"type": "paragraph", "inlines": [{"text": f"声明 {c['order']}：{c['text']}"}]}])
            blocks.append({"type": "list", "listType": "bullet", "items": items})
        if data_packet.get("evidences"):
            for ev in data_packet["evidences"]:
                blocks.append({
                    "type": "evidenceCard",
                    "claimOrder": ev.get("claimOrder", 1),
                    "title": ev.get("title", "检索证据"),
                    "content": (ev.get("content") or "")[:200],
                    "source": ev.get("source", "搜索检索结果"),
                    "url": ev.get("url", ""),
                    "relationType": ev.get("relation", "neutral"),
                    "credibilityScore": ev.get("credibility"),
                })
        return {"chapterId": anchor, "title": title, "anchor": anchor, "blocks": blocks}

    def _build_chapter_data_packets(self) -> Dict[str, Any]:
        """为每个章节准备对应的数据子集——每章只传该章独有的数据"""
        data = self.data
        result = data.result

        return {
            "summary": {
                "claim": data.claim,
                "resultLabel": result.resultLabel if result else "N/A",
                "confidenceScore": result.confidenceScore if result else None,
                "conclusion": result.conclusion if result else "",
            },
            "claims": {
                "claims": [
                    {"order": c.claimOrder, "text": c.claimText, "type": c.claimType}
                    for c in data.claims
                ],
            },
            "evidence": {
                "evidences": [
                    {
                        "claimOrder": e.claimOrder,
                        "title": e.evidenceTitle,
                        "content": e.evidenceContent[:300] if e.evidenceContent else "",
                        "source": e.sourceName,
                        "url": e.evidenceUrl,
                        "relation": e.relationType,
                        "credibility": e.credibilityScore,
                    }
                    for e in data.evidences
                ],
            },
            "verdict": {
                "resultLabel": result.resultLabel if result else "N/A",
                "confidenceScore": result.confidenceScore if result else None,
                "conclusion": result.conclusion if result else "",
                "analysisDetail": result.analysisDetail if result else "",
            },
            "appendix": {
                "runId": data.run_id,
                "generatedAt": data.generated_at,
                "originalClaim": data.claim,
            },
        }

    def _generate_chapter_blocks(
        self,
        chap_title: str,
        chap_id: str,
        data_packet: Dict[str, Any],
        guidance: str,
        layout: Dict[str, Any],
    ) -> Optional[List[Dict[str, Any]]]:
        """调用 LLM 为单个章节生成 blocks 数组"""
        # 每章只传该章独有的数据 + 原始声明，不传 KPI/keyFindings/summary
        # 避免 LLM 在各章重复写相同的数据
        chapter_input = {
            "chapterTitle": chap_title,
            "chapterId": chap_id,
            "guidance": guidance,
            "data": data_packet,
            "originalClaim": self.data.claim,
        }

        user_prompt = json.dumps(chapter_input, ensure_ascii=False, indent=2)

        try:
            response = self.llm.generate(SYSTEM_PROMPT_CHAPTER_IR, user_prompt)
            result = json.loads(response)
            blocks = result.get("blocks", [])
            if not isinstance(blocks, list):
                logger.warning("章节 %s 返回的 blocks 不是 list，跳过", chap_title)
                return None
            return blocks
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("章节 %s JSON 解析失败: %s", chap_title, e)
            return None

    # ================================================================
    # 降级路径：原有 Markdown 生成
    # ================================================================

    def _build_full_payload(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        """构建 LLM 输入数据包（降级用）"""
        data = self.data
        result = data.result

        evidence_rows = []
        for ev in data.evidences:
            evidence_rows.append({
                "claimOrder": ev.claimOrder,
                "title": ev.evidenceTitle,
                "source": ev.sourceName,
                "content": ev.evidenceContent[:200] if ev.evidenceContent else "",
                "url": ev.evidenceUrl,
                "relation": ev.relationType,
                "credibility": ev.credibilityScore,
            })

        return {
            "layout": layout,
            "claim": data.claim,
            "claims": [
                {"order": c.claimOrder, "text": c.claimText, "type": c.claimType}
                for c in data.claims
            ],
            "evidences": evidence_rows,
            "result": {
                "label": result.resultLabel if result else "N/A",
                "confidenceScore": result.confidenceScore if result else None,
                "conclusion": result.conclusion if result else "",
                "analysisDetail": result.analysisDetail if result else "",
                "supportCount": result.supportCount if result else 0,
                "attackCount": result.attackCount if result else 0,
            },
            "evidenceStats": {
                "total": len(data.evidences),
                "support": sum(1 for e in data.evidences if e.relationType == "support"),
                "attack": sum(1 for e in data.evidences if e.relationType == "attack"),
                "neutral": sum(1 for e in data.evidences if e.relationType == "neutral"),
            },
            "kpis": layout.get("kpis", []),
        }

    def _generate_report_markdown(self, payload: Dict[str, Any]) -> str:
        """LLM 生成完整 Markdown 报告（降级用）"""
        fallback_prompt = """
你是一个专业的事实核查报告撰写专家。你将收到一次事实核查的完整结构化数据，
需要生成一份内容丰富、结构清晰的 Markdown 格式事实核查报告。

## 报告结构要求

请严格按照以下 5 个章节组织报告：

### 1. 报告摘要
- 概述声明内容、核查方法和结论

### 2. 声明拆解
- 列出拆解出的所有可核查声明

### 3. 证据分析
- 用表格汇总所有证据
- 分析支持性和反驳性证据

### 4. 综合判定
- 给出最终判定结论和置信度说明

### 5. 报告附注
- 追踪 ID、生成时间、证据统计

直接返回完整的 Markdown 报告。
"""
        user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
        return self.llm.generate(fallback_prompt, user_prompt)

    def _generate_report_fallback_text(self, layout: Dict[str, Any]) -> str:
        """最坏情况降级：不用 LLM，直接拼凑文本"""
        data = self.data
        result = data.result
        parts = [
            f"# {layout.get('title', '事实核查报告')}",
            "",
            layout.get("summary", ""),
            "",
            "## 声明拆解",
        ]
        for c in data.claims:
            parts.append(f"- 声明 {c.claimOrder}：{c.claimText}")
        parts.extend(["", "## 证据分析"])
        for e in data.evidences:
            parts.append(f"- [{e.relationType}] {e.evidenceTitle}（{e.sourceName}）")
            if e.evidenceContent:
                parts[-1] += f"：{e.evidenceContent[:200]}"
        if result:
            parts.extend([
                "",
                "## 综合判定",
                f"**判定**：{result.resultLabel}",
                f"**置信度**：{result.confidenceScore}/100" if result.confidenceScore else "",
                f"**结论**：{result.conclusion}",
            ])
        return "\n".join(parts)

    # ================================================================
    # 工具方法
    # ================================================================

    @staticmethod
    def _build_kpis(result) -> List[Dict[str, Any]]:
        """从结果中提取 KPI 数据"""
        kpis = []
        if result:
            if result.confidenceScore is not None:
                tone = "good" if result.confidenceScore >= 60 else "bad"
                kpis.append({
                    "label": "置信度",
                    "value": f"{result.confidenceScore}/100",
                    "tone": tone,
                })
            kpis.append({
                "label": "证据总量",
                "value": f"{result.supportCount + result.attackCount} 条",
                "tone": "neutral",
            })
            kpis.append({
                "label": "支持 / 反驳",
                "value": f"{result.supportCount} / {result.attackCount}",
                "tone": "good" if result.supportCount >= result.attackCount else "bad",
            })
        return kpis
