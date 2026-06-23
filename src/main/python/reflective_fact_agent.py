"""ReflectiveFactAgent — 带反思循环的事实核查 Agent。

设计原则（开闭原则）：
- 不修改 FactAgent 的既有代码
- 通过组合（composition）包装 FactAgent
- 在 FactAgent 的标准流程之外，额外加入 BettaFish 风格的反思循环

反思循环（与 BettaFish 一致）：
1. 首次调用 FactAgent 完成标准核查
2. 反思当前证据是否充足（Reflection LLM）
3. 如不足，生成新的搜索查询
4. 执行补充搜索（复用 FactAgent 的证据检索工具）
5. 用新旧证据合并重新判定
6. 重复最多 MAX_REFLECTIONS 次
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.main.python.llms import create_chat_model
from src.main.python.main_agent import FactAgent
from src.main.python.prompts.reflection import (
    SYSTEM_PROMPT_REFLECTION,
    SYSTEM_PROMPT_EVIDENCE_UPDATE,
)

logger = logging.getLogger("reflective_fact_agent")


def _normalize_score_value(value) -> Optional[int]:
    """将分数归一化到 0-100 整数（与 fact_check.py 中的同名函数一致）"""
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number <= 1:
            number *= 100
        return max(0, min(100, round(number)))
    except (TypeError, ValueError):
        return None


class ReflectiveFactAgent:
    """带反思循环的事实核查 Agent（包装 FactAgent，不修改既有代码）"""

    MAX_REFLECTIONS = 2  # 与 BettaFish InsightEngine 一致（MAX_REFLECTIONS=3，我们取2减少延迟）

    def __init__(
        self,
        dataset: str = "fever",
        model_name: str = "doubao/doubao-seed-2-0-mini-260428",
        temperature: float = 0.2,
    ):
        # 内部持有 FactAgent 实例（不修改 FactAgent）
        self._agent = FactAgent(
            dataset=dataset,
            model_name=model_name,
            temperature=temperature,
        )
        # 反思和证据更新使用的 LLM（与主 Agent 同模型，但 temperature 更低）
        self._reflection_llm = create_chat_model(
            model_name=model_name,
            temperature=0.1,
        )
        self.dataset = dataset
        self.model_name = model_name

    @property
    def trace(self):
        """透传 trace 引用，方便外部读取推理路径"""
        return self._agent.trace

    def process_claim(
        self,
        claim: str,
        recursion_limit: int = 300,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """执行带反思循环的事实核查。

        返回：
            {
                "final_verdict": {"label": ..., "explanation": ..., "confidenceScore": ...},
                "reflection_rounds": N,  # 实际执行的反思轮数
                "all_evidences": [...],  # 所有轮次的证据汇总
                "reflection_log": [...]  # 每轮反思的日志
            }
        """
        # ---- 第 1 步：标准流程（首次核查）----
        logger.info("=== ReflectiveFactAgent: 第 1 步，标准流程 ===")
        results = self._agent.process_claim(
            claim.strip(),
            recursion_limit=recursion_limit,
            verbose=verbose,
        )

        # 解析结果
        from src.main.python.api.routers.fact_check import (
            _extract_claims_from_trace,
            _extract_evidence_items_from_trace,
            parse_verdict_from_results,
        )

        verdict = parse_verdict_from_results(results)
        events = self._agent.trace.events
        claims = _extract_claims_from_trace(events, claim.strip())
        label = verdict.get("label", "insufficient_evidence")
        evidence_items = _extract_evidence_items_from_trace(events, claims, label)

        all_evidences = evidence_items[:]
        reflection_log: List[Dict[str, Any]] = []
        final_verdict = verdict

        # ---- 第 2 步：反思循环 ----
        for round_idx in range(self.MAX_REFLECTIONS):
            logger.info("=== ReflectiveFactAgent: 反思第 %d 轮 ===", round_idx + 1)

            # 2a. 反思当前证据是否充足
            reflection_result = self._reflect(
                claim=claim.strip(),
                label=final_verdict.get("label", "insufficient_evidence"),
                confidence=final_verdict.get("confidenceScore"),
                explanation=final_verdict.get("explanation", ""),
                claims=claims,
                evidences=all_evidences,
            )

            reflection_log.append(reflection_result)

            if not reflection_result.get("need_more_search", False):
                logger.info("  证据已充足，停止反思")
                break

            # 2b. 执行补充搜索
            new_queries = reflection_result.get("new_search_queries", [])
            if not new_queries:
                logger.info("  没有需要补充搜索的查询")
                break

            new_evidences = self._do_supplemental_search(
                claim=claim.strip(),
                new_queries=new_queries,
                claims=claims,
                label=final_verdict.get("label", "insufficient_evidence"),
            )
            all_evidences.extend(new_evidences)

            # 2c. 用新旧证据合并更新判定
            if new_evidences:
                updated = self._update_verdict(
                    claim=claim.strip(),
                    current_verdict=final_verdict,
                    new_evidences=new_evidences,
                )
                if updated:
                    final_verdict = updated
                    logger.info("  判定已更新: %s (置信度: %s)",
                                final_verdict.get("label"),
                                final_verdict.get("confidenceScore"))
            else:
                logger.info("  补充搜索未找到新证据")

        return {
            "final_verdict": final_verdict,
            "reflection_rounds": len(reflection_log),
            "all_evidences": all_evidences,
            "reflection_log": reflection_log,
        }

    def _reflect(
        self,
        claim: str,
        label: str,
        confidence: Optional[int],
        explanation: str,
        claims: List[Any],
        evidences: List[Any],
    ) -> Dict[str, Any]:
        """反思当前证据是否充足，返回需要补充的搜索查询"""
        # 构建证据摘要
        evidence_summary = []
        for ev in evidences:
            evidence_summary.append({
                "claimOrder": getattr(ev, "claimOrder", 0),
                "title": getattr(ev, "evidenceTitle", "") or "",
                "source": getattr(ev, "sourceName", "") or "",
                "content": (getattr(ev, "evidenceContent", "") or "")[:200],
                "relation": getattr(ev, "relationType", "neutral"),
            })

        claims_summary = []
        for c in claims:
            claims_summary.append({
                "order": getattr(c, "claimOrder", 0),
                "text": getattr(c, "claimText", ""),
            })

        input_data = json.dumps({
            "claim": claim,
            "current_verdict": {
                "label": label,
                "confidenceScore": confidence,
                "conclusion": explanation[:300] if explanation else "",
            },
            "subclaims": claims_summary,
            "evidences": evidence_summary,
        }, ensure_ascii=False, indent=2)

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_REFLECTION},
                {"role": "user", "content": input_data},
            ]
            response = self._reflection_llm.invoke(messages)
            content = response.content

            # 解析 JSON
            parsed = self._extract_json(content)
            if parsed:
                return parsed
        except Exception as e:
            logger.warning("反思调用失败: %s", e)

        return {"need_more_search": False, "reasoning": "反思调用失败", "new_search_queries": []}

    def _do_supplemental_search(
        self,
        claim: str,
        new_queries: List[Dict[str, Any]],
        claims: List[Any],
        label: str,
    ) -> List[Any]:
        """执行补充搜索：全文搜索模式。

        直接调 search_service.search_fulltext()，对每条搜索结果的 URL
        用 Selenium 抓取正文 + LLM 抽取，返回每条结果作为一条证据。
        """
        from src.main.python.tools.search_service import search_fulltext

        new_evidences = []

        for q_info in new_queries:
            query = q_info.get("query", "")
            if not query:
                continue

            logger.info("  全文补充搜索: %s", query)
            try:
                results = search_fulltext(query, self.dataset, num_results=10)
            except Exception as e:
                logger.warning("  全文搜索失败: %s", e)
                continue

            if not results:
                logger.info("    无搜索结果")
                continue

            new_evidences.extend(results)
            logger.info("    → 本查询获得 %d 条证据", len(results))

        return new_evidences

    def _update_verdict(
        self,
        claim: str,
        current_verdict: Dict[str, Any],
        new_evidences: List[Any],
    ) -> Optional[Dict[str, Any]]:
        """基于补充证据更新判定"""
        new_evidence_text = []
        for ev in new_evidences:
            new_evidence_text.append({
                "content": getattr(ev, "evidenceContent", "") or "",
                "source": getattr(ev, "sourceName", "") or "",
                "relation": getattr(ev, "relationType", "neutral"),
            })

        input_data = json.dumps({
            "claim": claim,
            "current_verdict": {
                "label": current_verdict.get("label", "insufficient_evidence"),
                "confidenceScore": current_verdict.get("confidenceScore"),
                "explanation": (current_verdict.get("explanation") or "")[:500],
            },
            "new_evidences": new_evidence_text,
        }, ensure_ascii=False, indent=2)

        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_EVIDENCE_UPDATE},
                {"role": "user", "content": input_data},
            ]
            response = self._reflection_llm.invoke(messages)
            content = response.content

            parsed = self._extract_json(content)
            if parsed:
                return {
                    "label": parsed.get("updated_label", current_verdict.get("label")),
                    "confidenceScore": parsed.get("updated_confidence", current_verdict.get("confidenceScore")),
                    "explanation": parsed.get("updated_explanation", current_verdict.get("explanation")),
                }
        except Exception as e:
            logger.warning("证据更新调用失败: %s", e)

        return None

    def _extract_json(self, content: str) -> Optional[Dict[str, Any]]:
        """从 LLM 返回内容中提取 JSON"""
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end+1])
            except json.JSONDecodeError:
                pass
        return None
