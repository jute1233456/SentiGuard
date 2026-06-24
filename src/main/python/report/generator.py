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
from .json_utils import robust_json_loads
from .llms.client import get_report_llm
from .models import ReportData, ReportResult, SectionOutput
from .prompts.prompts import (
    SYSTEM_PROMPT_CHAPTER_IR,
    SYSTEM_PROMPT_REPORT_LAYOUT,
    SYSTEM_PROMPT_DEEP_CLAIM_ANALYSIS,
    SYSTEM_PROMPT_DEEP_SUMMARIZE,
    SYSTEM_PROMPT_DEEP_MD_TO_HTML,
    SYSTEM_PROMPT_CLAIM_CARD_HTML,
)
from ..prompts.deep_decomposer import DeepClaimDecomposer, DEFAULT_DEEP_REFLECTION_COUNT
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

        try:
            response = self.llm.generate(SYSTEM_PROMPT_REPORT_LAYOUT, user_prompt)
            layout = robust_json_loads(response, "布局设计")
            if layout:
                # 确保关键字段存在
                layout.setdefault("keyFindings", [])
                layout.setdefault("kpis", kpis)
                layout.setdefault("chapterGuidance", {})
                return layout
        except Exception as e:
            logger.warning("布局设计 LLM 调用失败，使用默认布局: %s", e)
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
            result = robust_json_loads(response, f"章节 {chap_title}")
            if result:
                blocks = result.get("blocks", [])
                if not isinstance(blocks, list):
                    logger.warning("章节 %s 返回的 blocks 不是 list，跳过", chap_title)
                    return None
                return blocks
            return None
        except Exception as e:
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
            total = result.supportCount + result.attackCount + result.neutralCount
            kpis.append({
                "label": "证据总量",
                "value": f"{total} 条",
                "tone": "neutral",
            })
            kpis.append({
                "label": "支持 / 反驳 / 中性",
                "value": f"{result.supportCount} / {result.attackCount} / {result.neutralCount}",
                "tone": "good" if result.supportCount >= result.attackCount else "bad",
            })
        return kpis


