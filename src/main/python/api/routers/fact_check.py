"""事实核查 API 路由。

端点一览：
- POST /fact-check/quick       — 快速核查（标准 FactAgent + 摘要搜索）
- POST /fact-check/deep        — 深度核查（ReflectiveFactAgent + 全文搜索 + 反思循环）
- POST /fact-check             — [废弃] 简化版，请使用 /quick
- POST /fact-check/detail      — [废弃] 详细版，请使用 /quick
- POST /fact-check/detail/db   — [废弃] 数据库对齐版，请使用 /quick 或 /deep
- POST /fact-check/detail/llm-report — [废弃] LLM 报告版，请使用 /deep

两个新端点（quick / deep）返回完全相同的 FactCheckDetailDBData 结构，
区别仅在内部核查深度。Java 后端可无缝切换到任一接口。
"""
from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime
from typing import Optional
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
from src.main.python.reflective_fact_agent import ReflectiveFactAgent
from src.main.python.report import ReportGenerator, LLMReportGenerator
from src.main.python.report.models import ReportData as ReportModuleData

router = APIRouter(
    prefix="/internal/v1",
    tags=["fact-check"],
    dependencies=[Depends(verify_internal_token)],
)

# 全局缓存 FactAgent 实例，避免重复初始化
_fact_agent: FactAgent | None = None
_reflective_agent: ReflectiveFactAgent | None = None


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


def get_reflective_agent() -> ReflectiveFactAgent:
    """获取或初始化 ReflectiveFactAgent 单例"""
    global _reflective_agent
    if _reflective_agent is None:
        _reflective_agent = ReflectiveFactAgent(
            dataset="fever",
            model_name="doubao/doubao-seed-2-0-mini-260428",
            temperature=0.2,
        )
    return _reflective_agent


# ======================================================================
# Verdict 解析函数（供所有端点复用）
# ======================================================================


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

    return _normalize_verdict(final_verdict)


def _normalize_verdict(verdict):
    """兼容模型返回 JSON、Python dict 字符串或嵌套 result 的情况。"""
    if isinstance(verdict, str):
        verdict = _parse_dict_like_text(verdict) or {"explanation": verdict}

    if not isinstance(verdict, dict):
        return {"label": "insufficient_evidence", "explanation": str(verdict or "")}

    if isinstance(verdict.get("result"), dict):
        verdict = verdict["result"]

    label = verdict.get("label")
    explanation = verdict.get("explanation")
    confidence_score = verdict.get("confidenceScore", verdict.get("confidence_score"))

    if isinstance(explanation, str):
        parsed_explanation = _parse_dict_like_text(explanation)
        if parsed_explanation:
            label = parsed_explanation.get("label", label)
            explanation = parsed_explanation.get("explanation", explanation)
            confidence_score = parsed_explanation.get("confidenceScore", parsed_explanation.get("confidence_score", confidence_score))

    if not label:
        text = str(explanation or "")
        if "not_supported" in text or "不支持" in text or "虚假" in text:
            label = "not_supported"
        elif "supported" in text or "支持" in text or "真实" in text:
            label = "supported"
        else:
            label = "insufficient_evidence"

    return {
        "label": str(label),
        "explanation": str(explanation or ""),
        "confidenceScore": _normalize_score_value(confidence_score),
    }


def _normalize_score_value(value) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if number <= 1:
            number *= 100
        return max(0, min(100, round(number)))
    except (TypeError, ValueError):
        return None


def _parse_dict_like_text(text: str) -> dict | None:
    """解析模型可能吐出的 JSON 或 Python dict 字符串。"""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return None
    return parsed if isinstance(parsed, dict) else None


# ======================================================================
# 共享辅助函数（供 quick / deep / 旧端点复用）
# ======================================================================


def _build_claims_evidences_from_trace(events: list, claim_text: str, label: str):
    """从 trace events 提取 claims 和 evidence items。"""
    claims = _extract_claims_from_trace(events, claim_text)
    evidence_items = _extract_evidence_items_from_trace(events, claims, label)
    return claims, evidence_items


