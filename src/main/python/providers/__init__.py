"""外部服务提供方 — 统一的外部 API 接入层

providers/ 收纳所有调用外部 API 服务的适配器，按能力域分为四个子包：

    providers/llm/         LLM 提供商
    providers/search/      搜索引擎
    providers/trending/    热搜平台
    providers/data/        新闻语料数据源
"""
# LLM
from src.main.python.providers.llm import (
    BaseLLM,
    LLMProvider,
    get_llm_provider,
    create_chat_model,
    invoke_with_json,
)
# Search
from src.main.python.providers.search import (
    BaseSearchEngine,
    SearchResult,
    SearchQuery,
    SearchEngineRegistry,
    register_search_engine,
    get_search_engine,
    list_search_engines,
)
# Trending
from src.main.python.providers.trending import (
    BaseTrendingCollector,
    TrendingItem,
    TrendingRegistry,
    register_trending_collector,
    get_trending_collector,
    list_trending_collectors,
    BaiduCollector,
    GoogleTrendsCollector,
    ToutiaoCollector,
)
# Data
from src.main.python.providers.data import (
    BaseDataSource,
    DOC_COLUMNS,
    merge_sources,
    GDELTClient,
    RSSClient,
    THUCNewsLoader,
)

__all__ = [
    # LLM
    "BaseLLM", "LLMProvider", "get_llm_provider", "create_chat_model", "invoke_with_json",
    # Search
    "BaseSearchEngine", "SearchResult", "SearchQuery", "SearchEngineRegistry",
    "register_search_engine", "get_search_engine", "list_search_engines",
    # Trending
    "BaseTrendingCollector", "TrendingItem", "TrendingRegistry",
    "register_trending_collector", "get_trending_collector", "list_trending_collectors",
    "BaiduCollector", "GoogleTrendsCollector", "ToutiaoCollector",
    # Data
    "BaseDataSource", "DOC_COLUMNS", "merge_sources",
    "GDELTClient", "RSSClient", "THUCNewsLoader",
]
