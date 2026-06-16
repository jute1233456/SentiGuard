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
    {
        "claim": "笔记本电脑不可以边充电边玩，这样对电池不健康。",
        "expected": "not_supported",
        "category": "数码误区",
        "note": "现代笔记本都有电源管理芯片，边充边玩不会损伤电池",
    },
    {
        "claim": "每天要喝8杯水才健康。",
        "expected": "not_supported",
        "category": "健康误区",
        "note": "8杯水没有科学依据，饮水量因人而异",
    },
    {
        "claim": "人体左侧大脑负责逻辑，右侧大脑负责创意，左撇子右脑更发达。",
        "expected": "not_supported",
        "category": "科普谣言",
        "note": "左右脑分工理论已被神经科学证伪，大脑是整体协作的",
    },
    {
        "claim": "味精加热后会致癌。",
        "expected": "not_supported",
        "category": "食品安全谣言",
        "note": "味精（谷氨酸钠）在正常烹饪温度下不会产生致癌物",
    },

    # ---- 真实事实（预期 supported）----
    {
        "claim": "维生素C可以预防坏血病，这是人类航海史上的重大发现。",
        "expected": "supported",
        "category": "医学事实",
        "note": "1747年林德医生的柠檬实验证实了这一点",
    },
    {
        "claim": "北京大学的鹅腿阿姨卖的鹅腿是正规食品，没有食品安全问题。",
        "expected": "not_supported",
        "category": "社会热点",
        "note": "北大鹅腿阿姨是真实存在的校园网红摊主",
    },
    {
        "claim": "武汉大学杨景媛同学被肖同学猥亵属实。",
        "expected": "not_supported",
        "category": "社会事件",
        "note": "2024年武大校园性骚扰事件，警方已通报",
    },
    {
        "claim": "2024年巴黎奥运会是第33届夏季奥林匹克运动会。",
        "expected": "supported",
        "category": "体育事实",
        "note": "于2024年7月26日至8月11日在法国巴黎举行",
    },
    {
        "claim": "吸烟会导致肺癌风险显著增加，这是医学界公认的事实。",
        "expected": "supported",
        "category": "健康事实",
        "note": "大量流行病学研究证实吸烟与肺癌的强相关性",
    },
]


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


def run_single_test(agent, test_case):
    """运行单个测试用例"""
    claim = test_case["claim"]
    category = test_case["category"]
    expected = test_case["expected"]

    print(f"\n{'='*80}")
    print(f"[{category}]")
    print(f"待验证: {claim}")
    if test_case.get("note"):
        print(f"参考:  {test_case['note']}")
    print(f"{'='*80}")

    verdict = None
    success = False

    try:
        print(">>> FactAgent 开始分析...")
        results = agent.process_claim(claim, recursion_limit=300, verbose=False)
        print(">>> 分析完成!")

        # 提取 verdict
        verdict = parse_verdict_from_results(results)

        # 判断结果
        success = verdict.get("label") == expected

        print(f"\n[结果]")
        print(f"  预期: {expected}")
        print(f"  实际: {verdict.get('label', 'None')}")
        print(f"  状态: {'PASS' if success else 'FAIL'}")
        expl = verdict.get('explanation', '无')
        if len(expl) > 300:
            expl = expl[:300] + "..."
        print(f"  解释: {expl}")

    except Exception as e:
        print(f"\n[错误] {e}")

    return {
        **test_case,
        "actual_label": verdict.get("label") if verdict else None,
        "explanation": verdict.get("explanation") if verdict else None,
        "success": success,
    }


def run_all_tests(model_name="doubao/doubao-seed-2-0-mini-260428"):
    """运行所有测试用例"""
    print(f"\n{'='*80}")
    print(f"FactAgent 表现测试开始!")
    print(f"使用模型: {model_name}")
    print(f"测试用例数: {len(TEST_CLAIMS)}")
    print(f"{'='*80}\n")

    # 初始化 Agent
    agent = FactAgent(dataset="fever", model_name=model_name)

    # 执行所有测试
    all_results = []
    for i, test_case in enumerate(TEST_CLAIMS):
        print(f"\n[{i+1}/{len(TEST_CLAIMS)}]", end="")
        res = run_single_test(agent, test_case)
        all_results.append(res)

    # 打印汇总
    total = len(all_results)
    correct = sum(1 for r in all_results if r["success"])
    accuracy = correct / total * 100 if total > 0 else 0

    print(f"\n\n{'='*80}")
    print(f"测试汇总")
    print(f"{'='*80}")
    print(f"  总测试数: {total}")
    print(f"  正确数:   {correct}")
    print(f"  错误数:   {total - correct}")
    print(f"  准确率:   {accuracy:.1f}%")

    # 分类统计
    category_stats = {}
    for res in all_results:
        cat = res["category"]
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "correct": 0}
        category_stats[cat]["total"] += 1
        if res["success"]:
            category_stats[cat]["correct"] += 1

    print(f"\n分类统计:")
    for cat, stats in category_stats.items():
        acc = stats["correct"] / stats["total"] * 100
        print(f"  {cat}: {stats['correct']}/{stats['total']} ({acc:.1f}%)")

    # 详细表格
    print(f"\n详细结果:")
    print(f"  {'#':<3} {'类别':<10} {'预期':<14} {'实际':<14} {'状态':<6}")
    print(f"  {'-'*65}")
    for i, r in enumerate(all_results):
        status = "PASS" if r["success"] else "FAIL"
        act = r["actual_label"] or "N/A"
        print(f"  {i+1:<3} {r['category']:<10} {r['expected']:<14} {act:<14} {status:<6}")

    # 保存详细结果
    with open("../../../test_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: test_results.json")

    return all_results


if __name__ == "__main__":
    run_all_tests()