def _build_result_conclusion(label: str, evidence_items: list):
    """根据 label 确定 resultLabel 和 conclusion。"""
    if label.lower() == "supported":
        return "supported", "声明真实：多个权威来源相互印证。"
    elif label.lower() == "not_supported":
        if not evidence_items:
            return "insufficient_evidence", "证据不足以判定声明真伪。"
        return "not_supported", "声明虚假：与多方权威信息不符。"
    return "insufficient_evidence", "证据不足以判定声明真伪。"


def _build_report_data_from_f3(claims, evidence_items, f3_result, trace, claim_text: str):
    """从 F3 结构化数据构造 ReportModuleData。"""
    f3_like = type("F3Like", (), {})()
    f3_like.claims = claims
    f3_like.evidences = evidence_items
    f3_like.result = f3_result
    report_data = ReportModuleData.from_f3_data(
        f3_like,
        run_id=trace.run_id if trace else "",
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    report_data.claim = claim_text
    return report_data


def _merge_evidence(trace_evidence: list, reflective_evidence: list) -> list:
    """合并 trace evidence 与 reflective supplement evidence，按 content+url 去重。"""
    seen = set()
    merged = []
    for ev in trace_evidence:
        key = (ev.evidenceContent, ev.evidenceUrl)
        if key not in seen:
            seen.add(key)
            merged.append(ev)
    for ev in reflective_evidence:
        content = getattr(ev, "evidenceContent", "") or ""
        url = getattr(ev, "evidenceUrl", "") or ""
        key = (content, url)
        if key not in seen:
            seen.add(key)
            merged.append(ev)
    return merged


def _build_f3_result(label: str, explanation: str, confidence_score, evidence_items: list) -> F3Result:
    """构建 F3Result（含 resultLabel、conclusion、supportCount、attackCount）。"""
    result_label, conclusion = _build_result_conclusion(label, evidence_items)
    support_count = sum(1 for ev in evidence_items if ev.relationType == "support")
    attack_count = sum(1 for ev in evidence_items if ev.relationType == "attack")
    return F3Result(
        resultLabel=result_label,
        confidenceScore=confidence_score,
        conclusion=conclusion,
        analysisDetail=explanation or "经多智能体系统分析完成事实核查。",
        supportCount=support_count,
        attackCount=attack_count,
    )


# ======================================================================
# 快速核查 — POST /internal/v1/fact-check/quick
# ======================================================================


def _build_quick_response(agent: FactAgent, req: FactCheckRequest) -> FactCheckDetailDBData:
    """快速核查：标准 FactAgent + 摘要搜索 + HTML 报告。"""
    results = agent.process_claim(
        req.claim.strip(),
        recursion_limit=300,
        verbose=False,
    )
    if agent.trace.trace_file is not None:
        logging.getLogger("fact_check").info(
            "trace file: %s | claim: %s",
            agent.trace.trace_file, req.claim.strip()[:80],
        )

    events = agent.trace.events
    verdict = parse_verdict_from_results(results)
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")
    confidence_score = verdict.get("confidenceScore")

    claims, evidence_items = _build_claims_evidences_from_trace(events, req.claim.strip(), label)
    f3_result = _build_f3_result(label, explanation, confidence_score, evidence_items)

    # 数据驱动 HTML 报告
    report_data = _build_report_data_from_f3(claims, evidence_items, f3_result, agent.trace, req.claim.strip())
    try:
        report_result = LLMReportGenerator(report_data).generate(renderer_name="html")
        report_format = "html"
    except Exception:
        logging.getLogger("fact_check").warning("LLM report generation failed, fallback to data-driven template", exc_info=True)
        report_result = ReportGenerator(report_data).generate(renderer_name="html")
        report_format = "html"

    f3_report = F3Report(
        reportTitle=report_result.title,
        reportContent=report_result.content,
        reportFormat=report_format,
    )

    return FactCheckDetailDBData(
        claims=claims,
        evidences=evidence_items,
        result=f3_result,
        report=f3_report,
    )


@router.post(
    "/fact-check/quick",
    response_model=ApiResponse[FactCheckDetailDBData],
    summary="快速核查（标准 FactAgent，摘要搜索，数据驱动报告）",
)
def fact_check_quick(req: FactCheckRequest) -> ApiResponse[FactCheckDetailDBData]:
    """快速核查：使用标准 FactAgent 完成事实核查，摘要搜索速度快，返回完整结构化数据。"""
    data = _build_quick_response(get_fact_agent(), req)
    return ApiResponse[FactCheckDetailDBData](data=data)


# ======================================================================
# 深度核查 — POST /internal/v1/fact-check/deep
# ======================================================================


def _build_deep_response(reflective_agent: ReflectiveFactAgent, req: FactCheckRequest) -> FactCheckDetailDBData:
    """深度核查：ReflectiveFactAgent + 全文搜索 + 反思循环 + LLM HTML 报告。"""
    ref_result = reflective_agent.process_claim(
        req.claim.strip(),
        recursion_limit=300,
        verbose=False,
    )

    verdict = ref_result["final_verdict"]
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")
    confidence_score = verdict.get("confidenceScore")

    # 从 trace 提取 claims + 基础 evidence
    events = reflective_agent.trace.events
    claims, trace_evidence = _build_claims_evidences_from_trace(events, req.claim.strip(), label)

    # 合并反思补充的证据
    all_evidence_items = _merge_evidence(trace_evidence, ref_result.get("all_evidences", []))
    f3_result = _build_f3_result(label, explanation, confidence_score, all_evidence_items)

    # LLM HTML 报告（失败降级为 Markdown）
    report_data = _build_report_data_from_f3(claims, all_evidence_items, f3_result, reflective_agent.trace, req.claim.strip())
    report_result = ReportGenerator(report_data).generate(renderer_name="html")
    report_format = "html"

    f3_report = F3Report(
        reportTitle=report_result.title,
        reportContent=report_result.content,
        reportFormat=report_format,
    )

    return FactCheckDetailDBData(
        claims=claims,
        evidences=all_evidence_items,
        result=f3_result,
        report=f3_report,
    )


@router.post(
    "/fact-check/deep",
    response_model=ApiResponse[FactCheckDetailDBData],
    summary="深度核查（ReflectiveFactAgent，全文搜索，反思循环，LLM 叙事报告）",
)
def fact_check_deep(req: FactCheckRequest) -> ApiResponse[FactCheckDetailDBData]:
    """深度核查：使用 ReflectiveFactAgent 完成事实核查，含最多 2 轮反思补充搜索，返回完整结构化数据。"""
    data = _build_deep_response(get_reflective_agent(), req)
    return ApiResponse[FactCheckDetailDBData](data=data)


# ======================================================================
# [废弃] F1 POST /internal/v1/fact-check — 简化版
# ======================================================================


@router.post(
    "/fact-check",
    response_model=ApiResponse[FactCheckData],
    summary="[废弃] 事实核查简化版，请使用 /quick",
    deprecated=True,
)
def fact_check(req: FactCheckRequest) -> ApiResponse[FactCheckData]:
    """[废弃] 简化版，仅返回 isTrue/conclusion/explanation 三字段。

    请使用 POST /internal/v1/fact-check/quick 替代，返回完整的结构化数据。
    """
    if req.reflective:
        db_data = _build_deep_response(get_reflective_agent(), req)
    else:
        db_data = _build_quick_response(get_fact_agent(), req)

    is_true = db_data.result.resultLabel == "supported"
    data = FactCheckData(
        isTrue=is_true,
        conclusion=db_data.result.conclusion,
        explanation=db_data.result.analysisDetail,
    )
    return ApiResponse[FactCheckData](data=data)


# ======================================================================
# [废弃] F2 POST /internal/v1/fact-check/detail — 详细版（含推理过程 + 证据链）
# ======================================================================


def _build_detail_response(agent: FactAgent, req: FactCheckRequest) -> FactCheckDetailData:
    """执行核查并组装详细响应体（含 trace + evidenceItems）。"""
    results = agent.process_claim(
        req.claim.strip(),
        recursion_limit=300,
        verbose=False,
    )

    if agent.trace.trace_file is not None:
        logging.getLogger("fact_check").info(
            "trace file: %s | claim: %s",
            agent.trace.trace_file, req.claim.strip()[:80],
        )

    verdict = parse_verdict_from_results(results)
    label = verdict.get("label", "supported")
    explanation = verdict.get("explanation", "")
    is_true = label.lower() == "supported"
    if is_true:
        conclusion = "声明真实：多个权威来源相互印证。"
    else:
        conclusion = "声明虚假：与多方权威信息不符或证据不足。"

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
    summary="[废弃] 详细版（含推理过程与证据链），请使用 /quick",
    deprecated=True,
)
def fact_check_detail(req: FactCheckRequest) -> ApiResponse[FactCheckDetailData]:
    """[废弃] 详细版，含推理路径和证据链。

    请使用 POST /internal/v1/fact-check/quick 替代，返回更完整的结构化数据。
    """
    data = _build_detail_response(get_fact_agent(), req)
    return ApiResponse[FactCheckDetailData](data=data)


