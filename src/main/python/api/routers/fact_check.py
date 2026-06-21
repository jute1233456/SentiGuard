"""F1 POST /internal/v1/fact-check — 事实核查（真实实现版）。

响应体仅包含三个字段：isTrue / conclusion / explanation。
"""
from __future__ import annotations

import json
import logging
import re
from fastapi import APIRouter, Depends

from src.main.python.api.deps import verify_internal_token
from src.main.python.api.schemas import (
    ApiResponse,
    EvidenceItem,
    FactCheckData,
    FactCheckDetailData,
    FactCheckRequest,
    FactCheckTrace,
    TraceRoute,
    TraceStep,
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

    # 记录 trace 文件路径，便于后端联调按路径取推理过程
    if agent.trace.trace_file is not None:
        logging.getLogger("fact_check").info(
            "trace file: %s | claim: %s",
            agent.trace.trace_file, req.claim.strip()[:80],
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


# ======================================================================
# F2 POST /internal/v1/fact-check/detail — 详细版（含推理过程 + 证据链）
# ======================================================================


def _build_detail_response(agent: FactAgent, req: FactCheckRequest) -> FactCheckDetailData:
    """执行核查并组装详细响应体（含 trace + evidenceItems）。"""
    results = agent.process_claim(
        req.claim.strip(),
        recursion_limit=300,
        verbose=False,
    )

    # 记录 trace 文件路径
    if agent.trace.trace_file is not None:
        logging.getLogger("fact_check").info(
            "trace file: %s | claim: %s",
            agent.trace.trace_file, req.claim.strip()[:80],
        )

    # ---- 解析 verdict ----
    verdict = parse_verdict_from_results(results)
    label = verdict.get("label", "supported")
    explanation = verdict.get("explanation", "")
    is_true = label.lower() == "supported"
    if is_true:
        conclusion = "声明真实：多个权威来源相互印证。"
    else:
        conclusion = "声明虚假：与多方权威信息不符或证据不足。"

    # ---- 从 trace events 构建推理路径 ----
    events = agent.trace.events

    route = [
        TraceRoute(graph=e["graph"], next=e["next"])
        for e in events if e["type"] == "supervisor"
    ]
    steps = [
        TraceStep(node=e["node"], output=e.get("structured_response"))
        for e in events if e["type"] == "step"
    ]
    searches = [
        EvidenceItem(
            subclaim="",
            query=e.get("query", ""),
            chosenUrl=e.get("chosen_url", ""),
            evidenceSnippet=e.get("evidence_snippet", ""),
        )
        for e in events if e["type"] == "search"
    ]
    verdict_event = None
    for e in events:
        if e["type"] == "verdict":
            verdict_event = {"label": e.get("label"), "explanation": e.get("explanation")}
            break

    trace_data = FactCheckTrace(
        runId=agent.trace.run_id,
        claim=agent.trace.claim,
        route=route,
        steps=steps,
        searches=searches,
        verdict=verdict_event,
    )

    # ---- 展平证据（把 search 事件的 evidence 映射到 subclaim 上下文） ----
    # 尝试从 evidence_seeker step 中提取 subclaim → query 映射
    subclaim_map: dict[str, str] = {}
    for e in events:
        if e["type"] == "step" and e["node"] == "evidence_seeker":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaims_with_query_evidence") or []:
                sc = item.get("subclaim", "")
                for qe in item.get("queries_with_evidence") or []:
                    subclaim_map[qe.get("query", "")] = sc

    evidence_items = [
        EvidenceItem(
            subclaim=subclaim_map.get(s.query, ""),
            query=s.query,
            chosenUrl=s.chosenUrl,
            evidenceSnippet=s.evidenceSnippet,
        )
        for s in searches
    ]

    return FactCheckDetailData(
        isTrue=is_true,
        conclusion=conclusion,
        explanation=explanation or "经多智能体系统分析完成事实核查。",
        trace=trace_data,
        evidenceItems=evidence_items,
    )


@router.post(
    "/fact-check/detail",
    response_model=ApiResponse[FactCheckDetailData],
    summary="事实核查（详细版，含推理过程与证据链）",
)
def fact_check_detail(req: FactCheckRequest) -> ApiResponse[FactCheckDetailData]:
    data = _build_detail_response(get_fact_agent(), req)
    return ApiResponse[FactCheckDetailData](data=data)
