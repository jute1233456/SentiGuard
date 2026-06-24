"""HTML 渲染器 — 将结构化 IR 渲染为美观的 HTML 页面。

借鉴 BettaFish 的设计理念，采用 block-type 分派渲染：
- 不再使用正则将 Markdown 转换为 HTML
- LLM 生成结构化 JSON blocks，渲染器按 type 精确渲染
- 支持 9 种 block 类型：heading/paragraph/list/table/callout/kpiGrid/blockquote/evidenceCard/hr

保留向后兼容：
- render() — 数据驱动模式（原有，SectionOutput → HTML）
- render_llm() — LLM 叙事模式降级路径（Markdown → HTML）
- render_ir() — 新增，结构化 IR → HTML（主力路径）
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..ir import (
    ALL_BLOCK_TYPES,
    BLOCK_BLOCKQUOTE,
    BLOCK_CALLOUT,
    BLOCK_EVIDENCE_CARD,
    BLOCK_HEADING,
    BLOCK_HR,
    BLOCK_KPI_GRID,
    BLOCK_LIST,
    BLOCK_PARAGRAPH,
    BLOCK_TABLE,
    CALLOUT_TONES,
    KPI_TONES,
    LIST_TYPES,
    RELATION_TYPES,
)
from ..models import SectionOutput
from .base import BaseRenderer, register_renderer


class HTMLRenderer(BaseRenderer):
    """HTML 渲染器 — 支持数据驱动、LLM 叙事、结构化 IR 三种模式"""

    # ================================================================
    # 公共接口
    # ================================================================

    def render(self, sections: List[SectionOutput], title: str) -> str:
        """数据驱动模式：将章节列表渲染为 HTML"""
        sorted_sections = sorted(sections, key=lambda s: s.order)

        body_parts: List[str] = []
        for sec in sorted_sections:
            body_parts.append(f'<div class="section">{self._md_to_html(sec.content)}</div>')

        return self._wrap_html(title, "\n".join(body_parts), kpis=None)

    def render_llm(self, content: str, layout: Dict[str, Any]) -> str:
        """LLM 叙事模式降级路径：将 LLM 生成的 Markdown 渲染为 HTML"""
        title = layout.get("title", "事实核查报告")
        kpis = layout.get("kpis", [])
        summary = layout.get("summary", "")
        key_findings = layout.get("keyFindings", [])

        body_parts: List[str] = []

        # Hero 区域
        hero_parts = [f'<div class="hero"><h1>{self._escape(title)}</h1>']
        if summary:
            hero_parts.append(f'<p class="summary">{self._escape(summary)}</p>')
        if key_findings:
            hero_parts.append('<div class="findings">')
            for f in key_findings:
                hero_parts.append(
                    f'<div class="finding"><strong>{self._escape(f.get("label", ""))}</strong>'
                    f'<p>{self._escape(f.get("detail", ""))}</p></div>'
                )
            hero_parts.append("</div>")
        hero_parts.append("</div>")
        body_parts.append("".join(hero_parts))

        # KPI 卡片
        if kpis:
            body_parts.append(self._render_kpi_row(kpis))

        # 报告正文
        body_parts.append(f'<div class="report-body">{self._md_to_html(content)}</div>')

        return self._wrap_html(title, "\n".join(body_parts), kpis=kpis)

    def render_framework(
        self, layout: Dict[str, Any],
        result: Any = None,
        claims: Any = None,          # List[ClaimItem]
        claim_texts: List[str] = None,  # 声明拆解后的文本列表
    ) -> str:
        """渲染 HTML 骨架（Hero + KPI + CSS），遵循标准报告模板结构：
        ① 报告摘要（Hero + KPIs）
        ② 判定结论（Verdict banner）
        ③ 声明拆解（按 StandardTemplate claims section）
        ④ 证据分析（{claim_sections} 占位符 → 逐段 LLM 卡片填充）
        ⑤ 报告附注（Metadata）

        用于 DeepLLMReportGenerator 的三阶段流程：框架 → 逐段 LLM 卡片 → 组装。
        """
        title = layout.get("title", "事实核查报告")
        kpis = layout.get("kpis", [])
        summary = layout.get("summary", "")
        key_findings = layout.get("keyFindings", [])

        body_parts: List[str] = []

        # ================================================================
        # Section ①：报告摘要（Hero + KPIs）
        # ================================================================
        hero_parts = [f'<div class="hero"><h1>{self._escape(title)}</h1>']
        if summary:
            hero_parts.append(f'<p class="summary">{self._escape(summary)}</p>')
        if key_findings:
            hero_parts.append('<div class="findings">')
            for f in key_findings:
                hero_parts.append(
                    f'<div class="finding"><strong>{self._escape(f.get("label", ""))}</strong>'
                    f'<p>{self._escape(f.get("detail", ""))}</p></div>'
                )
            hero_parts.append("</div>")
        hero_parts.append("</div>")
        body_parts.append("".join(hero_parts))

        # KPI 卡片
        if kpis:
            body_parts.append(self._render_kpi_row(kpis))

        # ================================================================
        # Section ②：判定结论
        # ================================================================
        if result:
            rlabel = getattr(result, "resultLabel", "") or ""
            if rlabel:
                verdict_class = "true" if "真" in rlabel else ("false" if "假" in rlabel else "uncertain")
                confidence = getattr(result, "confidenceScore", None)
                conclusion = getattr(result, "conclusion", "") or ""
                body_parts.append(
                    f'<div class="verdict-banner {verdict_class}">'
                    f'<span class="verdict-icon">{ "✅" if verdict_class == "true" else ("❌" if verdict_class == "false" else "⚠️") }</span>'
                    f'<div class="verdict-body">'
                    f'<span class="verdict-text">判定结果：{self._escape(rlabel)}</span>'
                )
                if confidence is not None:
                    body_parts.append(
                        f'<span class="verdict-confidence">置信度：{confidence}/100</span>'
                    )
                if conclusion:
                    body_parts.append(f'<p class="verdict-conclusion">{self._escape(conclusion)}</p>')
                body_parts.append("</div></div>")

        # ================================================================
        # Section ③：声明拆解
        # ================================================================
        if claim_texts:
            body_parts.append('<div class="section section-claims">')
            body_parts.append('<h2 class="section-title">📋 声明拆解</h2>')
            body_parts.append('<p class="section-desc">以下为原始声明经深度拆解后得到的可独立核查的子声明：</p>')
            body_parts.append('<ol class="claim-list">')
            for i, ct in enumerate(claim_texts, 1):
                body_parts.append(f'<li><strong>子声明 {i}</strong>：{self._escape(ct)}</li>')
            body_parts.append('</ol>')
            body_parts.append('</div>')

        # ================================================================
        # Section ④：证据分析（逐段 LLM 卡片填充此占位符）
        # ================================================================
        body_parts.append('<div class="section section-evidence">')
        body_parts.append('<h2 class="section-title">📊 证据分析</h2>')
        body_parts.append('<p class="section-desc">以下逐条分析每个子声明及其相关证据，综合判定真实性：</p>')
        body_parts.append('<div id="claim-sections">{claim_sections}</div>')
        body_parts.append('</div>')

        # ================================================================
        # Section ⑤：报告附注
        # ================================================================
        body_parts.append(
            '<div class="section section-metadata report-footer">'
            '<p>⚠️ 本报告由 SentiGuard 多智能体事实核查系统自动生成，仅供参考，不构成法律建议。</p>'
            '</div>'
        )

        return self._wrap_html(title, "\n".join(body_parts), kpis=kpis)

    def render_ir(self, document_ir: Dict[str, Any]) -> str:
        """结构化 IR 模式：将文档 IR 渲染为 HTML（主力路径）"""
        title = document_ir.get("title", "事实核查报告")
        summary = document_ir.get("summary", "")
        kpis = document_ir.get("kpis", [])
        key_findings = document_ir.get("keyFindings", [])
        chapters = document_ir.get("chapters", [])

        body_parts: List[str] = []

        # Hero 区域
        hero_parts = [f'<div class="hero"><h1>{self._escape(title)}</h1>']
        if summary:
            hero_parts.append(f'<p class="summary">{self._escape(summary)}</p>')
        if key_findings:
            hero_parts.append('<div class="findings">')
            for f in key_findings:
                hero_parts.append(
                    f'<div class="finding"><strong>{self._escape(f.get("label", ""))}</strong>'
                    f'<p>{self._escape(f.get("detail", ""))}</p></div>'
                )
            hero_parts.append("</div>")
        hero_parts.append("</div>")
        body_parts.append("".join(hero_parts))

        # KPI 卡片
        if kpis:
            body_parts.append(self._render_kpi_row(kpis))

        # 章节
        for chapter in chapters:
            chap_id = self._escape(chapter.get("anchor", ""))
            chap_title = self._escape(chapter.get("title", ""))
            body_parts.append(f'<section id="{chap_id}" class="chapter">')
            body_parts.append(self._render_blocks(chapter.get("blocks", [])))
            body_parts.append("</section>")

        return self._wrap_html(title, "\n".join(body_parts), kpis=kpis)

    # ================================================================
    # Block-type 分派渲染（IR 模式核心）
    # ================================================================

    def _render_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        """顺序渲染 blocks 数组"""
        return "".join(self._render_block(b) for b in blocks if isinstance(b, dict))

    def _render_block(self, block: Dict[str, Any]) -> str:
        """按 block.type 分派到具体的渲染方法"""
        block_type = block.get("type")
        if not block_type:
            return ""

        handlers = {
            BLOCK_HEADING: self._render_heading_block,
            BLOCK_PARAGRAPH: self._render_paragraph_block,
            BLOCK_LIST: self._render_list_block,
            BLOCK_TABLE: self._render_table_block,
            BLOCK_CALLOUT: self._render_callout_block,
            BLOCK_KPI_GRID: self._render_kpi_grid_block,
            BLOCK_BLOCKQUOTE: self._render_blockquote_block,
            BLOCK_EVIDENCE_CARD: self._render_evidence_card_block,
            BLOCK_HR: lambda b: "<hr>",
        }
        handler = handlers.get(block_type)
        if handler:
            return handler(block)
        return ""

    # ====== Block 渲染方法 ======

    def _render_heading_block(self, block: Dict[str, Any]) -> str:
        """渲染 heading block"""
        # 容错处理：level 可能是字符串甚至中文
        try:
            level = min(max(int(block.get("level", 2)), 1), 6)
        except (ValueError, TypeError):
            level = 2
        text = self._escape(block.get("text", ""))
        if not text:
            return ""
        anchor = block.get("anchor", "")
        if anchor:
            return f'<h{level} id="{self._escape(anchor)}">{text}</h{level}>'
        return f"<h{level}>{text}</h{level}>"

    def _render_paragraph_block(self, block: Dict[str, Any]) -> str:
        """渲染 paragraph block（含 inline marks）"""
        inlines = block.get("inlines", [])
        if not inlines:
            # 容错：如果 inlines 为空，尝试从 text/content 字段取文本
            fallback_text = block.get("text") or block.get("content", "")
            if fallback_text:
                return f"<p>{self._escape(fallback_text)}</p>"
            return ""
        html_parts: List[str] = []
        for run in inlines:
            if not isinstance(run, dict):
                html_parts.append(self._escape(str(run)))
                continue
            text = run.get("text", "")
            marks = run.get("marks", [])
            if not isinstance(marks, list):
                marks = []
            rendered_text = self._escape(text)
            for mark in marks:
                if not isinstance(mark, dict):
                    continue
                mark_type = mark.get("type")
                if mark_type == "bold":
                    rendered_text = f"<strong>{rendered_text}</strong>"
                elif mark_type == "italic":
                    rendered_text = f"<em>{rendered_text}</em>"
            html_parts.append(rendered_text)
        return f"<p>{''.join(html_parts)}</p>"

    def _render_list_block(self, block: Dict[str, Any]) -> str:
        """渲染 list block"""
        list_type = block.get("listType", "bullet")
        items = block.get("items", [])
        if not items:
            return ""
        tag = "ol" if list_type == "ordered" else "ul"
        items_html: List[str] = []
        for item in items:
            if isinstance(item, list):
                # 每个 item 是一个 block 数组
                content = self._render_blocks(item)
            elif isinstance(item, dict):
                content = self._render_block(item)
            else:
                content = self._escape(str(item))
            items_html.append(f"<li>{content}</li>")
        return f"<{tag}>{''.join(items_html)}</{tag}>"

    def _render_table_block(self, block: Dict[str, Any]) -> str:
        """渲染 table block"""
        rows = block.get("rows", [])
        if not rows:
            return ""
        html_rows: List[str] = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            cells = row.get("cells", [])
            cells_html: List[str] = []
            for cell in cells:
                if isinstance(cell, dict):
                    text = cell.get("text", "")
                else:
                    text = str(cell)
                tag = "th" if i == 0 else "td"
                cells_html.append(f"<{tag}>{self._escape(text)}</{tag}>")
            html_rows.append(f"<tr>{''.join(cells_html)}</tr>")
        if html_rows:
            return f"<table><thead>{html_rows[0]}</thead><tbody>{''.join(html_rows[1:])}</tbody></table>"
        return ""

    def _render_callout_block(self, block: Dict[str, Any]) -> str:
        """渲染 callout block（带图标和色块的提示框）"""
        tone = block.get("tone", "info")
        if tone not in ["info", "warning", "success", "danger"]:
            tone = "info"
        inner_blocks = block.get("blocks", [])
        inner_html = self._render_blocks(inner_blocks) if inner_blocks else ""
        title = block.get("title", "")
        title_html = f'<div class="callout-title">{self._escape(title)}</div>' if title else ""

        # 图标
        icons = {
            "info": "&#x2139;",      # ℹ
            "warning": "&#x26A0;",   # ⚠
            "success": "&#x2714;",   # ✔
            "danger": "&#x2718;",    # ✘
        }
        icon = icons.get(tone, "")

        return (
            f'<div class="callout callout-{tone}">'
            f'<div class="callout-icon">{icon}</div>'
            f'<div class="callout-body">{title_html}{inner_html}</div>'
            f"</div>"
        )

    def _render_kpi_grid_block(self, block: Dict[str, Any]) -> str:
        """渲染 kpiGrid block"""
        items = block.get("items", [])
        if not items:
            return ""
        cards: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("label", "")
            value = item.get("value", "")
            tone = item.get("tone", "neutral")
            if tone not in KPI_TONES:
                tone = "neutral"
            cards.append(
                f'<div class="kpi-card {tone}">'
                f'<div class="kpi-label">{self._escape(label)}</div>'
                f'<div class="kpi-value">{self._escape(value)}</div>'
                f"</div>"
            )
        return f'<div class="kpi-row">{"".join(cards)}</div>'

    def _render_blockquote_block(self, block: Dict[str, Any]) -> str:
        """渲染 blockquote block"""
        text = block.get("text", "")
        if not text:
            return ""
        return f"<blockquote><p>{self._escape(text)}</p></blockquote>"

    def _render_evidence_card_block(self, block: Dict[str, Any]) -> str:
        """渲染 evidenceCard block（事实核查专用）"""
        claim_order = block.get("claimOrder", "")
        title = block.get("title", "")
        content = block.get("content", "")
        source = block.get("source", "")
        url = block.get("url", "")
        relation_type = block.get("relationType", "neutral")
        credibility = block.get("credibilityScore")

        # 容错：如果没有内容，不渲染
        if not title and not content:
            return ""

        # 论辩关系标签
        relation_labels = {
            "support": ("支持", "support"),
            "attack": ("反驳", "attack"),
            "neutral": ("中性", "neutral"),
        }
        rel_label, rel_class = relation_labels.get(relation_type, ("未知", "neutral"))

        # 可信度条
        credibility_html = ""
        if credibility is not None:
            cred_int = max(0, min(100, int(credibility)))
            cred_class = "high" if cred_int >= 60 else ("mid" if cred_int >= 30 else "low")
            credibility_html = (
                f'<div class="evidence-credibility">'
                f'<span class="cred-label">可信度</span>'
                f'<div class="cred-bar"><div class="cred-fill {cred_class}" style="width:{cred_int}%"></div></div>'
                f'<span class="cred-value">{cred_int}/100</span>'
                f"</div>"
            )

        # 来源链接
        source_html = ""
        if url:
            source_html = (
                f'<a href="{self._escape(url)}" class="evidence-source" '
                f'target="_blank" rel="noopener">'
                f'{self._escape(source or url)} &#8599;</a>'
            )
        elif source:
            source_html = f'<span class="evidence-source">{self._escape(source)}</span>'

        return (
            f'<div class="evidence-card">'
            f'<div class="evidence-header">'
            f'<span class="evidence-relation {rel_class}">{rel_label}</span>'
            f'<span class="evidence-claim">声明 #{self._escape(str(claim_order))}</span>'
            f"</div>"
            f'<div class="evidence-body">'
            f'<div class="evidence-title">{self._escape(title)}</div>'
            f'<div class="evidence-content">{self._escape(content)}</div>'
            f"{credibility_html}"
            f"</div>"
            f'<div class="evidence-footer">{source_html}</div>'
            f"</div>"
        )

    # ================================================================
    # KPI 行辅助（共用于 render_llm 和 render_ir）
    # ================================================================

    def _render_kpi_row(self, kpis: List[Dict[str, Any]]) -> str:
        """渲染 KPI 卡片行"""
        cards: List[str] = []
        for kpi in kpis:
            tone = kpi.get("tone", "neutral")
            if tone not in KPI_TONES:
                tone = "neutral"
            cards.append(
                f'<div class="kpi-card {tone}">'
                f'<div class="kpi-label">{self._escape(kpi.get("label", ""))}</div>'
                f'<div class="kpi-value">{self._escape(kpi.get("value", ""))}</div>'
                f"</div>"
            )
        return f'<div class="kpi-row">{"".join(cards)}</div>'

    # ================================================================
    # 包裹 HTML 页面
    # ================================================================

    def _wrap_html(self, title: str, body: str, kpis: Any = None) -> str:
        """生成完整 HTML 页面（借鉴 BettaFish 设计风格，丰富的 CSS 变量与视觉层次）"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._escape(title)}</title>
