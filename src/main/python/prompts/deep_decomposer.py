"""深度核查声明拆解器 — 带反思机制的声明分解。

流程：
1. 初始拆解（LLM 首轮生成）
2. N 轮反思（检查重复/包含/过于庞大，可配置反思次数）
3. 输出最终子声明列表
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .deep_claim_decomposition import (
    DEFAULT_DEEP_REFLECTION_COUNT,
    SYSTEM_PROMPT_DEEP_DECOMPOSITION,
    SYSTEM_PROMPT_DEEP_DECOMPOSITION_REFLECTION,
)
from src.main.python.llms import create_chat_model

logger = logging.getLogger("deep_claim_decomposer")


class DeepClaimDecomposer:
    """深度核查声明拆解器 — 带反思循环。"""

    def __init__(
        self,
        model_name: str = "doubao/doubao-seed-2-0-mini-260428",
        reflection_count: int = DEFAULT_DEEP_REFLECTION_COUNT,
        temperature: float = 0.2,
    ):
        self.model_name = model_name
        self.reflection_count = reflection_count
        self.llm = create_chat_model(
            model_name=model_name,
            temperature=temperature,
        )
        self._reflection_log: List[Dict[str, Any]] = []

    @property
    def reflection_log(self) -> List[Dict[str, Any]]:
        return list(self._reflection_log)

    def decompose(self, claim: str) -> List[str]:
        """对声明进行带反思的深度拆解。

        返回最终的子声明文本列表。
        """
        self._reflection_log = []

        # 第1步：初始拆解
        logger.info("深度声明拆解: 首轮生成")
        subclaims = self._initial_decomposition(claim)
        if not subclaims:
            logger.warning("首轮拆解失败，返回原始声明")
            self._reflection_log.append({
                "round": 0,
                "type": "initial_failed",
                "subclaims": [claim],
                "summary": "首轮拆解失败（LLM 调用异常或 JSON 解析失败），保留原始声明",
            })
            return [claim]

        self._reflection_log.append({
            "round": 0,
            "type": "initial",
            "subclaims": list(subclaims),
            "summary": f"首轮拆解得到 {len(subclaims)} 条子声明",
        })
        logger.info("首轮拆解: %d 条子声明", len(subclaims))

        # 第2步：反思循环
        for i in range(self.reflection_count):
            logger.info("深度声明拆解: 第 %d/%d 轮反思", i + 1, self.reflection_count)
            subclaims = self._reflection_round(subclaims, i + 1, self.reflection_count)
            if not subclaims:
                subclaims = self._get_previous_subclaims()
                break

        return subclaims

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = self.llm.invoke(messages)
        return response.content

    def _robust_json_loads(self, raw: str, context: str = "JSON") -> Optional[Dict[str, Any]]:
        """内联的鲁棒 JSON 解析（避免循环导入）"""
        if not raw or not raw.strip():
            return None
        text = raw.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end+1]
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return None

    def _initial_decomposition(self, claim: str) -> List[str]:
        """首轮拆解"""
        try:
            response = self._call_llm(SYSTEM_PROMPT_DEEP_DECOMPOSITION, claim)
            result = self._robust_json_loads(response, "深度声明拆解")
            if result:
                items = result.get("subclaims", [])
                if items and isinstance(items, list):
                    return [
                        item["subclaim"] if isinstance(item, dict) and "subclaim" in item
                        else (item if isinstance(item, str) else str(item))
                        for item in items
                    ]
            return []
        except Exception as e:
            logger.warning("首轮拆解异常: %s", e)
            return []

    def _reflection_round(self, current_claims: List[str], current_round: int, total_rounds: int) -> List[str]:
        """单轮反思"""
        try:
            claims_json = json.dumps(current_claims, ensure_ascii=False, indent=2)
            system_prompt = SYSTEM_PROMPT_DEEP_DECOMPOSITION_REFLECTION.format(
                current_round=current_round,
                total_rounds=total_rounds,
                claims_json=claims_json,
            )
            response = self._call_llm(system_prompt, "请检查并优化以上子声明列表。")
            result = self._robust_json_loads(response, f"深度声明拆解反思第{current_round}轮")

            if result:
                new_claims = result.get("subclaims", [])
                summary = result.get("reflection_summary", "")

                if new_claims and isinstance(new_claims, list):
                    self._reflection_log.append({
                        "round": current_round,
                        "type": "reflection",
                        "subclaims": list(new_claims),
                        "summary": summary,
                    })
                    logger.info("  反思结果: %s -> %d 条", summary, len(new_claims))
                    return [str(c) for c in new_claims]

            # 解析失败，保留当前列表
            self._reflection_log.append({
                "round": current_round,
                "type": "reflection_failed",
                "subclaims": list(current_claims),
                "summary": "JSON 解析失败，保留当前列表",
            })
            return list(current_claims)

        except Exception as e:
            logger.warning("反思第%d轮异常: %s", current_round, e)
            return list(current_claims)

    def _get_previous_subclaims(self) -> List[str]:
        """获取上一个有效轮次的子声明"""
        for entry in reversed(self._reflection_log):
            if entry.get("subclaims"):
                return list(entry["subclaims"])
        return []


__all__ = [
    "DeepClaimDecomposer",
    "DEFAULT_DEEP_REFLECTION_COUNT",
]
