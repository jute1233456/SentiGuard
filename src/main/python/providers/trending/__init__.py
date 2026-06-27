"""热搜平台适配层

支持的热搜来源：
    - 百度热搜（BaiduCollector）
    - Google Trends（GoogleTrendsCollector）
    - 头条热榜（ToutiaoCollector）

新增热搜平台：
    1. 继承 BaseTrendingCollector，实现 fetch(limit) → List[TrendingItem]
    2. 文件末尾调用 register_trending_collector() 自注册
    3. 在下方添加 `from . import new_module  # noqa: F401` 触发注册
"""

# 基类和注册表
from src.main.python.providers.trending.base import (
    BaseTrendingCollector,
    TrendingItem,
    TrendingRegistry,
    register_trending_collector,
    get_trending_collector,
    list_trending_collectors,
)

# 导入各采集器模块以触发自注册，同时导出类名
from src.main.python.providers.trending.baidu import BaiduCollector              # noqa: F401
from src.main.python.providers.trending.google_trends import GoogleTrendsCollector  # noqa: F401
from src.main.python.providers.trending.toutiao import ToutiaoCollector           # noqa: F401

__all__ = [
    # 基类和注册表
    "BaseTrendingCollector", "TrendingItem", "TrendingRegistry",
    "register_trending_collector", "get_trending_collector", "list_trending_collectors",
    # 采集器
    "BaiduCollector", "GoogleTrendsCollector", "ToutiaoCollector",
]