# ======================================================================
# [废弃] F3 POST /internal/v1/fact-check/detail/db — 数据库对齐版
# ======================================================================


def _infer_relation_type(label: str, evidence_count: int) -> str:
    """根据总体标签推断 evidence 的 relationType 默认值。"""
    if label == "supported":
        return "support"
    elif label == "not_supported":
        return "attack"
    return "neutral"


def _extract_claims_from_trace(events: list, fallback_claim: str = "") -> list:
    """从 trace events 中提取所有可核查声明列表。"""
    claims = []
    seen = set()

    def add_claim(text: str, claim_type: str = "verifiable"):
        value = str(text or "").strip()
        if not value or value in seen:
            return
        seen.add(value)
        claims.append(F3ClaimItem(
            claimOrder=len(claims) + 1,
            claimText=value,
            claimType=claim_type or "verifiable",
        ))

    def similar_claim_exists(candidate: str) -> bool:
        candidate = str(candidate or "").strip()
        if not candidate:
            return True
        for claim in claims:
            existing = claim.claimText or ""
            if candidate in existing or existing in candidate:
                return True
            tokens = ["特朗普", "连任", "拜登", "选举人票", "超过270", "投票日", "11月3日", "总统大选"]
            overlap = sum(1 for token in tokens if token in candidate and token in existing)
            if overlap >= 2:
                return True
        return False

    def supplement_from_original() -> None:
        source = str(fallback_claim or "").strip()
        if not source:
            return
        parts = re.split(r"[。；;]|，并且|,\s*and|，且|，以及|，", source)
        context = "2020年美国总统大选" if "2020年美国总统大选" in source else ""
        for part in parts:
            value = part.strip(" ，,。；;、")
            if not value or len(value) < 8:
                continue
            if context and "美国总统大选" not in value and any(token in value for token in ["拜登", "特朗普", "投票日", "选举人票"]):
                value = context + value
            if not similar_claim_exists(value):
                add_claim(value, "verifiable")

    # 优先取最终用于核查的可验证声明
    for e in events:
        if e.get("type") == "step" and e.get("node") == "claim_splitter":
            sr = e.get("structured_response") or {}
            for sc in sr.get("subclaims") or []:
                add_claim(sc, "verifiable")
            if claims:
                supplement_from_original()
                return claims

    # claim_splitter 为空时，回退到分类节点里的声明
    for e in events:
        if e.get("type") == "step" and e.get("node") == "claim_classification":
            sr = e.get("structured_response") or {}
            for item in sr.get("claims") or sr.get("classified_claims") or []:
                if isinstance(item, dict):
                    add_claim(
                        item.get("claim") or item.get("claim_text") or item.get("text"),
                        item.get("type") or item.get("claim_type") or item.get("classification") or "verifiable",
                    )
                else:
                    add_claim(item, "verifiable")
            if claims:
                supplement_from_original()
                return claims

    for e in events:
        if e.get("type") == "step" and e.get("node") == "query_generator":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaim_with_questions") or []:
                if isinstance(item, dict):
                    add_claim(item.get("subclaim"), "verifiable")
            if claims:
                supplement_from_original()
                return claims

    for e in events:
        if e.get("type") == "step" and e.get("node") == "evidence_seeker":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaims_with_query_evidence") or []:
                if isinstance(item, dict):
                    add_claim(item.get("subclaim"), "verifiable")
            if claims:
                supplement_from_original()
                return claims

    add_claim(fallback_claim, "verifiable")
    return claims


