"""FactAgent 表现测试脚本：
给一系列真实和虚假的claim，测试其事实核查能力！
"""
import json
import os
import re
import sys

# 把项目根目录加入 sys.path，使得 `src.main.python.xxx` 绝对导入可以正常工作
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from dotenv import load_dotenv

load_dotenv()

from src.main.python.main_agent import FactAgent


# 测试用例：生活中常见的误区和事实
TEST_CLAIMS = [
    # ---- 常见误区 / 谣言（预期 not_supported）----
    {
        "claim": "吃什么补什么，吃胶原蛋白可以补充人体胶原蛋白。",
        "expected": "not_supported",
        "category": "饮食误区",
        "note": "口服胶原蛋白会被消化分解为氨基酸，无法直接补充皮肤胶原",
    },

    # ---- 真实事实（预期 supported）----
    {
        "claim": "维生素C可以预防坏血病，这是人类航海史上的重大发现。",
        "expected": "supported",
        "category": "医学事实",
        "note": "1747年林德医生的柠檬实验证实了这一点",
    },
]


def print_step_details(step, step_num):
    """打印单个步骤的详细信息"""
    print(f"\n{'='*80}")
    print(f"步骤 {step_num}: {list(step.keys())[0]}")
    print(f"{'='*80}")

    for agent_name, agent_data in step.items():
        if agent_name == "__end__":
            continue

        if "messages" in agent_data and len(agent_data["messages"]) > 0:
            for msg in agent_data["messages"]:
                msg_content = msg.content if hasattr(msg, 'content') else str(msg)
                msg_sender = msg.name if hasattr(msg, 'name') else agent_name

                print(f"\n【{msg_sender}】输出:")
                print("-" * 80)

                # 尝试解析 JSON 来更好地显示
                try:
                    parsed = json.loads(msg_content)
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))
                except json.JSONDecodeError:
                    # 尝试提取代码块中的 JSON
                    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", msg_content)
                    if match:
                        try:
                            parsed = json.loads(match.group(1))
                            print(json.dumps(parsed, ensure_ascii=False, indent=2))
                        except json.JSONDecodeError:
                            print(msg_content[:500] + ("..." if len(msg_content) > 500 else ""))
                    else:
                        print(msg_content[:500] + ("..." if len(msg_content) > 500 else ""))


def print_search_details(results):
    """从结果中提取并打印搜索相关的信息"""
    print(f"\n{'='*80}")
    print("🔍 搜索信息提取")
    print(f"{'='*80}")

    found_searches = False

    for i, step in enumerate(results):
        for agent_name, agent_data in step.items():
            if "messages" in agent_data:
                for msg in agent_data["messages"]:
                    msg_content = msg.content if hasattr(msg, 'content') else str(msg)

                    # 检查是否有搜索相关的内容
                    if "evidence_seeker" in str(type(msg)) or "search" in msg_content.lower():
                        found_searches = True
                        print(f"\n步骤 {i+1} - 证据搜索:")
                        print("-" * 80)

                        # 提取搜索查询
                        if "query" in msg_content.lower():
                            # 尝试找到搜索查询
                            lines = msg_content.split('\n')
                            for line in lines:
                                if "query" in line.lower() or "question" in line.lower():
                                    print(f"  📝 {line.strip()}")

                        # 检查是否有提取到的证据
                        if "evidence" in msg_content.lower() or "article" in msg_content.lower():
                            print(f"  📄 找到证据内容")

    if not found_searches:
        print("  本次未检测到显式的网络搜索步骤")


def parse_verdict_from_results(results):
    """从 FactAgent 返回的 step list 里提取最终的 label 和 explanation"""
    final_verdict = {"label": None, "explanation": None}

    # 倒序查找 verdict_predictor 的输出
    for step in reversed(results):
        if isinstance(step, dict) and "verdict_predictor" in step:
            vp_data = step["verdict_predictor"]
            if "messages" in vp_data and len(vp_data["messages"]) > 0:
                msg_content = vp_data["messages"][0].content if hasattr(vp_data["messages"][0], 'content') else str(vp_data["messages"][0])
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


def run_single_test(agent, test_case, show_details=True):
    """运行单个测试用例"""
    claim = test_case["claim"]
    category = test_case["category"]
    expected = test_case["expected"]

    print(f"\n{'='*80}")
    print(f"{'='*80}")
    print(f"📋 测试用例: [{category}]")
    print(f"{'='*80}")
    print(f"待验证: {claim}")
    if test_case.get("note"):
        print(f"参考:  {test_case['note']}")
    print(f"预期:   {expected}")
    print(f"{'='*80}\n")

    verdict = None
    success = False
    results = None

    try:
        print(">>> FactAgent 开始分析...")
        print(">>> 下面是完整的推理过程:\n")

        results = agent.process_claim(claim, recursion_limit=300, verbose=False)

        print(f"\n{'='*80}")
        print("📊 推理步骤概览")
        print(f"{'='*80}")
        for i, step in enumerate(results):
            step_key = list(step.keys())[0]
            print(f"  步骤 {i+1}: {step_key}")

        if show_details:
            # 打印每个步骤的详细信息
            for i, step in enumerate(results):
                print_step_details(step, i + 1)

            # 提取并打印搜索信息
            print_search_details(results)

        print(">>> 分析完成!\n")

        # 提取 verdict
        verdict = parse_verdict_from_results(results)

        # 判断结果
        success = verdict.get("label") == expected

        print(f"\n{'='*80}")
        print("🎯 最终结论")
        print(f"{'='*80}")
        print(f"  预期: {expected}")
        print(f"  实际: {verdict.get('label', 'None')}")
        print(f"  状态: {'✅ PASS' if success else '❌ FAIL'}")
        print(f"\n  判断依据:")
        expl = verdict.get('explanation', '无')
        if len(expl) > 800:
            expl = expl[:800] + "..."
        print(f"  {expl}")

    except Exception as e:
        print(f"\n❌ [错误] {e}")
        import traceback
        traceback.print_exc()

    return {
        **test_case,
        "actual_label": verdict.get("label") if verdict else None,
        "explanation": verdict.get("explanation") if verdict else None,
        "success": success,
        "full_results": results,
    }


