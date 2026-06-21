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
                                    "evidence": {
                                        "type": "string",
                                        "description": "搜索引擎返回的中文证据摘要，必须使用中文撰写，包含最新数据和具体来源。"
                                    }
                                },
                                "required": ["query", "evidence"],
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

## 工作流程

1. 接收上一步生成的子声明和问题列表
2. 对每个问题，调用 `search_retrieve_news(query=问题内容, dataset="fever")`
3. 从搜索结果中提取与问题直接相关的信息
4. 将提取的证据用中文整理到 `evidence` 字段
"""

