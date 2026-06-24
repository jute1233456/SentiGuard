claim_decomposition = {
    "name": "claim_decomposition",
    "description": "Splits an input claim into multiple subclaims.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "subclaims": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The subclaims derived from the input claim."
            }
        },
        "additionalProperties": False,
        "required": ["subclaims"]
    }
}

claim_decomposition_examples = [
    {
        "input_claim": "武汉协和医院和同济医院都在武汉市江汉区",
        "subclaims": [
            "Located(武汉协和医院, 武汉市江汉区) ::: 验证武汉协和医院位于武汉市江汉区",
            "Located(武汉同济医院, 武汉市江汉区) ::: 验证武汉同济医院位于武汉市江汉区",
        ],
    },
    {
        "input_claim": "2020年东京奥运会于2021年7月23日至8月8日举行，中国代表团获得了38枚金牌",
        "subclaims": [
            "EventDate(2020年东京奥运会, 2021年7月23日-8月8日) ::: 验证2020年东京奥运会的举办日期为2021年7月23日至8月8日",
            "GoldMedalCount(中国代表团, 2020年东京奥运会, 38枚) ::: 验证中国代表团在2020年东京奥运会上获得了38枚金牌",
        ],
    },
    {
        "input_claim": "张教授在清华大学和北京大学都担任过教授职务",
        "subclaims": [
            "WorkedAt(张教授, 清华大学, 教授) ::: 验证张教授曾在清华大学担任教授",
            "WorkedAt(张教授, 北京大学, 教授) ::: 验证张教授曾在北京大学担任教授",
        ],
    },
]


claim_decomposition_prompt = f"""
你是一个声明拆解专家。给定一个需要事实核查的声明，你需要将其拆解为多个独立的一阶谓词逻辑子声明。

## 一阶谓词逻辑形式

每条子声明使用一阶谓词逻辑格式：
`谓词(主体, 客体, 属性...) ::: 用中文描述要验证的内容`

- **谓词**：用英文动词过去式（Located、Won、WorkedAt、IsA 等）
- **主体/客体**：用中文实体名称
- **::: 之后**：用中文描述要验证的内容

## 等价性原则（最重要）

拆解后的子声明集合必须与原声明**逻辑等价**，即：
- 原声明为真 **↔** 所有子声明同时满足预期的逻辑关系（AND/OR）

### AND 关系（并列）
原声明中的"和"、"都"、"且"等表示并列关系时：
- 原声明："武汉协和医院和同济医院都在武汉"
- 等价形式：Located(协和, 武汉) **AND** Located(同济, 武汉)
- 拆解：两个子声明**都**为真，原声明才为真

### OR 关系（选择）
原声明中的"或"、"或者"等表示选择关系时：
- 原声明："张教授在清华大学或北京大学担任过教授"
- 等价形式：WorkedAt(张教授, 清华) **OR** WorkedAt(张教授, 北大)
- 拆解：两个子声明**至少一个**为真，原声明即为真

## 适度拆分原则

每个子声明拆到**容易通过搜索验证的程度**即可，不要过度拆分。

- ✅ 正确：声明"张教授在清华或北大任职" → 拆为"在清华任职"和"在北大任职"
- ❌ 过度：声明"张雪峰是中国人" → 不必拆成"是北京人""是上海人""是广东人"...
  - "是中国人"本身就是一条容易验证的原子声明，无需再拆

过度拆分只会徒增搜索工作量，不会提高核查质量。

## 禁止包含关系

子声明之间不能是包含关系。如果子声明 A 成立时子声明 B 必然成立，说明 B 被 A 包含。
- ❌ 错误："中国在2020年奥运会上获得奖牌"（包含了"获得金牌"）
- ✅ 正确：
  - "中国在2020年奥运会上获得38枚金牌"
  - "中国在2020年奥运会上获得32枚银牌"

## 禁止重复（重要）

子声明之间**不能有重复**。同一个事实只拆一次，不能因为措辞不同就重复列出。

判断重复的标准：**如果两个子声明指向同一个可核查事实，只是在用词、语序、详略上不同，则视为重复，只保留一条。**

- ❌ 错误（同一意思重复拆）：
  - 原声明："2026年以来经常发生成年人被送进戒网瘾学校，有人在里面遭受虐待甚至致残"
  - 错误拆解（6条，实际只有3个独立事实）：
    - "成年人被送往戒网瘾学校"
    - "机构中存在囚禁虐待行为"
    - "机构中出现了致残死亡等严重后果"
    - "成年人被抓紧戒网瘾学校等地方" ← 与第1条重复
    - "很多人在里面遭受囚禁虐待" ← 与第2条重复
    - "出现了致残死亡等严重后果" ← 与第3条重复
  - ✅ 正确拆解（3条即可）：
    - "成年人被送往戒网瘾学校或行为矫正机构"
    - "这些机构中存在囚禁虐待行为"
    - "这些机构中出现了致残死亡等严重后果"

- ❌ 错误：原声明"昨天张三打了李四，张三把李四揍了" → "张三打了李四"和"张三揍了李四"重复
- ✅ 正确："张三打了李四"

## 完整性原则

拆解必须覆盖原声明中所有可核查的断言，不能遗漏。
- 原声明中有几个独立的实体、事件、属性，就应该拆出几条
- 时间、地点、数量、关系等每个维度都要考虑

以下是示例：
{claim_decomposition_examples}

返回格式为 JSON，包含 subclaims 数组。
"""