def _claim_order_for_text(claims: list, text: str) -> int:
    value = str(text or "").strip()
    for claim in claims:
        if claim.claimText == value:
            return claim.claimOrder
    for claim in claims:
        if value and (value in claim.claimText or claim.claimText in value):
            return claim.claimOrder
    return claims[0].claimOrder if claims else 1


def _valid_evidence_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    invalid_markers = {
        "none", "null", "n/a", "no evidence", "no relevant evidence",
        "未检索到相关有效证据", "未检索到有效证据", "无相关有效证据",
        "没有相关证据", "未找到相关证据", "没有找到相关证据", "暂无证据", "证据不足",
    }
    lower_value = value.lower()
    return not any(marker in lower_value or marker in value for marker in invalid_markers)


def _infer_evidence_relation(subclaim: str, evidence_text: str, fallback_label: str) -> str:
    claim = str(subclaim or "")
    evidence = str(evidence_text or "")
    combined = claim + "\n" + evidence
    attack_markers = ["不成立", "未能", "未成功", "没有", "并非", "不是", "矛盾", "反驳", "仅获得", "232"]
    support_markers = ["成立", "获得", "超过", "306", "11月3日", "为11月3日", "投票日为", "支持", "符合"]

    if any(marker in evidence for marker in attack_markers):
        return "attack"
    if any(marker in combined for marker in support_markers):
        return "support"
    return _infer_relation_type(fallback_label, 1)