def run_all_tests(model_name="doubao/doubao-seed-2-0-mini-260428", show_details=True):
    """运行所有测试用例"""
    print(f"\n{'='*80}")
    print(f"{'='*80}")
    print(f"       FactAgent 事实核查完整测试")
    print(f"{'='*80}")
    print(f"{'='*80}")
    print(f"\n使用模型: {model_name}")
    print(f"测试用例数: {len(TEST_CLAIMS)}")
    print(f"显示详情: {'是' if show_details else '否'}")
    print(f"\n{'='*80}\n")

    # 初始化 Agent
    print(">>> 初始化 FactAgent...")
    agent = FactAgent(dataset="fever", model_name=model_name)
    print(">>> FactAgent 初始化完成!\n")

    # 执行所有测试
    all_results = []
    for i, test_case in enumerate(TEST_CLAIMS):
        print(f"\n{'='*80}")
        print(f"进度: [{i+1}/{len(TEST_CLAIMS)}]")
        res = run_single_test(agent, test_case, show_details=show_details)
        all_results.append(res)

        # 询问是否继续
        if i < len(TEST_CLAIMS) - 1:
            try:
                input("\n按 Enter 继续下一个测试...")
            except KeyboardInterrupt:
                print("\n\n用户中断测试")
                break

    # 打印汇总
    total = len(all_results)
    correct = sum(1 for r in all_results if r["success"])
    accuracy = correct / total * 100 if total > 0 else 0

    print(f"\n\n{'='*80}")
    print(f"{'='*80}")
    print(f"       测试汇总")
    print(f"{'='*80}")
    print(f"{'='*80}")
    print(f"  总测试数: {total}")
    print(f"  正确数:   {correct}")
    print(f"  错误数:   {total - correct}")
    print(f"  准确率:   {accuracy:.1f}%")
    print(f"{'='*80}")

    # 分类统计
    category_stats = {}
    for res in all_results:
        cat = res["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "correct": 0}
        category_stats[cat]["total"] += 1
        if res["success"]:
            category_stats[cat]["correct"] += 1

    if len(category_stats) > 1:
        print(f"\n分类统计:")
        for cat, stats in category_stats.items():
            acc = stats["correct"] / stats["total"] * 100
            print(f"  {cat}: {stats['correct']}/{stats['total']} ({acc:.1f}%)")

    # 详细表格
    print(f"\n详细结果:")
    print(f"\n  {'#':<3} {'类别':<12} {'预期':<14} {'实际':<14} {'状态':<6}")
    print(f"  {'-'*65}")
    for i, r in enumerate(all_results):
        status = "✅" if r["success"] else "❌"
        act = r["actual_label"] or "N/A"
        print(f"  {i+1:<3} {r['category']:<12} {r['expected']:<14} {act:<14} {status:<6}")

    # 保存详细结果
    output_file = os.path.join(os.path.dirname(__file__), "../../../test_results.json")
    # 移除 full_results 来节省空间
    saved_results = [{k: v for k, v in r.items() if k != "full_results"} for r in all_results]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(saved_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_file}")

    return all_results


def run_single_claim(claim, model_name="doubao/doubao-seed-2-0-mini-260428"):
    """只运行单个 claim 的测试"""
    print(f"\n{'='*80}")
    print(f"       FactAgent 单条事实核查")
    print(f"{'='*80}")
    print(f"\n待验证: {claim}")
    print(f"\n{'='*80}\n")

    # 初始化 Agent
    print(">>> 初始化 FactAgent...")
    agent = FactAgent(dataset="fever", model_name=model_name)
    print(">>> FactAgent 初始化完成!\n")

    # 运行测试
    results = agent.process_claim(claim, recursion_limit=300, verbose=False)

    # 打印所有步骤
    print(f"\n{'='*80}")
    print("📊 完整推理过程")
    print(f"{'='*80}")

    for i, step in enumerate(results):
        print_step_details(step, i + 1)

    # 打印搜索信息
    print_search_details(results)

    # 获取最终结论
    verdict = parse_verdict_from_results(results)

    print(f"\n{'='*80}")
    print("🎯 最终结论")
    print(f"{'='*80}")
    print(f"  判断: {verdict.get('label', 'None')}")
    print(f"\n  解释:")
    expl = verdict.get('explanation', '无')
    print(f"  {expl}")

    return results


if __name__ == "__main__":
    # 检查命令行参数
    import argparse

    parser = argparse.ArgumentParser(description="FactAgent 事实核查测试")
    parser.add_argument("--claim", type=str, help="只测试单个声明")
    parser.add_argument("--model", type=str, default="doubao/doubao-seed-2-0-mini-260428",
                        help="使用的模型名称")
    parser.add_argument("--no-details", action="store_true", help="不显示详细推理过程")

    args = parser.parse_args()

    if args.claim:
        # 单条测试模式
        run_single_claim(args.claim, model_name=args.model)
    else:
        # 完整测试模式
        run_all_tests(model_name=args.model, show_details=not args.no_details)
