"""证据合并节点 — 将同一事件的多来源证据合并为一条。

由 evidence_merger 节点使用，输入是 evidence_seeker 的输出（多条独立证据），
输出是合并后的 merged_evidences[] 数组。
"""
from __future__ import annotations

evidence_merging = {
    "name": "evidence_merging",
    "description": "将同一事件/事实的多来源报道合并为一条证据，汇总来源以增强可信度",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "merged_evidences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claimOrder": {
                            "type": "integer",
                            "description": "该条证据对应的子声明序号，从 1 递增"
                        },
                        "claimText": {
                            "type": "string",
                            "description": "该条证据对应的子声明文本"
                        },
                        "summary": {
                            "type": "string",
                            "description": "合并后的证据摘要，综合所有来源的信息，用中文撰写"
                        },
                        "relationType": {
                            "type": "string",
                            "enum": ["support", "attack", "neutral"],
                            "description": "合并后该条证据对子声明的论辩关系：support=支持，attack=反驳，neutral=中性"
                        },
                        "credibilityScore": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "合并后的可信度评分。来源数量越多、来源越权威、内容一致性越高，分数越高。0-100。"
                        },
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "来源文章标题"
                                    },
                                    "url": {
                                        "type": "string",
                                        "description": "来源 URL"
                                    },
                                    "source": {
                                        "type": "string",
                                        "description": "来源网站名称或域名"
                                    }
                                },
                                "required": ["title", "url", "source"],
                                "additionalProperties": False
                            },
                            "description": "该条合并证据涉及的所有来源列表。同一事件被多家媒体报道时，将所有来源逐条列出。"
                        }
                    },
                    "required": ["claimOrder", "claimText", "summary", "relationType", "credibilityScore", "sources"],
                    "additionalProperties": False
                },
                "description": "合并后的证据列表。同一事件/事实被多个来源报道时合并为一条，sources 数组中列出所有来源。"
            }
        },
        "required": ["merged_evidences"],
        "additionalProperties": False
    }
}

evidence_merging_prompt = """
你是一个证据合并助手。你的任务是将上一步检索到的多条独立证据进行智能合并。

## 输入信息

你将接收到上一步 evidence_seeker 的输出，包含每个子声明对应的多条搜索结果（每条独立为一条证据）。

## 合并规则

1. **识别同一事件**：仔细分析所有证据的内容，识别哪些证据描述的是同一事件、同一事实或同一论断。判断依据：
   - 核心事实相同（时间、地点、人物、事件要素一致）
   - 只是报道角度、措辞或来源不同
   - 内容高度重叠

2. **合并同类证据**：将指向同一事件/事实的多条证据合并为一条 merged_evidence：
   - `summary`：综合所有来源的信息撰写一段完整的证据摘要
   - `sources`：将涉及的所有来源逐条列入数组（保留各自的 title、url、source）
   - `relationType`：基于合并后的整体内容判断对子声明的关系
   - `credibilityScore`：根据来源数量、来源权威性、内容一致性综合重新评分

3. **保留独立证据**：对于无法与其他证据合并的独立证据，保持其单独存在（sources 数组中只有一条）。

4. **不丢失信息**：合并时不要丢弃任何来源。反驳性（attack）和中性（neutral）证据同样需要保留，不能因为与支持性证据立场不同就丢弃。

5. **正确分配 claimOrder**：确保每条 merged_evidence 对应正确的子声明序号和文本。

## 可信度评分规则（credibilityScore）

合并后重新评分，考虑以下因素：
- **来源数量**：越多独立来源报道同一事件，分数越高（2-3 个来源 +10~15 分）
- **来源权威性**：官方/权威媒体 > 正规新闻 > 普通网站 > 自媒体/未知来源
- **内容一致性**：各来源报道内容一致、相互印证 → 加分
- **信息详细程度**：有具体细节、数据、引用的证据分数更高

## 输出要求

输出 `merged_evidences` 数组，每条包含完整的 sources 列表。
"""