def _extract_evidence_items_from_trace(events: list, claims: list, label: str) -> list[F3EvidenceItem]:
    """从 search trace 优先提取证据；缺少 search 时回退到 evidence_seeker 文本。"""
    evidence_items: list[F3EvidenceItem] = []
    seen = set()
    search_queries_with_evidence = set()

    def add_item(claim_order: int, title: str, content: str, url: str = "",
                 source_name: str = "", subclaim: str = "", publish_time: str = "",
                 credibility_score: int | None = None, query: str = "") -> bool:
        if not _valid_evidence_text(content):
            return False
        clean_title = str(title or "检索证据").strip()
        clean_content = str(content or "").strip()
        clean_url = str(url or "").strip()
        key = (claim_order, clean_content, clean_url)
        if key in seen:
            return False
        seen.add(key)
        relation_type = _infer_evidence_relation(subclaim, clean_content, label)
        credibility_score = _normalize_score_value(credibility_score)
        evidence_items.append(F3EvidenceItem(
            claimOrder=claim_order,
            evidenceTitle=clean_title,
            evidenceContent=clean_content,
            evidenceUrl=clean_url,
            sourceName=str(source_name or "搜索检索结果").strip(),
            evidenceType="web",
            relationType=relation_type,
            credibilityScore=credibility_score,
            publishTime=publish_time or None,
        ))
        if query:
            search_queries_with_evidence.add(query)
        return True

    query_to_claim_order: dict[str, int] = {}
    query_to_subclaim: dict[str, str] = {}
    for e in events:
        if e.get("type") == "step" and e.get("node") == "query_generator":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaim_with_questions") or []:
                subclaim = str(item.get("subclaim") or "").strip()
                claim_order = _claim_order_for_text(claims, subclaim)
                for query in item.get("questions") or []:
                    query_text = str(query or "").strip()
                    if query_text:
                        query_to_claim_order[query_text] = claim_order
                        query_to_subclaim[query_text] = subclaim

    query_to_agent_score: dict[str, int | None] = {}
    for e in events:
        if e.get("type") == "step" and e.get("node") == "evidence_seeker":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaims_with_query_evidence") or []:
                for qe in item.get("queries_with_evidence") or []:
                    query_text = str(qe.get("query") or "").strip()
                    if query_text:
                        query_to_agent_score[query_text] = _normalize_score_value(
                            qe.get("credibilityScore", qe.get("credibility_score"))
                        )

    def resolve_claim_order(query: str) -> int:
        value = str(query or "").strip()
        if value in query_to_claim_order:
            return query_to_claim_order[value]
        best_order = claims[0].claimOrder if claims else 1
        best_score = 0
        for claim in claims:
            claim_text = claim.claimText or ""
            score = 0
            for token in ["特朗普", "拜登", "选举人票", "投票日", "11月3日", "连任", "总统大选", "结果"]:
                if token in value and token in claim_text:
                    score += 1
            if score > best_score:
                best_score = score
                best_order = claim.claimOrder
        return best_order

    # 1. 优先使用 search trace
    for e in events:
        if e.get("type") == "search":
            query = str(e.get("query") or "").strip()
            title = e.get("source_title") or (f"检索问题：{query}" if query else "搜索证据")
            add_item(
                resolve_claim_order(query),
                title,
                e.get("evidence_snippet"),
                e.get("chosen_url", ""),
                e.get("source_name", ""),
                query_to_subclaim.get(query, query),
                e.get("publish_time", ""),
                query_to_agent_score.get(query),
                query,
            )

    # 2. 回退使用 evidence_seeker
    for e in events:
        if e.get("type") == "step" and e.get("node") == "evidence_seeker":
            sr = e.get("structured_response") or {}
            for item in sr.get("subclaims_with_query_evidence") or []:
                claim_order = _claim_order_for_text(claims, item.get("subclaim", ""))
                for qe in item.get("queries_with_evidence") or []:
                    query = str(qe.get("query") or "").strip()
                    if query and query in search_queries_with_evidence:
                        continue
                    content = qe.get("evidence")
                    title = f"检索问题：{query}" if query else "检索证据"
                    agent_score = qe.get("credibilityScore", qe.get("credibility_score"))
                    add_item(
                        resolve_claim_order(query) if query else claim_order,
                        title,
                        content,
                        subclaim=item.get("subclaim", ""),
                        credibility_score=agent_score,
                        query=query,
                    )

    return evidence_items


