verdict_prediction = {
    "name": "verdict_prediction",
    "description": "Predicts whether the input claim is supported based on retrieved evidence.",
    "parameters": {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": ["supported", "not_supported"],
                        "description": "The verdict on whether the claim is supported by the evidence."
                    },
                    "explanation": {
                        "type": "string",
                        "description": "中文解释，基于证据说明判定理由，引用关键证据和来源。"
                    }
                },
                "required": ["label", "explanation"],
                "additionalProperties": False
            }
        },
        "required": ["result"],
        "additionalProperties": False
    }
}


verdict_prediction_prompt = """
你是一个事实核查判定助手，负责根据检索到的证据判断声明是否成立。

## 输入信息
需要进行事实核查的声明：
{claim}

以下是该声明的子声明、子问题以及每个问题的检索证据：
{cell}

## 判定流程

1. 分析检索到的证据
   - 审查所有与子声明相关的证据
   - 评估每条证据的可信度、一致性和可靠性

2. 投票机制判定
   - 如果多个来源强烈支持该子声明，判定为 "supported"
   - 如果多个来源与该子声明矛盾，判定为 "not_supported"
   - 如果证据混杂、不足或不明确，判定为 "not_supported"

3. 提供判定理由（**必须使用中文**）
   - 清晰解释为什么判定为 "supported" 或 "not_supported"
   - 引用影响你决定的关键证据
   - 如果证据不充分，说明局限性或不确定性
"""