claim_classification = {
    "name": "claim_classification",
    "description": "Classifies subclaims as either 'verifiable' or 'non-verifiable'.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "subclaim_type_dict": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subclaim": {"type": "string", "description": "The subclaim text."},
                        "type": {
                            "type": "string",
                            "enum": ["verifiable", "non-verifiable"],
                            "description": "Classification type of the subclaim."
                        }
                    },
                    "required": ["subclaim", "type"],
                    "additionalProperties": False
                },
                "description": "A list of subclaims with their classification types."
            }
        },
        "additionalProperties": False,
        "required": ["subclaim_type_dict"]
    }
}


claim_classification_prompt = r"""
You are an expert in claim verification. Your task is to determine whether a given claim is verifiable or non-verifiable.
A verifiable claim is a factual statement that can be checked against objective evidence from reliable sources. It makes specific assertions about the world that can be proven true or false through investigation.

A non-verifiable claim is one that cannot be objectively verified because it:
- Expresses a subjective opinion, preference, or personal experience  
- Makes vague or ambiguous statements without specific details  
- Refers to future events that haven't occurred yet  
- Makes normative or ethical judgments about what "should" be  
- Contains hypothetical scenarios or counterfactuals  

### Examples:
Verifiable: "The average global temperature increased by 0.8$^\circ$C between 1880 and 2012." 
Non-verifiable: "Climate change is the most important issue facing humanity today."  
Verifiable: "The film 'Parasite' won the Academy Award for Best Picture in 2020."  
Non-verifiable: "Parasite deserved to win the Academy Award for Best Picture."

Please analyze the following claim and classify it as either VERIFIABLE or NON-VERIFIABLE. Provide a brief explanation for your classification.
"""


claim_splitting = {
    "name": "claim_splitting",
    "description": "Verifiable subclaims only",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "subclaims": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The verifiable subclaims after filtering out non-verifiable subclaims"
            }
        },
        "additionalProperties": False,
        "required": ["subclaims"]
    }
}
claim_splitter_prompt = """
你是一个声明清洗专家。你的任务是对拆解后的子声明列表进行两步清洗：

## 第一步：去重与消除包含关系

检查子声明之间是否存在**语义重复**或**包含关系**：

### 1.1 语义重复的处理
如果两个子声明指向同一个可核查事实，只是措辞不同，则视为语义重复。
→ **删除序号大的那个**（保留序号小的）。

例如：
- ["A是中国人", "A是中国人"] → 第1条和第2条语义重复，删除第2条
- ["2026年高考难度增加", "2026全国卷高考难度提升"] → 语义重复，保留第1条，删除第2条

### 1.2 包含关系的处理
如果子声明 A 成立时子声明 B 必然成立（即 A 包含 B），则 A 是范围大的，B 是范围小的。
→ **修改范围大的那个**，删去与 B 重叠的部分，使两者不再有包含关系。

例如：
- 输入：["中国在奥运会上获得奖牌", "中国在奥运会上获得金牌"]
  - "获得奖牌"包含"获得金牌"
  - 修改范围大的第1条 → "中国在奥运会上获得非金牌的奖牌"
  - 保留第2条 → "中国在奥运会上获得金牌"
  - 结果：["中国在奥运会上获得非金牌的奖牌", "中国在奥运会上获得金牌"]

- 输入：["2026年高考难度增加", "2026年全国卷数学高考难度增加"]
  - "高考难度增加"包含"全国卷数学高考难度增加"
  - 修改范围大的第1条 → "2026年高考除数学外其他科目难度增加"
  - 保留第2条 → "2026年全国卷数学高考难度增加"
  - 结果：["2026年高考除数学外其他科目难度增加", "2026年全国卷数学高考难度增加"]

## 第二步：过滤不可核查

从去重后的列表中，只保留 verifiable（可核查）类型的子声明。
过滤掉 non-verifiable（不可核查）类型的子声明。

如果所有子声明都被过滤掉，返回 ["NON-SUPPORTED"]。
"""
