"""
本地测试：运行事实核查 → 生成 HTML 报告 → 保存到文件

用法：
    python src/test/python/test_report_html.py                           # 默认 quick 模式
    python src/test/python/test_report_html.py --mode deep               # 深度核查
    python src/test/python/test_report_html.py --mode quick --claim "声明"
    python src/test/python/test_report_html.py --mode deep --claim "声明" --output-dir result/
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from dotenv import load_dotenv
load_dotenv()

from src.main.python.main_agent import FactAgent
from src.main.python.reflective_fact_agent import ReflectiveFactAgent
from src.main.python.report import ReportGenerator, DeepLLMReportGenerator
from src.main.python.report.models import ReportData as ReportModuleData
from src.main.python.api.schemas import F3Result
from src.main.python.api.routers.fact_check import (
    _extract_claims_from_trace,
    _extract_evidence_items_from_trace,
    parse_verdict_from_results,
    _build_result_conclusion,
)


RESULTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../result/test_reports"))


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _save_report(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ 报告已保存: {os.path.abspath(path)} ({len(content)} 字节)")


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 已保存: {os.path.abspath(path)}")


def _print_summary(label: str, confidence: int, evidence_items: list):
    support = sum(1 for ev in evidence_items if ev.relationType == "support")
    attack = sum(1 for ev in evidence_items if ev.relationType == "attack")
    print(f"  判定: {label}")
    print(f"  置信度: {confidence}")
    print(f"  证据: {len(evidence_items)} 条（支持 {support} / 反驳 {attack}）")


def run_quick(claim: str, model: str, output_dir: str = ""):
    print(f"🔵 快速核查: {claim}")
    agent = FactAgent(dataset="fever", model_name=model)
    results = agent.process_claim(claim.strip(), recursion_limit=300, verbose=False)

    verdict = parse_verdict_from_results(results)
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")
    confidence_score = verdict.get("confidenceScore")

    events = agent.trace.events
    claims = _extract_claims_from_trace(events, claim.strip())
    evidence_items = _extract_evidence_items_from_trace(events, claims, label)
    result_label, conclusion = _build_result_conclusion(label, evidence_items)

    neutral_count = sum(1 for ev in evidence_items if ev.relationType == "neutral")
    f3_result = F3Result(
        resultLabel=result_label,
        confidenceScore=confidence_score,
        conclusion=conclusion,
        analysisDetail=explanation or "经多智能体系统分析完成事实核查。",
        supportCount=sum(1 for ev in evidence_items if ev.relationType == "support"),
        attackCount=sum(1 for ev in evidence_items if ev.relationType == "attack"),
        neutralCount=neutral_count,
    )

    f3_like = type("F3Like", (), {})()
    f3_like.claims = claims
    f3_like.evidences = evidence_items
    f3_like.result = f3_result
    report_data = ReportModuleData.from_f3_data(
        f3_like,
        run_id=agent.trace.run_id if agent.trace else "",
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    report_data.claim = claim.strip()

    print(">>> 生成 HTML 报告...")
    report_result = ReportGenerator(report_data).generate(renderer_name="html")

    _save_report(os.path.join(output_dir, "report.html") if output_dir else f"quick_report_{agent.trace.run_id}.html",
                 report_result.content)
    _print_summary(result_label, confidence_score, evidence_items)


def run_deep(claim: str, model: str, output_dir: str = "", reflections: int = 5):
    print(f"🔴 深度核查: {claim}")
    agent = ReflectiveFactAgent(dataset="fever", model_name=model)
    result = agent.process_claim(claim.strip(), recursion_limit=300, verbose=False)

    verdict = result["final_verdict"]
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")
    confidence_score = verdict.get("confidenceScore")

    events = agent.trace.events
    claims = _extract_claims_from_trace(events, claim.strip())
    trace_evidence = _extract_evidence_items_from_trace(events, claims, label)

    seen = {(ev.evidenceContent, ev.evidenceUrl) for ev in trace_evidence}
    for ev in result.get("all_evidences", []):
        key = (getattr(ev, "evidenceContent", "") or "", getattr(ev, "evidenceUrl", "") or "")
        if key not in seen:
            seen.add(key)
            trace_evidence.append(ev)

    evidence_items = trace_evidence
    result_label, conclusion = _build_result_conclusion(label, evidence_items)

    neutral_count = sum(1 for ev in evidence_items if ev.relationType == "neutral")
    f3_result = F3Result(
        resultLabel=result_label,
        confidenceScore=confidence_score,
        conclusion=conclusion,
        analysisDetail=explanation or "经多智能体系统分析完成事实核查。",
        supportCount=sum(1 for ev in evidence_items if ev.relationType == "support"),
        attackCount=sum(1 for ev in evidence_items if ev.relationType == "attack"),
        neutralCount=neutral_count,
    )

    f3_like = type("F3Like", (), {})()
    f3_like.claims = claims
    f3_like.evidences = evidence_items
    f3_like.result = f3_result
    report_data = ReportModuleData.from_f3_data(
        f3_like,
        run_id=agent.trace.run_id if agent.trace else "",
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    report_data.claim = claim.strip()

    print(">>> 生成深度 LLM 叙事报告（逐段生成，约 60-120s）...")
    try:
        generator = DeepLLMReportGenerator(report_data, reflection_count=reflections)
        report_result = generator.generate(renderer_name="html")

        conv_log = generator.get_conversation_log()
        log_path = os.path.join(output_dir, "llm_conversation_log.json")
        _save_json(log_path, {
            "claim": claim.strip(),
            "run_id": agent.trace.run_id if agent.trace else "",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_llm_calls": len(conv_log),
            "phases": [entry["phase"] for entry in conv_log],
            "conversations": conv_log,
        })

        # 保存声明拆解日志
        decomp_log = generator.get_decomposition_log()
        if decomp_log:
            decomp_path = os.path.join(output_dir, "decomposition_log.json")
            _save_json(decomp_path, {
                "claim": claim.strip(),
                "reflections": reflections,
                "rounds": decomp_log,
            })
    except Exception as e:
        print(f"  DeepLLMReportGenerator 失败: {e}")
        print(">>> 降级为数据驱动 HTML 报告...")
        report_result = ReportGenerator(report_data).generate(renderer_name="html")

    _save_report(os.path.join(output_dir, "report.html"), report_result.content)
    _print_summary(result_label, confidence_score, evidence_items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 HTML 事实核查报告")
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick",
                        help="quick=快速核查(默认), deep=深度核查")
    parser.add_argument("--claim", default="2024年巴黎奥运会是第33届夏季奥林匹克运动会。")
    parser.add_argument("--model", default="doubao/doubao-seed-2-0-mini-260428")
    parser.add_argument("--reflections", type=int, default=5, help="声明拆解反思次数（默认5，仅deep模式有效）")
    parser.add_argument("--output-dir", default="", help="输出目录（默认为 result/test_reports/）")
    args = parser.parse_args()

    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(RESULTS_DIR, f"{args.mode}_{timestamp}")

    _ensure_dir(out_dir)
    print(f"📁 输出目录: {out_dir}")

    if args.mode == "quick":
        run_quick(args.claim, args.model, out_dir)
    else:
        run_deep(args.claim, args.model, out_dir, reflections=args.reflections)
