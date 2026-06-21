query_generation = {
    "name": "query_generation",
    "description": "Generates questions based on given subclaims.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "subclaim_with_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subclaim": {
                            "type": "string",
                            "description": "A subclaim derived from the main claim."
                        },
                        "questions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of questions generated based on the subclaim."
                        }
                    },
                    "required": ["subclaim", "questions"],
                    "additionalProperties": False
                },
                "description": "A list of subclaims, each with a corresponding set of generated questions."
            }
        },
        "additionalProperties": False,
        "required": ["subclaim_with_questions"]
    }
}

query_generation_prompt = """
你是一个搜索查询生成助手。为每个子声明生成适合搜索引擎的中文搜索问题，用于检索证据验证声明。

## 规则

1. **面向最新信息**：生成的问题要能检索到最新的相关信息，对于时效性敏感话题，在问题中暗示需要最新数据。
2. **全部使用中文**：搜索问题必须是中文，因为搜索源是中文内容。
3. **多样性**：从不同角度和维度生成问题，覆盖不同的关键词和表述方式。
4. **具体明确**：包含具体实体名称和关键术语，避免模糊泛泛的提问。
5. **简洁**：每个问题控制在20字以内，适合搜索引擎。

返回格式：
[
    {"claim": "子声明内容", "questions": ["搜索问题1", "搜索问题2", ...]}
]
"""