<style>
  /* ================================================================
     CSS 变量体系（借鉴 BettaFish themeTokens 设计）
     ================================================================ */
  :root {{
    --bg: #f8f9fc;
    --surface: #ffffff;
    --text: #1a1a2e;
    --text-secondary: #5a6178;
    --muted: #8b92a8;
    --border: #e2e6ef;
    --border-light: #eef0f6;
    --accent: #4361ee;
    --accent-light: #e8ecff;
    --accent-gradient: linear-gradient(135deg, #4361ee, #3a0ca3);
    --good: #2d6a4f;
    --good-bg: #d8f3dc;
    --good-light: #b7e4c7;
    --bad: #9b2226;
    --bad-bg: #f8d7da;
    --bad-light: #f1c0c3;
    --neutral: #6c757d;
    --neutral-bg: #e9ecef;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 16px rgba(0,0,0,0.06);
    --shadow-lg: 0 8px 32px rgba(0,0,0,0.08);
    --radius-sm: 8px;
    --radius: 12px;
    --radius-lg: 16px;
    --callout-info: #4361ee;
    --callout-info-bg: #eef0ff;
    --callout-warning: #e8590c;
    --callout-warning-bg: #fff4e6;
    --callout-success: #2d6a4f;
    --callout-success-bg: #d8f3dc;
    --callout-danger: #9b2226;
    --callout-danger-bg: #f8d7da;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0a0a14;
      --surface: #141420;
      --text: #e4e6f0;
      --text-secondary: #9ca3af;
      --muted: #6b7280;
      --border: #2a2a3e;
      --border-light: #1f1f32;
      --accent: #6c8cff;
      --accent-light: #1a1a3e;
      --accent-gradient: linear-gradient(135deg, #6c8cff, #5a2dca);
      --good: #52b788;
      --good-bg: #1b3a2a;
      --good-light: #2d6a4f;
      --bad: #ef4444;
      --bad-bg: #3b1a1a;
      --bad-light: #6b2a2a;
      --neutral: #9ca3af;
      --neutral-bg: #2a2a3e;
      --shadow-sm: 0 1px 3px rgba(0,0,0,0.15);
      --shadow-md: 0 4px 16px rgba(0,0,0,0.25);
      --shadow-lg: 0 8px 32px rgba(0,0,0,0.35);
      --callout-info: #6c8cff;
      --callout-info-bg: #1a1a3e;
      --callout-warning: #ff922b;
      --callout-warning-bg: #2d1f0a;
      --callout-success: #52b788;
      --callout-success-bg: #1b3a2a;
      --callout-danger: #ef4444;
      --callout-danger-bg: #3b1a1a;
    }}
  }}

  /* ================================================================
     基础重置与排版
     ================================================================ */
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
    max-width: 1000px;
    margin: 0 auto;
    padding: 32px 24px;
    -webkit-font-smoothing: antialiased;
  }}

  /* ================================================================
     Hero 区域（报告标题、摘要、关键发现）
     ================================================================ */
  .hero {{
    margin-bottom: 36px;
    padding: 36px 32px;
    background: var(--accent-gradient);
    border-radius: var(--radius-lg);
    color: #ffffff;
    position: relative;
    overflow: hidden;
  }}
  .hero::before {{
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: rgba(255,255,255,0.06);
    pointer-events: none;
  }}
  .hero::after {{
    content: '';
    position: absolute;
    bottom: -30%;
    left: -10%;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: rgba(255,255,255,0.04);
    pointer-events: none;
  }}
  .hero h1 {{ font-size: 1.8em; margin-bottom: 12px; font-weight: 700; letter-spacing: -0.3px; position: relative; z-index: 1; }}
  .hero .summary {{ font-size: 1.05em; opacity: 0.9; line-height: 1.8; position: relative; z-index: 1; max-width: 800px; }}
  .findings {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 24px; position: relative; z-index: 1; }}
  .finding {{
    padding: 14px 18px;
    background: rgba(255,255,255,0.12);
    backdrop-filter: blur(8px);
    border-radius: var(--radius);
    border: 1px solid rgba(255,255,255,0.15);
  }}
  .finding strong {{ display: block; margin-bottom: 4px; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.8; }}
  .finding p {{ font-size: 0.95em; margin: 0; opacity: 0.95; }}

  /* ================================================================
     KPI 卡片行
     ================================================================ */
  .kpi-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px;
    margin-bottom: 36px;
  }}
  .kpi-card {{
    padding: 20px 16px;
    border-radius: var(--radius);
    text-align: center;
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border-light);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    background: var(--surface);
  }}
  .kpi-card:hover {{
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }}
  .kpi-card.good {{ border-top: 3px solid var(--good); }}
  .kpi-card.bad {{ border-top: 3px solid var(--bad); }}
  .kpi-card.neutral {{ border-top: 3px solid var(--muted); }}
  .kpi-label {{ font-size: 0.8em; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.3px; }}
  .kpi-value {{ font-size: 1.6em; font-weight: 700; }}
  .kpi-card.good .kpi-value {{ color: var(--good); }}
  .kpi-card.bad .kpi-value {{ color: var(--bad); }}

  /* ================================================================
     章节
     ================================================================ */
  .chapter {{ margin-bottom: 32px; }}

  /* ================================================================
     Callout 提示框（四色调）
     ================================================================ */
  .callout {{
    display: flex;
    gap: 14px;
    padding: 18px 20px;
    margin: 20px 0;
    border-radius: var(--radius);
    border-left: 4px solid;
    box-shadow: var(--shadow-sm);
  }}
  .callout-info {{ background: var(--callout-info-bg); border-color: var(--callout-info); }}
  .callout-warning {{ background: var(--callout-warning-bg); border-color: var(--callout-warning); }}
  .callout-success {{ background: var(--callout-success-bg); border-color: var(--callout-success); }}
  .callout-danger {{ background: var(--callout-danger-bg); border-color: var(--callout-danger); }}
  .callout-icon {{ font-size: 1.4em; line-height: 1.4; flex-shrink: 0; margin-top: 1px; }}
  .callout-title {{ font-weight: 600; margin-bottom: 6px; font-size: 1.05em; }}
  .callout-body p {{ margin: 4px 0; }}
  .callout-body ul, .callout-body ol {{ margin: 4px 0; padding-left: 20px; }}

  /* ================================================================
     证据卡片
     ================================================================ */
  .evidence-card {{
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin: 14px 0;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s ease;
    background: var(--surface);
  }}
  .evidence-card:hover {{ box-shadow: var(--shadow-md); }}
  .evidence-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    background: var(--accent-light);
    font-size: 0.85em;
    border-bottom: 1px solid var(--border-light);
  }}
  .evidence-relation {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.82em;
    letter-spacing: 0.3px;
  }}
  .evidence-relation.support {{ background: var(--good-bg); color: var(--good); }}
  .evidence-relation.attack {{ background: var(--bad-bg); color: var(--bad); }}
  .evidence-relation.neutral {{ background: var(--neutral-bg); color: var(--neutral); }}
  .evidence-claim {{ color: var(--muted); font-size: 0.9em; }}
  .evidence-body {{ padding: 14px 16px; }}
  .evidence-title {{ font-weight: 600; margin-bottom: 8px; font-size: 1em; color: var(--text); }}
  .evidence-content {{ font-size: 0.9em; color: var(--text-secondary); line-height: 1.7; margin-bottom: 10px; }}
  .evidence-credibility {{ display: flex; align-items: center; gap: 8px; font-size: 0.82em; color: var(--muted); }}
  .cred-bar {{ flex: 1; height: 6px; background: var(--neutral-bg); border-radius: 3px; overflow: hidden; }}
  .cred-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }}
  .cred-fill.high {{ background: var(--good); }}
  .cred-fill.mid {{ background: var(--callout-warning); }}
  .cred-fill.low {{ background: var(--bad); }}
  .evidence-footer {{
    padding: 10px 16px;
    border-top: 1px solid var(--border-light);
    font-size: 0.85em;
    background: var(--bg);
  }}
  .evidence-source {{ color: var(--accent); text-decoration: none; }}
  .evidence-source:hover {{ text-decoration: underline; }}

  /* ================================================================
     报告正文通用样式（Markdown → HTML 渲染结果）
     ================================================================ */
  .report-body, .chapter {{
    padding: 0 4px;
  }}
  .report-body h2, .chapter h2 {{
    font-size: 1.4em;
    margin: 36px 0 14px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--accent);
    color: var(--accent);
    font-weight: 700;
  }}
  .report-body h3, .chapter h3 {{
    font-size: 1.2em;
    margin: 28px 0 10px;
    color: var(--text);
    font-weight: 600;
  }}
  .report-body h4, .chapter h4 {{
    font-size: 1.05em;
    margin: 22px 0 8px;
    color: var(--text-secondary);
    font-weight: 600;
  }}
  .report-body p, .chapter p {{ margin: 12px 0; line-height: 1.9; color: var(--text); }}
  .report-body ul, .report-body ol, .chapter ul, .chapter ol {{ margin: 12px 0; padding-left: 24px; }}
  .report-body li, .chapter li {{ margin: 6px 0; line-height: 1.7; }}
  .report-body table, .chapter table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 16px 0;
    font-size: 0.9em;
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
  }}
  .report-body th, .report-body td, .chapter th, .chapter td {{
    padding: 12px 16px;
    border: 1px solid var(--border);
    text-align: left;
  }}
  .report-body th, .chapter th {{
    background: var(--accent-light);
    font-weight: 600;
    color: var(--accent);
    font-size: 0.9em;
    letter-spacing: 0.3px;
  }}
  .report-body tr:nth-child(even), .chapter tr:nth-child(even) {{ background: var(--bg); }}
  .report-body blockquote, .chapter blockquote {{
    border-left: 4px solid var(--accent);
    padding: 16px 20px;
    margin: 16px 0;
    background: var(--accent-light);
    border-radius: 0 var(--radius) var(--radius) 0;
    color: var(--text-secondary);
    font-style: italic;
  }}
  .report-body blockquote p, .chapter blockquote p {{ margin: 0; }}
  .report-body hr, .chapter hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}
  .report-body code {{
    background: var(--neutral-bg);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.88em;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  }}
  .report-body pre {{
    background: var(--surface);
    padding: 18px 20px;
    border-radius: var(--radius);
    overflow-x: auto;
    margin: 16px 0;
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
  }}
  .section {{
    margin-bottom: 24px;
    background: var(--surface);
    border-radius: var(--radius);
    padding: 24px;
    box-shadow: var(--shadow-sm);
    border: 1px solid var(--border-light);
  }}

  /* ================================================================
     判定标语 & 报告页脚
     ================================================================ */
  .verdict-banner {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 24px;
    margin: 24px 0;
    border-radius: var(--radius);
    font-size: 1.1em;
    font-weight: 600;
  }}
  .verdict-banner.true {{ background: var(--good-bg); color: var(--good); border: 1px solid var(--good-light); }}
  .verdict-banner.false {{ background: var(--bad-bg); color: var(--bad); border: 1px solid var(--bad-light); }}
  .verdict-banner.uncertain {{ background: var(--neutral-bg); color: var(--neutral); border: 1px solid var(--border); }}
  .verdict-icon {{ font-size: 1.4em; }}
  .report-footer {{
    margin-top: 48px;
    padding: 20px 0;
    border-top: 1px solid var(--border);
    text-align: center;
    color: var(--muted);
    font-size: 0.85em;
  }}

  .verdict-body {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .verdict-confidence {{
    font-size: 0.9em;
    opacity: 0.85;
  }}
  .verdict-conclusion {{
    margin: 8px 0 0;
    font-size: 0.9em;
    line-height: 1.7;
    font-weight: 400;
    opacity: 0.9;
  }}

  /* ================================================================
     报告模板 Section（声明拆解 / 证据分析 / 附注）
     ================================================================ */
  .section-title {{
    font-size: 1.3em;
    color: var(--accent);
    margin: 36px 0 8px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--accent);
    font-weight: 700;
  }}
  .section-desc {{
    color: var(--text-secondary);
    font-size: 0.9em;
    margin-bottom: 20px;
  }}
  .claim-list {{
    margin: 12px 0 24px;
    padding-left: 24px;
    line-height: 2;
  }}
  .claim-list li {{
    padding: 8px 0;
    border-bottom: 1px solid var(--border-light);
  }}
  .claim-list li strong {{
    color: var(--accent);
  }}

  /* ================================================================
     声明分析卡片（逐段 LLM 生成）
     ================================================================ */
  .claim-card {{
    margin: 28px 0;
    background: var(--surface);
    border-radius: var(--radius-lg);
    padding: 28px;
    box-shadow: var(--shadow-md);
    border: 1px solid var(--border-light);
  }}
  .claim-card-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }}
  .claim-number {{
    font-size: 1.15em;
    font-weight: 700;
    color: var(--accent);
  }}
  .claim-type-badge {{
    display: inline-block;
    padding: 2px 12px;
    border-radius: 12px;
    font-size: 0.82em;
    font-weight: 600;
    background: var(--accent-light);
    color: var(--accent);
  }}
  .claim-text {{
    margin: 12px 0 20px;
    padding: 14px 18px;
    background: var(--bg);
    border-left: 4px solid var(--accent);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-style: italic;
    color: var(--text-secondary);
    font-size: 0.95em;
  }}
  .claim-analysis h4 {{
    font-size: 1.05em;
    margin-bottom: 10px;
    color: var(--text);
  }}
  .claim-analysis p {{
    color: var(--text-secondary);
    line-height: 1.8;
    margin-bottom: 16px;
  }}
  .evidence-list {{
    margin: 16px 0;
  }}
  .claim-verdict {{
    margin-top: 20px;
    padding: 14px 18px;
    background: var(--accent-light);
    border-radius: var(--radius);
    font-size: 0.95em;
  }}
  .claim-verdict .verdict-label {{ font-weight: 700; color: var(--accent); }}
  .claim-verdict .verdict-value {{ color: var(--text); }}

  /* ================================================================
     响应式
     ================================================================ */
  @media (max-width: 700px) {{
    body {{ padding: 16px 12px; }}
    .hero {{ padding: 24px 20px; }}
    .hero h1 {{ font-size: 1.4em; }}
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
    .evidence-header {{ flex-wrap: wrap; }}
    .section {{ padding: 16px; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>"""

    # ================================================================
    # 遗留：Markdown → HTML 转换（用于 render_llm 降级路径）
    # ================================================================

    def _md_to_html(self, md: str) -> str:
        """简单的 Markdown → HTML 转换（保留用于降级路径）"""
        html = md

        # 代码块
        html = re.sub(
            r"```(\w*)\n(.*?)```",
            lambda m: f"<pre><code>{self._escape(m.group(2))}</code></pre>",
            html,
            flags=re.DOTALL,
        )

        # 行内代码
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)

        # 表格
        html = re.sub(
            r"((?:\|.+\|\n)+)",
            self._convert_table,
            html,
        )

        # 标题
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)

        # 水平线
        html = re.sub(r"^---+\s*$", r"<hr>", html, flags=re.MULTILINE)

        # 无序列表
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"(<li>.*</li>\n?)+", self._wrap_list, html)

        # 有序列表
        html = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)

        # 加粗
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

        # 链接
        html = re.sub(
            r"\[(.+?)\]\((.+?)\)",
            lambda m: f'<a href="{self._escape(m.group(2))}" target="_blank" rel="noopener">{self._escape(m.group(1))}</a>',
            html,
        )

        # 段落：连续非空行
        lines = html.split("\n")
        result: List[str] = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                continue
            if stripped.startswith("<h") or stripped.startswith("<hr") or stripped.startswith("<pre") or stripped.startswith("<table") or stripped.startswith("<li") or stripped.startswith("</"):
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(stripped)
            elif stripped.startswith("<ul>"):
                in_list = True
                result.append(stripped)
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(f"<p>{stripped}</p>")
        if in_list:
            result.append("</ul>")

        return "\n".join(result)

    def _convert_table(self, match: re.Match) -> str:
        """Markdown 表格转 HTML"""
        lines = match.group(1).strip().split("\n")
        if len(lines) < 2:
            return match.group(0)

        rows: List[str] = []
        for i, line in enumerate(lines):
            if i == 1 and re.match(r"^[\s|:-]+$", line):
                continue
            cells = [c.strip() for c in line.strip(" |").split("|")]
            tag = "th" if i == 0 else "td"
            rows.append(
                "<tr>" + "".join(f"<{tag}>{self._escape(c)}</{tag}>" for c in cells) + "</tr>"
            )

        return "<table><thead>" + rows[0] + "</thead><tbody>" + "".join(rows[1:]) + "</tbody></table>"

    def _wrap_list(self, match: re.Match) -> str:
        items = match.group(0)
        return "<ul>" + items + "</ul>"

    @staticmethod
    def _escape(text: str) -> str:
        """HTML 转义"""
        if not isinstance(text, str):
            text = str(text)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )


register_renderer("html", HTMLRenderer)
