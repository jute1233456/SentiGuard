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
    FactCheckDetailDBData,
    FactCheckRequest,
    FactCheckTrace,
    F3ClaimItem,
    F3EvidenceItem,
    F3Report,
    F3Result,
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


# ======================================================================
# F3 POST /internal/v1/fact-check/detail/db — 数据库对齐版
# ======================================================================


def _infer_relation_type(label: str, evidence_count: int) -> str:
    """根据总体标签推断 evidence 的 relationType 默认值。"""
    if label == "supported":
        return "support"
    elif label == "not_supported":
        return "attack"
    return "neutral"


def _build_credibility_score(evidence_count: int, verdict_label: str) -> Optional[int]:
    """基于证据数量和判定结果估算可信度分数。"""
    if evidence_count == 0:
        return None
    base = 60
    if verdict_label == "supported":
        base += 20
    elif verdict_label == "not_supported":
        base += 15
    if evidence_count >= 3:
        base += 10
    elif evidence_count >= 2:
        base += 5
    return min(base, 100)


def _extract_claims_from_trace(events: list) -> list:
    """从 trace events 中提取所有可核查声明列表。"""
    claims = []
    seen = set()
    claim_order = 0
    for e in events:
        if e["type"] == "step" and e["node"] == "claim_splitter":
            sr = e.get("structured_response") or {}
            for sc in sr.get("subclaims") or []:
                text = sc.strip()
                if text and text not in seen:
                    seen.add(text)
                    claim_order += 1
                    claims.append(F3ClaimItem(
                        claimOrder=claim_order,
                        claimText=text,
                        claimType="verifiable",
                    ))
            break  # 只取 claim_splitter 的结果
    return claims


def _build_detail_db_response(agent: FactAgent, req: FactCheckRequest) -> FactCheckDetailDBData:
    """执行核查并组装数据库对齐版响应体。"""
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

    events = agent.trace.events

    # ---- 1. 解析 verdict ----
    verdict = parse_verdict_from_results(results)
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")

    # ---- 2. 构建 claims ----
    claims = _extract_claims_from_trace(events)

    # ---- 3. 构建 evidences ----
    # 建立 query → claimOrder 映射
    query_to_claim_order: dict[str, int] = {}
    for e in events:
        if e["type"] == "step" and e["node"] == "query_generator":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaim_with_questions") or []:
                sc_text = item.get("subclaim", "").strip()
                # 找到这个 subclaim 对应的 claimOrder
                co = None
                for c in claims:
                    if c.claimText == sc_text:
                        co = c.claimOrder
                        break
                if co is None:
                    continue
                for q in item.get("questions") or []:
                    query_to_claim_order[q] = co
            break

    default_relation = _infer_relation_type(label, len([e for e in events if e["type"] == "search"]))
    support_count = 0
    attack_count = 0

    evidence_items: list[F3EvidenceItem] = []
    for e in events:
        if e["type"] == "search":
            query = e.get("query", "")
            co = query_to_claim_order.get(query, 1)
            relation = default_relation
            if relation == "support":
                support_count += 1
            elif relation == "attack":
                attack_count += 1

            evidence_items.append(F3EvidenceItem(
                claimOrder=co,
                evidenceTitle=e.get("source_title", ""),
                evidenceContent=e.get("evidence_snippet", ""),
                evidenceUrl=e.get("chosen_url", ""),
                sourceName=e.get("source_name", ""),
                evidenceType="web",
                relationType=relation,
                credibilityScore=None,
                publishTime=None,
            ))

    # ---- 4. 构建 result ----
    is_true = label.lower() == "supported"
    if is_true:
        conclusion = "声明真实：多个权威来源相互印证。"
    elif label.lower() == "not_supported":
        conclusion = "声明虚假：与多方权威信息不符。"
    else:
        conclusion = "证据不足以判定声明真伪。"

    credibility = _build_credibility_score(len(evidence_items), label)

    # 将 verdict 的 label 映射到更丰富的标签体系
    if label.lower() == "supported":
        result_label = "supported"
    elif label.lower() == "not_supported":
        result_label = "not_supported"
    else:
        result_label = "insufficient_evidence"

    f3_result = F3Result(
        resultLabel=result_label,
        confidenceScore=credibility,
        conclusion=conclusion,
        analysisDetail=explanation or "经多智能体系统分析完成事实核查。",
        supportCount=support_count,
        attackCount=attack_count,
    )

    # ---- 5. 构建 report ----
    report_lines = []
    report_lines.append(f"# 事实核查报告\n")
    report_lines.append(f"**核查对象**：{req.claim.strip()}\n")
    report_lines.append(f"**核查结论**：{conclusion}\n")
    report_lines.append(f"**置信度**：{credibility if credibility else 'N/A'}/100\n")
    report_lines.append("---\n")
    report_lines.append("## 声明拆解\n")
    for c in claims:
        report_lines.append(f"- **声明 {c.claimOrder}**：{c.claimText}\n")
    report_lines.append("\n## 证据分析\n")
    for ev in evidence_items:
        report_lines.append(f"- **声明 {ev.claimOrder}** 相关证据：\n")
        report_lines.append(f"  - 标题：{ev.evidenceTitle}\n")
        report_lines.append(f"  - 来源：{ev.sourceName}\n")
        report_lines.append(f"  - 链接：{ev.evidenceUrl}\n")
        report_lines.append(f"  - 摘要：{ev.evidenceContent}\n")
        report_lines.append(f"  - 关系：{ev.relationType}\n")
    if not evidence_items:
        report_lines.append("（未检索到有效证据）\n")
    report_lines.append("\n## 最终结论\n")
    report_lines.append(f"{explanation}\n")

    f3_report = F3Report(
        reportTitle=f"事实核查报告 — {req.claim.strip()[:50]}",
        reportContent="".join(report_lines),
        reportFormat="markdown",
    )

    return FactCheckDetailDBData(
        claims=claims,
        evidences=evidence_items,
        result=f3_result,
        report=f3_report,
    )


@router.post(
    "/fact-check/detail/db",
    response_model=ApiResponse[FactCheckDetailDBData],
    summary="事实核查（数据库对齐版，含声明/证据/结果/报告结构化数据）",
)
def fact_check_detail_db(req: FactCheckRequest) -> ApiResponse[FactCheckDetailDBData]:
    data = _build_detail_db_response(get_fact_agent(), req)
    return ApiResponse[FactCheckDetailDBData](data=data)
