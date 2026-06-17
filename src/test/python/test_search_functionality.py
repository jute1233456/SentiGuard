#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
专门测试搜索功能 - 设定关键词，检查搜索结果
"""
import os
import sys
import json
from dotenv import load_dotenv

# 把项目根目录加入 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# 加载环境变量
load_dotenv()


def test_serper_api():
    """测试 Serper API 搜索"""
    print("=" * 80)
    print("测试 1: Serper API 直接搜索")
    print("=" * 80)

    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("❌ SERPER_API_KEY 未设置")
        return None

    print(f"✅ SERPER_API_KEY: 已设置")

    # 测试搜索查询
    test_queries = [
        "胶原蛋白 消化吸收",
        "维生素C 坏血病",
        "地球 形状",
    ]

    results = {}
    for query in test_queries:
        print(f"\n🔍 搜索: {query}")
        print("-" * 80)

        try:
            import requests

            server_address = "https://google.serper.dev/search"
            payload = json.dumps({"q": query, "num": 5})
            headers = {
                'X-API-KEY': api_key,
                'Content-Type': 'application/json'
            }

            response = requests.post(server_address, headers=headers, data=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()
                organic = data.get('organic', [])

                if organic:
                    print(f"✅ 找到 {len(organic)} 条结果")
                    results[query] = organic

                    for i, item in enumerate(organic[:3]):
                        title = item.get('title', '')
                        snippet = item.get('snippet', '')
                        link = item.get('link', '')
                        print(f"\n  结果 {i+1}:")
                        print(f"  标题: {title}")
                        print(f"  摘要: {snippet[:100]}..." if len(snippet) > 100 else f"  摘要: {snippet}")
                        print(f"  链接: {link}")
                else:
                    print("❌ 没有找到结果")
            else:
                print(f"❌ API 调用失败: {response.status_code}")
                print(f"   {response.text}")

        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            import traceback
            traceback.print_exc()

    return results


def test_search_engine_retriever():
    """测试 SearchEngineRetriever 类"""
    print("\n" + "=" * 80)
    print("测试 2: SearchEngineRetriever 类")
    print("=" * 80)

    try:
        from src.main.python.tools.retrieve import SearchEngineRetriever

        print("✅ 导入成功")

        # 创建检索器
        retriever = SearchEngineRetriever(dataset="fever", headless=True)
        print("✅ 初始化成功")

        # 测试搜索
        test_queries = [
            "胶原蛋白 消化",
            "维生素C 坏血病",
        ]

        for query in test_queries:
            print(f"\n🔍 搜索: {query}")
            print("-" * 80)

            try:
                result = retriever._retrieve_single(query)
                if result:
                    print(f"✅ 找到结果:")
                    print(f"   {result[:200]}..." if len(result) > 200 else f"   {result}")
                else:
                    print("❌ 没有找到结果")
            except Exception as e:
                print(f"❌ 搜索失败: {e}")

        # 清理
        if hasattr(retriever, 'driver'):
            retriever.driver.quit()

        return True

    except Exception as e:
        print(f"❌ SearchEngineRetriever 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_search_retrieve_news_tool():
    """测试 search_retrieve_news 工具"""
    print("\n" + "=" * 80)
    print("测试 3: search_retrieve_news 工具")
    print("=" * 80)

    try:
        from src.main.python.tools.retrieve import search_retrieve_news

        print("✅ 工具导入成功")

        # 测试查询
        test_queries = [
            "胶原蛋白 人体吸收",
            "维生素C 预防坏血病",
        ]

        for query in test_queries:
            print(f"\n🔍 工具搜索: {query}")
            print("-" * 80)

            try:
                result = search_retrieve_news.invoke({
                    "query": query,
                    "dataset": "fever"
                })

                if result:
                    print(f"✅ 工具返回结果:")
                    print(f"   {result[:300]}..." if len(result) > 300 else f"   {result}")
                else:
                    print("❌ 没有结果")

            except Exception as e:
                print(f"❌ 工具调用失败: {e}")
                import traceback
                traceback.print_exc()

        return True

    except Exception as e:
        print(f"❌ 工具测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_keywords_in_results(results, keywords):
    """检查搜索结果中是否包含指定关键词"""
    print("\n" + "=" * 80)
    print("关键词检查")
    print("=" * 80)

    for query, items in results.items():
        print(f"\n查询: {query}")
        print("-" * 80)

        all_text = ""
        for item in items:
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            all_text += title + " " + snippet + " "

        for keyword in keywords:
            found = keyword.lower() in all_text.lower()
            status = "✅" if found else "❌"
            print(f"  {status} 关键词 '{keyword}': {'找到' if found else '未找到'}")


def analyze_search_results(results):
    """分析搜索结果"""
    print("\n" + "=" * 80)
    print("搜索结果分析")
    print("=" * 80)

    for query, items in results.items():
        print(f"\n📊 查询: {query}")
        print(f"   结果数量: {len(items)}")

        domains = set()
        for item in items:
            link = item.get('link', '')
            if link:
                from urllib.parse import urlparse
                domain = urlparse(link).netloc
                domains.add(domain)

        print(f"   涉及域名: {len(domains)} 个")
        print(f"   域名列表: {', '.join(list(domains)[:5])}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("=" * 80)
    print("       FactAgent 搜索功能完整测试")
    print("=" * 80)
    print("=" * 80)

    # 测试 1: Serper API
    serper_results = test_serper_api()

    # 如果有结果，检查关键词
    if serper_results:
        check_keywords_in_results(serper_results, [
            "胶原蛋白", "氨基酸", "消化",
            "维生素C", "坏血病",
        ])
        analyze_search_results(serper_results)

    # 测试 2: SearchEngineRetriever
    test_search_engine_retriever()

    # 测试 3: search_retrieve_news 工具
    test_search_retrieve_news_tool()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    print("\n💡 提示:")
    print("  - 如果 Serper API 返回 'All API keys exhausted'，说明 API Key 配额用完了")
    print("  - 可以申请新的 Serper API Key 或检查使用量")
    print("  - Gemini 仍可提供一些基于训练数据的回答")