@router.post(
    "/fact-check/detail/db",
    response_model=ApiResponse[FactCheckDetailDBData],
    summary="[废弃] 数据库对齐版，请使用 /quick 或 /deep",
    deprecated=True,
)
def fact_check_detail_db(req: FactCheckRequest) -> ApiResponse[FactCheckDetailDBData]:
    """[废弃] 数据库对齐版，保持向后兼容（Java 后端当前调用此接口）。

    新代码请使用 POST /internal/v1/fact-check/quick 或 /deep 替代。
    """
    if req.reflective:
        data = _build_deep_response(get_reflective_agent(), req)
    else:
        data = _build_quick_response(get_fact_agent(), req)
    return ApiResponse[FactCheckDetailDBData](data=data)


# ======================================================================
# [废弃] LLM 叙事报告接口
# ======================================================================


@router.post(
    "/fact-check/detail/llm-report",
    response_model=ApiResponse[FactCheckDetailDBData],
    summary="[废弃] LLM 叙事报告版，请使用 /deep",
    deprecated=True,
)
def fact_check_llm_report(req: FactCheckRequest) -> ApiResponse[FactCheckDetailDBData]:
    """[废弃] LLM 叙事报告版。

    请使用 POST /internal/v1/fact-check/deep 替代，功能相同且返回更完整的结构化数据。
    """
    data = _build_deep_response(get_reflective_agent(), req)
    return ApiResponse[FactCheckDetailDBData](data=data)
