"""F1 POST /internal/v1/fact-check — 事实核查（真实实现版）。

响应体仅包含三个字段：isTrue / conclusion / explanation。
"""
from __future__ import annotations

import json
import re
from fastapi import APIRouter, Depends

from src.main.python.api.deps import verify_internal_token
from src.main.python.api.schemas import (
    ApiResponse,
    FactCheckData,
    FactCheckRequest,
)
from src.main.python.main_agent import FactAgent

router = APIRouter(
    prefix="/internal/v1",
    tags=["fact-check"],
    dependencies=[Depends(verify_internal_token)],
)

# 全局缓存 FactAgent 实例，避免重复初始化
_fact_agent: FactAgent | None = None


def get_fact_agent() -> FactAgent:
    """获取或初始化 FactAgent 单例"""
    global _fact_agent
    if _fact_agent is None:
        _fact_agent = FactAgent(
            dataset="fever",
            model_name="doubao/doubao-seed-2-0-mini-260428",
            temperature=0.2,
        )
    return _fact_agent


def parse_verdict_from_results(results):
    """从 FactAgent 返回的 step list 里提取最终的 label 和 explanation"""
    final_verdict = {"label": None, "explanation": None}

    # 倒序查找 verdict_predictor 的输出
    for step in reversed(results):
        if isinstance(step, dict) and "verdict_predictor" in step:
            vp_data = step["verdict_predictor"]
            if "messages" in vp_data and len(vp_data["messages"]) > 0:
                msg_content = (
                    vp_data["messages"][0].content
                    if hasattr(vp_data["messages"][0], "content")
                    else str(vp_data["messages"][0])
                )
                # 尝试从消息里提取 JSON
                try:
                    parsed = json.loads(msg_content)
                    if "result" in parsed:
                        final_verdict = parsed["result"]
                    elif "label" in parsed:
                        final_verdict = parsed
                    break
                except (json.JSONDecodeError, TypeError):
                    pass

                # 再尝试提取代码块
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", msg_content)
                if match:
                    try:
                        parsed = json.loads(match.group(1))
                        if "result" in parsed:
                            final_verdict = parsed["result"]
                        elif "label" in parsed:
                            final_verdict = parsed
                        break
                    except json.JSONDecodeError:
                        pass

                # 最后尝试找子串
                content_lower = msg_content.lower()
                if "not_supported" in content_lower or "not supported" in content_lower:
                    final_verdict["label"] = "not_supported"
                elif "supported" in content_lower:
                    final_verdict["label"] = "supported"
                final_verdict["explanation"] = msg_content

    return final_verdict


@router.post(
    "/fact-check",
    response_model=ApiResponse[FactCheckData],
    summary="事实核查（真实实现，调用多智能体系统）",
)
def fact_check(req: FactCheckRequest) -> ApiResponse[FactCheckData]:
    # ----- 真实实现：调用 FactAgent -----
    agent = get_fact_agent()

    # 执行事实核查
    results = agent.process_claim(
        req.claim.strip(),
        recursion_limit=300,
        verbose=False,
    )

    # 解析结果
    verdict = parse_verdict_from_results(results)

    # 映射到接口格式
    label = verdict.get("label", "supported")
    explanation = verdict.get("explanation", "")

    # supported → isTrue=True, not_supported → isTrue=False
    is_true = label.lower() == "supported"

    # 生成结论文本
    if is_true:
        conclusion = "声明真实：多个权威来源相互印证。"
    else:
        conclusion = "声明虚假：与多方权威信息不符或证据不足。"

    data = FactCheckData(
        isTrue=is_true,
        conclusion=conclusion,
        explanation=explanation or "经多智能体系统分析完成事实核查。",
    )
    return ApiResponse[FactCheckData](data=data)
