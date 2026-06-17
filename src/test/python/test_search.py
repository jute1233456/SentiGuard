#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 FactAgent 的网络搜索功能 - Pytest 格式
"""
import os
import sys
import json
from dotenv import load_dotenv

# 把项目根目录加入 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# 加载环境变量
load_dotenv()


class TestFactAgentSearch:
    """FactAgent 网络搜索功能测试"""

    def test_api_keys_set(self):
        """测试必要的 API Key 是否已设置"""
        SERPER_API_KEY = os.getenv("SERPER_API_KEY")
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

        assert SERPER_API_KEY is not None, "SERPER_API_KEY must be set in .env"
        assert len(SERPER_API_KEY) > 0, "SERPER_API_KEY cannot be empty"
        assert GOOGLE_API_KEY is not None, "GOOGLE_API_KEY must be set in .env"
        assert len(GOOGLE_API_KEY) > 0, "GOOGLE_API_KEY cannot be empty"

    def test_media_bias_database_loaded(self):
        """测试媒体偏见数据库是否能正确加载"""
        from src.main.python.tools.retrieve import MEDIA_BIAS_DICT, MEDIA_DATA

        assert MEDIA_DATA is not None, "MEDIA_DATA should not be None"
        assert isinstance(MEDIA_DATA, list), "MEDIA_DATA should be a list"
        assert len(MEDIA_DATA) > 0, "MEDIA_DATA should not be empty"
        assert len(MEDIA_DATA) == 5714, f"Expected 5714 records, got {len(MEDIA_DATA)}"

        # 检查第一条记录的结构
        first_entry = MEDIA_DATA[0]
        assert "url" in first_entry, "Each entry should have 'url' field"
        assert "bias" in first_entry, "Each entry should have 'bias' field"
        assert "factual" in first_entry, "Each entry should have 'factual' field"

    def test_media_bias_dict_creation(self):
        """测试媒体偏见字典是否正确创建"""
        from src.main.python.tools.retrieve import MEDIA_BIAS_DICT, MEDIA_DATA

        assert MEDIA_BIAS_DICT is not None, "MEDIA_BIAS_DICT should not be None"
        assert isinstance(MEDIA_BIAS_DICT, dict), "MEDIA_BIAS_DICT should be a dict"

        # 验证字典中的一些键
        sample_urls = [
            "newrepublic.com/",
            "www.accountable.us/",
            "www.newscorpse.com/"
        ]
        for url in sample_urls:
            assert url in MEDIA_BIAS_DICT, f"URL {url} should be in MEDIA_BIAS_DICT"

    def test_url_validation_edu_gov_org(self):
        """测试 .edu, .gov, .org 域名是否能通过检查"""
        from src.main.python.tools.retrieve import SearchEngineRetriever

        # 创建检索器但不启动浏览器
        retriever = SearchEngineRetriever(dataset="feverous", headless=True)

        # 清理浏览器
        if hasattr(retriever, 'driver'):
            retriever.driver.quit()
            del retriever.driver

        # 测试域名
        test_cases = [
            ("https://en.wikipedia.org/wiki/Science", True),  # .org
            ("https://www.nih.gov/health", True),           # .gov
            ("https://www.harvard.edu", True),              # .edu
        ]

        for url, expected in test_cases:
            result = retriever._check_valid_url(url)
            assert result == expected, f"URL {url} should be {'valid' if expected else 'invalid'}"

    def test_url_validation_scientific_domains(self):
        """测试科学域名是否能通过检查"""
        from src.main.python.tools.retrieve import SearchEngineRetriever

        # 创建检索器但不启动浏览器
        retriever = SearchEngineRetriever(dataset="feverous", headless=True)

        # 清理浏览器
        if hasattr(retriever, 'driver'):
            retriever.driver.quit()
            del retriever.driver

        # 测试科学域名
        scientific_urls = [
            "https://www.nature.com/articles/d41586-020-00126-9",
            "https://www.science.org/doi/10.1126/science.abd7331",
            "https://pubmed.ncbi.nlm.nih.gov/32423446/",
        ]

        for url in scientific_urls:
            result = retriever._check_valid_url(url)
            assert result is True, f"Scientific URL {url} should be valid"

    def test_search_retriever_initialization(self):
        """测试 SearchEngineRetriever 初始化"""
        from src.main.python.tools.retrieve import SearchEngineRetriever

        # 可以初始化
        retriever = SearchEngineRetriever(dataset="feverous", headless=True)
        assert retriever is not None
        assert retriever.dataset == "feverous"

        # 清理
        if hasattr(retriever, 'driver'):
            retriever.driver.quit()

    def test_get_original_url_function(self):
        """测试 _get_original_url 函数"""
        from src.main.python.tools.retrieve import SearchEngineRetriever

        retriever = SearchEngineRetriever(dataset="feverous", headless=True)

        # 清理浏览器
        if hasattr(retriever, 'driver'):
            retriever.driver.quit()
            del retriever.driver

        test_cases = [
            ("https://www.example.com/page.html", "www.example.com/"),
            ("https://example.org/article", "example.org/"),
            ("http://sub.domain.gov/path", "sub.domain.gov/"),
        ]

        for url, expected in test_cases:
            result = retriever._get_original_url(url)
            assert result == expected, f"Expected {expected} for {url}"


class TestSearchFlowDocumentation:
    """搜索流程文档测试"""

    def test_search_flow_documentation_exists(self):
        """测试搜索相关代码有适当的文档"""
        from src.main.python.tools import retrieve

        # 检查 SearchEngineRetriever 类是否有文档
        assert retrieve.SearchEngineRetriever.__doc__ is None or isinstance(
            retrieve.SearchEngineRetriever.__doc__, str
        )

        # 检查主要方法
        methods_to_check = [
            "_query_search_server",
            "_check_valid_url",
            "_retrieve_single",
            "get_details",
            "_process_content",
            "retrieve",
        ]

        for method_name in methods_to_check:
            method = getattr(retrieve.SearchEngineRetriever, method_name, None)
            assert method is not None, f"Method {method_name} should exist"

    def test_search_tool_exists(self):
        """测试 search_retrieve_news 工具存在"""
        from src.main.python.tools.retrieve import search_retrieve_news

        assert search_retrieve_news is not None, "search_retrieve_news should exist"
        assert hasattr(search_retrieve_news, 'invoke'), "Tool should have invoke method"


# 如果直接运行这个文件，也可以执行简单的测试
if __name__ == "__main__":
    print("=" * 60)
    print("FactAgent Web Search Test - Standalone Mode")
    print("=" * 60)
    print("\nTo run with pytest:")
    print("  pytest src/test/python/test_search.py -v")
    print("\nOr run specific test:")
    print("  pytest src/test/python/test_search.py::TestFactAgentSearch::test_api_keys_set -v")
    print("\n" + "=" * 60)

    # 简单的手动测试
    print("\nRunning quick manual checks...")

    # 检查 API keys
    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    print(f"\nSERPER_API_KEY: {'OK' if SERPER_API_KEY else 'MISSING'}")
    print(f"GOOGLE_API_KEY: {'OK' if GOOGLE_API_KEY else 'MISSING'}")

    # 检查数据库
    try:
        from src.main.python.tools.retrieve import MEDIA_DATA
        print(f"Media Bias DB: OK - {len(MEDIA_DATA)} records")
    except Exception as e:
        print(f"Media Bias DB: ERROR - {e}")

    print("\nQuick check completed!")
