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
        """生成完整 HTML 页面（含增强 CSS）"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._escape(title)}</title>
<style>
  :root {{
    --bg: #ffffff;
    --text: #1a1a2e;
    --muted: #6c757d;
    --border: #e9ecef;
    --accent: #4361ee;
    --accent-light: #eef0ff;
    --good: #2d6a4f;
    --good-bg: #d8f3dc;
    --bad: #9b2226;
    --bad-bg: #f8d7da;
    --neutral: #6c757d;
    --neutral-bg: #e9ecef;
    --shadow: 0 2px 8px rgba(0,0,0,0.08);
    --radius: 12px;
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
      --bg: #0f0f1a;
      --text: #e0e0e0;
      --muted: #9ca3af;
      --border: #2d2d44;
      --accent: #6c8cff;
      --accent-light: #1a1a3e;
      --good: #52b788;
      --good-bg: #1b3a2a;
      --bad: #ef4444;
      --bad-bg: #3b1a1a;
      --neutral-bg: #2d2d44;
      --shadow: 0 2px 8px rgba(0,0,0,0.3);
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
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.8;
    max-width: 960px;
    margin: 0 auto;
    padding: 24px 20px;
  }}

  /* Hero 区域 */
  .hero {{ margin-bottom: 32px; padding: 32px; background: var(--accent-light); border-radius: var(--radius); }}
  .hero h1 {{ font-size: 1.8em; margin-bottom: 16px; color: var(--accent); }}
  .hero .summary {{ font-size: 1.05em; color: var(--text); line-height: 1.8; }}
  .findings {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 20px; }}
  .finding {{ padding: 12px 16px; background: var(--bg); border-radius: 8px; border-left: 3px solid var(--accent); }}
  .finding strong {{ display: block; margin-bottom: 4px; color: var(--accent); }}
  .finding p {{ font-size: 0.9em; color: var(--muted); margin: 0; }}

  /* KPI 卡片 */
  .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 32px; }}
  .kpi-card {{ padding: 16px; border-radius: var(--radius); text-align: center; box-shadow: var(--shadow); }}
  .kpi-card.good {{ background: var(--good-bg); }}
  .kpi-card.bad {{ background: var(--bad-bg); }}
  .kpi-card.neutral {{ background: var(--neutral-bg); }}
  .kpi-label {{ font-size: 0.8em; color: var(--muted); margin-bottom: 4px; }}
  .kpi-value {{ font-size: 1.4em; font-weight: 700; }}

  /* 章节 */
  .chapter {{ margin-bottom: 32px; }}

  /* Callout 提示框 */
  .callout {{ display: flex; gap: 12px; padding: 16px; margin: 16px 0; border-radius: var(--radius); border-left: 4px solid; }}
  .callout-info {{ background: var(--callout-info-bg); border-color: var(--callout-info); }}
  .callout-warning {{ background: var(--callout-warning-bg); border-color: var(--callout-warning); }}
  .callout-success {{ background: var(--callout-success-bg); border-color: var(--callout-success); }}
  .callout-danger {{ background: var(--callout-danger-bg); border-color: var(--callout-danger); }}
  .callout-icon {{ font-size: 1.3em; line-height: 1.4; flex-shrink: 0; }}
  .callout-title {{ font-weight: 600; margin-bottom: 6px; }}
  .callout-body p {{ margin: 4px 0; }}
  .callout-body ul, .callout-body ol {{ margin: 4px 0; padding-left: 20px; }}

  /* 证据卡片 */
  .evidence-card {{ border: 1px solid var(--border); border-radius: var(--radius); margin: 12px 0; overflow: hidden; box-shadow: var(--shadow); }}
  .evidence-header {{ display: flex; align-items: center; gap: 10px; padding: 8px 14px; background: var(--accent-light); font-size: 0.85em; }}
  .evidence-relation {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 0.85em; }}
  .evidence-relation.support {{ background: var(--good-bg); color: var(--good); }}
  .evidence-relation.attack {{ background: var(--bad-bg); color: var(--bad); }}
  .evidence-relation.neutral {{ background: var(--neutral-bg); color: var(--neutral); }}
  .evidence-claim {{ color: var(--muted); }}
  .evidence-body {{ padding: 12px 14px; }}
  .evidence-title {{ font-weight: 600; margin-bottom: 6px; font-size: 1em; }}
  .evidence-content {{ font-size: 0.9em; color: var(--text); line-height: 1.7; margin-bottom: 8px; }}
  .evidence-credibility {{ display: flex; align-items: center; gap: 8px; font-size: 0.8em; color: var(--muted); }}
  .cred-bar {{ flex: 1; height: 6px; background: var(--neutral-bg); border-radius: 3px; overflow: hidden; }}
  .cred-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
  .cred-fill.high {{ background: var(--good); }}
  .cred-fill.mid {{ background: var(--callout-warning); }}
  .cred-fill.low {{ background: var(--bad); }}
  .evidence-footer {{ padding: 8px 14px; border-top: 1px solid var(--border); font-size: 0.85em; }}
  .evidence-source {{ color: var(--accent); text-decoration: none; }}
  .evidence-source:hover {{ text-decoration: underline; }}

  /* 报告正文通用样式 */
  .report-body, .chapter {{
    padding: 0 4px;
  }}
  .report-body h2, .chapter h2 {{ font-size: 1.4em; margin: 32px 0 12px; padding-bottom: 8px; border-bottom: 2px solid var(--accent); color: var(--accent); }}
  .report-body h3, .chapter h3 {{ font-size: 1.15em; margin: 24px 0 8px; color: var(--text); }}
  .report-body h4, .chapter h4 {{ font-size: 1.05em; margin: 20px 0 6px; color: var(--text); }}
  .report-body p, .chapter p {{ margin: 10px 0; line-height: 1.9; }}
  .report-body ul, .report-body ol, .chapter ul, .chapter ol {{ margin: 10px 0; padding-left: 24px; }}
  .report-body li, .chapter li {{ margin: 6px 0; line-height: 1.7; }}
  .report-body table, .chapter table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.9em; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
  .report-body th, .report-body td, .chapter th, .chapter td {{ padding: 10px 14px; border: 1px solid var(--border); text-align: left; }}
  .report-body th, .chapter th {{ background: var(--accent-light); font-weight: 600; color: var(--accent); }}
  .report-body tr:nth-child(even), .chapter tr:nth-child(even) {{ background: var(--accent-light); }}
  .report-body blockquote, .chapter blockquote {{ border-left: 4px solid var(--accent); padding: 12px 16px; margin: 12px 0; background: var(--accent-light); border-radius: 0 8px 8px 0; }}
  .report-body blockquote p, .chapter blockquote p {{ margin: 0; }}
  .report-body hr, .chapter hr {{ border: none; border-top: 1px solid var(--border); margin: 28px 0; }}
  .report-body code {{ background: var(--neutral-bg); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; font-family: 'JetBrains Mono', 'Fira Code', monospace; }}
  .report-body pre {{ background: var(--neutral-bg); padding: 16px; border-radius: 8px; overflow-x: auto; margin: 12px 0; }}
  .section {{ margin-bottom: 24px; }}

  @media (max-width: 600px) {{
    body {{ padding: 16px 12px; }}
    .hero {{ padding: 20px; }}
    .hero h1 {{ font-size: 1.4em; }}
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
    .evidence-header {{ flex-wrap: wrap; }}
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
