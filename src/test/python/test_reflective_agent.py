"""
本地测试：运行 ReflectiveFactAgent（带反思循环的版本）→ 生成 HTML 报告 → 保存到文件

用法：
    python src/test/python/test_reflective_agent.py
    python src/test/python/test_reflective_agent.py --claim "你的声明"
    python src/test/python/test_reflective_agent.py --claim "你的声明" --output my_report.html
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from dotenv import load_dotenv
load_dotenv()

from src.main.python.reflective_fact_agent import ReflectiveFactAgent
from src.main.python.api.routers.fact_check import (
    _extract_claims_from_trace,
    _extract_evidence_items_from_trace,
    parse_verdict_from_results,
)
from src.main.python.api.schemas import F3Result
from src.main.python.report import LLMReportGenerator, ReportGenerator
from src.main.python.report.models import ReportData as ReportModuleData


def run(claim: str, model: str = "doubao/doubao-seed-2-0-mini-260428", output: str = ""):
    print(f"声明: {claim}")
    print(f"模型: {model}")
    print()

    # 1. 运行带反思循环的事实核查
    print(">>> ReflectiveFactAgent 开始分析（含反思循环）...")
    agent = ReflectiveFactAgent(dataset="fever", model_name=model)
    result = agent.process_claim(claim.strip(), recursion_limit=300, verbose=False)
    print(">>> 分析完成\n")

    # 2. 解析结果
    verdict = result["final_verdict"]
    label = verdict.get("label", "insufficient_evidence")
    explanation = verdict.get("explanation", "")
    confidence_score = verdict.get("confidenceScore")

    print(f"判定: {label}")
    print(f"置信度: {confidence_score}")
    print(f"反思轮数: {result['reflection_rounds']}")
    print(f"证据总数: {len(result['all_evidences'])}")
    print()

    # 3. 从 trace 提取声明
    events = agent.trace.events
    claims = _extract_claims_from_trace(events, claim.strip())
    evidence_items = result["all_evidences"]

    support_count = sum(1 for e in evidence_items if getattr(e, "relationType", None) == "support")
    attack_count = sum(1 for e in evidence_items if getattr(e, "relationType", None) == "attack")
    print(f"声明拆解: {len(claims)} 条")
    print(f"证据: {len(evidence_items)} 条（支持 {support_count} / 反驳 {attack_count}）")
    print()

    # 4. 构建结果
    is_true = label.lower() == "supported"
    if is_true:
        conclusion = "声明真实：多个权威来源相互印证。"
    elif label.lower() == "not_supported":
        conclusion = "声明虚假：与多方权威信息不符。"
    else:
        conclusion = "证据不足以判定声明真伪。"

    result_label = "supported" if label.lower() == "supported" else ("not_supported" if label.lower() == "not_supported" else "insufficient_evidence")

    f3_result = F3Result(
        resultLabel=result_label,
        confidenceScore=confidence_score,
        conclusion=conclusion,
        analysisDetail=explanation or "经多智能体系统分析完成事实核查。",
        supportCount=support_count,
        attackCount=attack_count,
    )

    # 5. 构造 ReportData
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

    # 6. 生成 HTML 报告
    print(">>> 正在生成 LLM 叙事 HTML 报告...")
    try:
        report_result = LLMReportGenerator(report_data).generate(renderer_name="html")
    except Exception as e:
        print(f"LLM 模式失败: {e}")
        print(">>> 降级为数据驱动模式...")
        report_result = ReportGenerator(report_data).generate()

    # 7. 保存文件
    output_path = output or f"reflective_report_{agent.trace.run_id}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_result.content)

    print(f"\n✅ 报告已保存: {os.path.abspath(output_path)}")
    print(f"   格式: {report_result.format}")
    print(f"   大小: {len(report_result.content)} 字节")
    print(f"\n用浏览器打开该文件查看效果")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行带反思循环的事实核查并生成 HTML 报告")
    parser.add_argument("--claim", default="2024年巴黎奥运会是第33届夏季奥林匹克运动会。")
    parser.add_argument("--model", default="doubao/doubao-seed-2-0-mini-260428")
    parser.add_argument("--output", default="", help="输出文件路径")
    args = parser.parse_args()
    run(args.claim, args.model, args.output)