class DeepLLMReportGenerator(LLMReportGenerator):
    """深度搜索专用报告生成器。

    逐段生成，每个子声明+其证据捆绑分析：
    1. LLM 设计布局
    2. 对每个子声明，LLM 分析子声明+其所有证据（逐条分析）
    3. LLM 汇总所有分析生成完整 Markdown
    4. LLM 将 Markdown → 美观 HTML
    """

    def __init__(self, data: ReportData, reflection_count: int = DEFAULT_DEEP_REFLECTION_COUNT):
        super().__init__(data)
        self.conversation_log: List[Dict[str, Any]] = []
        self.reflection_count = reflection_count
        self.decomposition_log: List[Dict[str, Any]] = []

    def _llm_call(self, phase: str, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM 并记录对话日志"""
        response = self.llm.generate(system_prompt, user_prompt)
        self.conversation_log.append({
            "phase": phase,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": response,
        })
        return response

    def get_conversation_log(self) -> List[Dict[str, Any]]:
        return list(self.conversation_log)

    def get_decomposition_log(self) -> List[Dict[str, Any]]:
        return list(self.decomposition_log)

    def generate(self, renderer_name: str = "html") -> ReportResult:
        """生成深度搜索报告（三阶段流程）：
        ① IR 渲染器生成 HTML 骨架（Hero + KPI + CSS），留 {claim_sections} 占位符
        ② LLM 逐段生成每个子声明的 HTML 卡片
        ③ 纯字符串 replace 组装
        """
        self.conversation_log = []
        self.decomposition_log = []

        try:
            # 阶段1: 布局设计
            layout = self._design_layout()

            # 阶段1.5: 深度声明拆解（带反思机制）
            self._deep_decompose_claims()

            # 阶段2+3: 三阶段 HTML 组装（逐段 LLM 生成卡片，不再需要单独的 MD 分析步骤）
            html_content = self._render_html_report(layout)

            return ReportResult(
                title=layout.get("title", "深度事实核查报告"),
                sections=[SectionOutput(title=layout.get("title", "深度事实核查报告"), content=html_content, order=1)],
                content=html_content,
                format="html",
            )
        except Exception as e:
            logger.exception("DeepLLMReportGenerator.generate() 异常，降级到数据驱动模式: %s", e)
            raise

    def _deep_decompose_claims(self):
        """使用 DeepClaimDecomposer 对原始声明进行深度拆解（带反思），
        替换 data.claims 中的子声明列表。"""
        original_claim = self.data.claim
        if not original_claim:
            logger.warning("原始声明为空，跳过深度拆解")
            return

        try:
            decomposer = DeepClaimDecomposer(
                reflection_count=self.reflection_count,
            )
            deep_subclaims = decomposer.decompose(original_claim)

            self.decomposition_log = decomposer.reflection_log

            if not deep_subclaims or deep_subclaims == [original_claim]:
                logger.info("深度拆解未产生新子声明，使用原有 claims")
                return

            from .models import ClaimItem
            new_claims = []
            for i, sc_text in enumerate(deep_subclaims, 1):
                new_claims.append(ClaimItem(
                    claimOrder=i,
                    claimText=sc_text,
                    claimType="verifiable",
                ))

            logger.info("深度拆解: %d 条子声明（原 %d 条）", len(new_claims), len(self.data.claims))
            self.data.claims = new_claims
        except Exception as e:
            logger.exception("深度声明拆解异常，跳过拆解使用原有 claims: %s", e)
            self.decomposition_log = [{
                "round": 0,
                "type": "decompose_failed",
                "subclaims": [original_claim],
                "summary": f"DeepClaimDecomposer 异常: {e}",
            }]

    def _build_claim_evidence_map(self) -> List[Dict[str, Any]]:
        """按 claimOrder 将证据分组到对应的子声明"""
        data = self.data
        claim_map = {}
        for c in data.claims:
            claim_map[c.claimOrder] = {
                "order": c.claimOrder,
                "text": c.claimText,
                "type": c.claimType,
                "evidences": [],
            }

        for e in data.evidences:
            order = e.claimOrder
            if order not in claim_map:
                claim_map[order] = {
                    "order": order,
                    "text": f"子声明 #{order}",
                    "type": "verifiable",
                    "evidences": [],
                }
            claim_map[order]["evidences"].append({
                "title": e.evidenceTitle or "",
                "content": (e.evidenceContent or "")[:2000],
                "source": e.sourceName or "",
                "url": e.evidenceUrl or "",
                "relation": e.relationType or "neutral",
                "credibility": e.credibilityScore,
            })

        return [claim_map[k] for k in sorted(claim_map.keys())]

    def _analyze_all_claims(self) -> List[str]:
        """逐个分析每个子声明+其证据"""
        claim_evidences = self._build_claim_evidence_map()
        total = len(claim_evidences)
        analyses = []

        for i, item in enumerate(claim_evidences, 1):
            progress_info = f"正在分析第 {i}/{total} 个子声明"

            data_packet = {
                "claimOrder": item["order"],
                "claimText": item["text"],
                "claimType": item["type"],
                "evidences": item["evidences"],
                "evidenceCount": len(item["evidences"]),
            }

            user_prompt = json.dumps({
                "progress": progress_info,
                "claimData": data_packet,
            }, ensure_ascii=False, indent=2)

            try:
                response = self._llm_call(
                    f"analyze_claim_{i}",
                    SYSTEM_PROMPT_DEEP_CLAIM_ANALYSIS,
                    user_prompt,
                )
                analyses.append(response)
                logger.info("子声明 %d/%d 分析完成", i, total)
            except Exception as e:
                logger.warning("子声明 %d 分析失败: %s", i, e)
                fallback = self._build_claim_fallback(item)
                analyses.append(fallback)

        return analyses

    def _render_html_report(self, layout: Dict[str, Any]) -> str:
        """三阶段 HTML 组装：
        ① 渲染 HTML 骨架（Hero + KPI + CSS），留 {claim_sections} 占位符
        ② LLM 逐段生成每个子声明的 HTML 卡片（分析+证据内嵌）
        ③ 组装
        """
        try:
            return self._do_render_html_report(layout)
        except Exception as e:
            logger.exception("三阶段 HTML 组装失败，降级到 IR 渲染器: %s", e)
            from .renderers.html import HTMLRenderer
            renderer = HTMLRenderer()
            return renderer.render_llm("（报告生成失败，请重试）", layout)

    def _do_render_html_report(self, layout: Dict[str, Any]) -> str:
        """三阶段 HTML 组装的具体实现"""
        from .renderers.html import HTMLRenderer
        renderer = HTMLRenderer()

        # 阶段①：HTML 骨架（含声明拆解列表）
        result = self.data.result
        claim_texts = [c.claimText for c in self.data.claims] if self.data.claims else []
        framework = renderer.render_framework(
            layout, result=result, claim_texts=claim_texts,
        )

        # 阶段②：逐段 LLM 生成 HTML 卡片
        claim_evidences = self._build_claim_evidence_map()
        total = len(claim_evidences)
        cards: List[str] = []

        for i, item in enumerate(claim_evidences, 1):
            progress_info = f"正在生成第 {i}/{total} 个声明分析卡片"

            data_packet = {
                "progress": progress_info,
                "claimOrder": item["order"],
                "claimText": item["text"],
                "claimType": item["type"],
                "evidences": item["evidences"],
                "evidenceCount": len(item["evidences"]),
            }

            user_prompt = json.dumps(data_packet, ensure_ascii=False, indent=2)

            try:
                response = self._llm_call(
                    f"claim_card_{i}",
                    SYSTEM_PROMPT_CLAIM_CARD_HTML,
                    user_prompt,
                )
                import re as _re
                match = _re.search(r"```(?:html)?\s*([\s\S]*?)\s*```", response)
                if match:
                    cards.append(match.group(1).strip())
                else:
                    cards.append(response.strip())
                logger.info("声明卡片 %d/%d 生成完成", i, total)
            except Exception as e:
                logger.warning("声明卡片 %d 生成失败: %s", i, e)
                fallback = self._build_claim_card_html_fallback(item)
                cards.append(fallback)

        # 阶段③：组装
        all_cards = "\n".join(cards)
        return framework.replace("{claim_sections}", all_cards)

    def _build_claim_card_html_fallback(self, item: Dict[str, Any]) -> str:
        """逐段 LLM 调用失败时的 HTML 降级卡片（纯数据渲染，不调 LLM）"""
        order = item.get("order", "?")
        text = item.get("text", "")
        ctype = item.get("type", "verifiable")
        parts = [
            f'<div class="claim-card">',
            f'<div class="claim-card-header">',
            f'<span class="claim-number">子声明 {order}</span>',
            f'<span class="claim-type-badge">{ctype}</span>',
            f"</div>",
            f'<blockquote class="claim-text">{text}</blockquote>',
            f'<div class="claim-analysis"><h4>证据列表</h4></div>',
            f'<div class="evidence-list">',
        ]
        for ev in item.get("evidences", []):
            rel = ev.get("relation", "neutral")
            rel_label = {"support": "支持", "attack": "反驳", "neutral": "中性"}.get(rel, "中性")
            cred = ev.get("credibility")
            cred_html = ""
            if cred is not None:
                cred_int = max(0, min(100, int(cred)))
                cred_class = "high" if cred_int >= 60 else ("mid" if cred_int >= 30 else "low")
                cred_html = (
                    f'<div class="evidence-credibility">'
                    f'<span class="cred-label">可信度</span>'
                    f'<div class="cred-bar"><div class="cred-fill {cred_class}" style="width:{cred_int}%"></div></div>'
                    f'<span class="cred-value">{cred_int}/100</span>'
                    f"</div>"
                )
            parts.append(
                f'<div class="evidence-card">'
                f'<div class="evidence-header">'
                f'<span class="evidence-relation {rel}">{rel_label}</span>'
                f'<span class="evidence-claim">{ev.get("source", "")}</span>'
                f"</div>"
                f'<div class="evidence-body">'
                f'<div class="evidence-title">{ev.get("title", "")}</div>'
                f'<div class="evidence-content">{ev.get("content", "")}</div>'
                f"{cred_html}"
                f"</div>"
                f'<div class="evidence-footer">'
                f'<a class="evidence-source" href="{ev.get("url", "")}" target="_blank">查看原文 →</a>'
                f"</div>"
                f"</div>"
            )
        parts.append("</div>")  # evidence-list
        parts.append("</div>")  # claim-card
        return "\n".join(parts)

    def _build_claim_fallback(self, item: Dict[str, Any]) -> str:
        """子声明分析失败时的降级文本"""
        lines = [
            f"### 子声明 {item['order']}：{item['text']}",
            "",
            "**证据列表：**",
        ]
        for ev in item.get("evidences", []):
            rel_icon = {"support": "✅", "attack": "❌", "neutral": "➖"}.get(ev["relation"], "📄")
            lines.append(f"- {rel_icon} [{ev['relation']}] {ev['title']}（来源：{ev['source']}）")
            if ev["content"]:
                lines.append(f"  {ev['content'][:200]}")
        lines.append("")
        return "\n".join(lines)

    def _summarize_report(self, layout: Dict[str, Any], analyses: List[str]) -> str:
        """汇总所有子声明分析，生成完整 Markdown 报告"""
        result = self.data.result
        kpis = layout.get("kpis", [])

        user_prompt = json.dumps({
            "layout": {
                "title": layout.get("title", "事实核查报告"),
                "summary": layout.get("summary", ""),
                "keyFindings": layout.get("keyFindings", []),
                "kpis": kpis,
                "result": {
                    "label": result.resultLabel if result else "N/A",
                    "confidenceScore": result.confidenceScore if result else None,
                    "conclusion": result.conclusion if result else "",
                    "analysisDetail": result.analysisDetail if result else "",
                },
                "evidenceStats": {
                    "total": len(self.data.evidences),
                    "support": sum(1 for e in self.data.evidences if e.relationType == "support"),
                    "attack": sum(1 for e in self.data.evidences if e.relationType == "attack"),
                    "neutral": sum(1 for e in self.data.evidences if e.relationType == "neutral"),
                },
            },
            "analyses": analyses,
        }, ensure_ascii=False, indent=2)

        try:
            response = self._llm_call("summarize", SYSTEM_PROMPT_DEEP_SUMMARIZE, user_prompt)
            return response
        except Exception as e:
            logger.warning("汇总报告生成失败: %s", e)
            return self._build_fallback_summary(layout, analyses)

    def _build_fallback_summary(self, layout: Dict[str, Any], analyses: List[str]) -> str:
        """汇总失败时的降级：直接拼接"""
        parts = [
            f"# {layout.get('title', '事实核查报告')}",
            "",
            layout.get("summary", ""),
            "",
            "## 声明拆解与证据分析",
            "",
        ]
        parts.extend(analyses)
        result = self.data.result
        if result:
            parts.extend([
                "",
                "## 综合判定",
                f"**判定**：{result.resultLabel}",
                f"**置信度**：{result.confidenceScore}/100" if result.confidenceScore else "",
                f"**结论**：{result.conclusion}",
                "",
            ])
        parts.extend([
            "## 报告附注",
            f"- 追踪 ID：`{self.data.run_id}`" if self.data.run_id else "",
            f"- 生成时间：{self.data.generated_at}" if self.data.generated_at else "",
        ])
        return "\n".join(parts)

    def _convert_md_to_html(self, md_content: str, layout: Dict[str, Any]) -> str:
        """将 Markdown 转换为 HTML。
        内容较短时用 LLM 美化，过长时直接走 IR 渲染器（避免 LLM token 溢出）。"""
        result = self.data.result

        kpi_data = self._build_kpis(result)

        # 内容超过 20000 字符时，跳过 LLM 调用，直接用 IR 渲染器
        # LLM MD→HTML 需要输入+输出双倍 token，大文档极易截断
        if len(md_content) > 20000:
            logger.info("Markdown 内容过长 (%d chars)，跳过 LLM，直接使用 IR 渲染器", len(md_content))
            from .renderers.base import get_renderer
            renderer_cls = get_renderer("html")
            renderer = renderer_cls()
            return renderer.render_llm(md_content, layout)

        user_prompt = json.dumps({
            "kpis": kpi_data,
            "markdown_content": md_content,
        }, ensure_ascii=False, indent=2)

        try:
            response = self._llm_call("md_to_html", SYSTEM_PROMPT_DEEP_MD_TO_HTML, user_prompt)
            import re
            match = re.search(r"```(?:html)?\s*([\s\S]*?)\s*```", response)
            if match:
                return match.group(1).strip()
            if response.strip().startswith("<!DOCTYPE") or response.strip().startswith("<html"):
                return response.strip()
            # LLM 输出不规范，降级到 IR 渲染器
            from .renderers.base import get_renderer
            renderer_cls = get_renderer("html")
            renderer = renderer_cls()
            return renderer.render_llm(md_content, layout)
        except Exception as e:
            logger.warning("Markdown→HTML 转换失败: %s", e)
            from .renderers.base import get_renderer
            renderer_cls = get_renderer("html")
            renderer = renderer_cls()
            return renderer.render_llm(md_content, layout)
