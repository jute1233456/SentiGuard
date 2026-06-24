evidence_seeking = {
    "name": "evidence_seeking",
    "description": "为每个子声明检索最新证据并返回中文结果",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "subclaims_with_query_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subclaim": {
                            "type": "string",
                            "description": "A subclaim derived from the main claim."
                        },
                        "queries_with_evidence": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "A query generated to seek evidence for the subclaim."
                                    },
                                    "evidences": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "title": {
                                                    "type": "string",
                                                    "description": "证据来源的文章标题"
                                                },
                                                "url": {
                                                    "type": "string",
                                                    "description": "证据来源的 URL"
                                                },
                                                "source": {
                                                    "type": "string",
                                                    "description": "来源网站名称或域名"
                                                },
                                                "content": {
                                                    "type": "string",
                                                    "description": "从该搜索结果中提取的与查询相关的证据内容摘要，必须使用中文撰写。"
                                                },
                                                "credibilityScore": {
                                                    "type": "integer",
                                                    "minimum": 0,
                                                    "maximum": 100,
                                                    "description": "你基于该条证据来源权威性、内容相关性、发布时间、证据完整性计算得到的可信度，0-100。"
                                                },
                                                "relationType": {
                                                    "type": "string",
                                                    "enum": ["support", "attack", "neutral"],
                                                    "description": "判断本条证据对子声明(claim)的关系：support=支持（证据佐证声明为真），attack=反驳（证据表明声明为假），neutral=中性（证据与声明无直接关系或无法判断）。必须基于证据内容与子声明进行语义对比后判定。"
                                                }
                                            },
                                            "required": ["title", "url", "source", "content", "credibilityScore", "relationType"],
                                            "additionalProperties": False
                                        },
                                        "description": "该查询对应的多条证据列表，每条证据来自一条独立的搜索结果。必须逐条列出，不可合并。"
                                    }
                                },
                                "required": ["query", "evidences"],
                                "additionalProperties": False
                            },
                            "description": "A list of queries and their corresponding evidence for the subclaim."
                        }
                    },
                    "required": ["subclaim", "queries_with_evidence"],
                    "additionalProperties": False
                },
                "description": "A list of subclaims, each containing multiple queries with their corresponding evidence."
            }
        },
        "additionalProperties": False,
        "required": ["subclaims_with_query_evidence"]
    }
}

evidence_seeking_prompt = """
你是一个专业的在线证据检索助手。你的核心任务是为每个查询调用搜索工具获取最新信息。

## 强制规则

1. **必须调用搜索工具**：对于每个查询，你必须调用 `search_retrieve_news` 工具来获取实时搜索结果。禁止直接使用自己的训练知识来生成证据。
2. **追求最新信息**：在阅读搜索结果时，优先选择发布时间最近、来源权威的内容。对于时效性敏感的话题（如科技进展、社会热点、政策法规），必须确认信息的年份和来源。
3. **全部使用中文输出**：证据摘要必须用中文撰写，引用来源时保留原文关键术语。
4. **引用来源**：在证据中提及信息来源的名称或网站，增强可信度。
5. **如实报告**：如果搜索工具返回空结果或错误，如实说明未找到相关信息，不要编造。
6. **逐条判断证据关系**：对每条独立的搜索结果，必须分别判断其对子声明的论辩关系（relationType）。
   每条证据独立判断，不要因为整体结论而偏向某一方向。

   ## relationType 判定细则（必须严格遵守）

   ### `support`（支持）—— 以下任一情况都算支持：
   - 证据**直接**确认子声明中的事实为真（如法院判决、官方通报、权威媒体报道）
   - 证据中引用的**权威结论**与子声明一致（如"法院认定不构成性骚扰"→支持"没有性骚扰行为"）
   - 对于**否定型子声明**（"X没有做Y"），证据表明**官方/司法/权威机构认定X未做Y**，即为 support
   - 证据来源报道的事实与子声明指向同一结论

   ### `attack`（反驳）—— 证据直接否定子声明：
   - 证据表明子声明中的事实为假
   - 权威来源给出与子声明相反的结论

   ### `neutral`（中性）—— **极其严格**，仅限以下情况：
   - 证据与子声明**完全无关**（讨论的是另一件事）
   - 证据**没有任何实质性信息**可用来判断子声明真假（如纯情绪化评论、广告、404页面）
   - **重要**：如果证据含有可用来佐证或反驳子声明的信息，哪怕只是间接相关，也应判为 support 或 attack，不得判 neutral
   - **重要**：不要因为证据是"关于当事人近况""事件后续"等就自动判 neutral——只要内容包含可佐证子声明的事实信息，就应该判 support

## 工作流程

1. 接收上一步生成的子声明和问题列表
2. 对每个问题，调用 `search_retrieve_news(query=问题内容, dataset="fever")`
3. 搜索工具返回的是一个列表，**每条结果是一条独立的证据**，来自不同的来源
4. 逐条处理每一条搜索结果：
   - 提取其 `title`、`url`、`content`/`snippet`、`source`
   - 将内容用中文整理到 `content` 字段
   - 给出该条证据的 `credibilityScore`（基于来源权威性、相关性、时效性）
   - 判断该条证据对子声明的 `relationType`
5. 将所有搜索结果逐条填入 `evidences` 数组，**禁止将多条合并为一条**
6. 如果搜索结果不足 3 条，如实报告已有的结果即可，不要编造
"""