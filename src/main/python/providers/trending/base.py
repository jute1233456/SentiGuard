"""热搜采集器基类 — 定义统一接口和注册表

参照 providers/search/base.py 的 SearchEngineRegistry 模式，
提供 BaseTrendingCollector 抽象基类 + TrendingRegistry 注册表。
所有热搜平台采集器需继承基类并通过 register_trending_collector() 自注册。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrendingItem:
    """统一的热搜条目数据类

    所有 Collector 的 fetch() 方法都返回此类型，确保多源数据格式统一。
    """
    rank: int
    title: str
    heat: float          # 热度分（0-100），由各采集器自行归一化
    url: str
    summary: str = ""
    source_name: str = ""  # 来源标识："baidu" / "toutiao" / "google_trends"
    raw_data: Dict = field(default_factory=dict)  # 原始数据，供调试和扩展

    def __repr__(self) -> str:
        return f"#{self.rank} [{self.source_name}] {self.title} (热度:{self.heat})"


class BaseTrendingCollector(ABC):
    """热搜采集器抽象基类

    所有热搜平台采集器需继承此类，实现 fetch(limit) 方法，
    返回统一的 List[TrendingItem]。

    新增平台步骤：
        1. 继承 BaseTrendingCollector，设置 SOURCE_NAME
        2. 实现 fetch(limit) → List[TrendingItem]
        3. 在文件末尾调用 register_trending_collector() 自注册
        4. 在 providers/trending/__init__.py 中 import 该模块触发注册
    """

    SOURCE_NAME: str = "unknown"

    @abstractmethod
    def fetch(self, limit: int) -> List[TrendingItem]:
        """拉取实时热搜榜单

        Args:
            limit: 返回热搜数量上限

        Returns:
            统一格式的 TrendingItem 列表
        """
        ...

    def get_source_name(self) -> str:
        """返回采集器标识名"""
        return self.SOURCE_NAME


class TrendingRegistry:
    """热搜采集器注册表

    管理所有已注册的热搜采集器，支持按名称获取实例。
    参照 providers/search/base.py 的 SearchEngineRegistry 模式。
    """

    def __init__(self):
        self._collectors: Dict[str, type] = {}

    def register(self, name: str, collector_class: type) -> None:
        """注册一个热搜采集器

        Args:
            name: 采集器标识名（如 "baidu", "toutiao"）
            collector_class: 采集器类（须继承 BaseTrendingCollector）

        Raises:
            ValueError: 采集器类未继承 BaseTrendingCollector
        """
        if not issubclass(collector_class, BaseTrendingCollector):
            raise ValueError(
                f"采集器 {collector_class.__name__} 必须继承 BaseTrendingCollector"
            )
        self._collectors[name] = collector_class

    def get(self, name: str, config: Optional[Dict] = None) -> Optional[BaseTrendingCollector]:
        """按名称获取采集器实例

        Args:
            name: 采集器标识名
            config: 可选的配置字典，传递给采集器构造函数

        Returns:
            采集器实例，未找到时返回 None
        """
        cls = self._collectors.get(name)
        if cls is None:
            return None
        if config is not None:
            return cls(**config)
        return cls()

    def list_available(self) -> List[str]:
        """列出所有已注册的采集器名称"""
        return list(self._collectors.keys())

    def create_all(self, config: Optional[Dict] = None) -> List[BaseTrendingCollector]:
        """创建所有已注册采集器的实例，返回列表"""
        collectors = []
        for name in self._collectors:
            collector = self.get(name, config)
            if collector:
                collectors.append(collector)
        return collectors


# ---- 全局单例 + 便捷函数 ----

_trending_registry = TrendingRegistry()


def register_trending_collector(name: str, collector_class: type) -> None:
    """注册热搜采集器（便捷函数）

    在各 Collector 模块末尾调用，实现自注册：
        register_trending_collector("baidu", BaiduCollector)
    """
    _trending_registry.register(name, collector_class)


def get_trending_collector(name: str, config: Optional[Dict] = None) -> Optional[BaseTrendingCollector]:
    """获取热搜采集器实例（便捷函数）

    使用方式：
        collector = get_trending_collector("baidu")
        items = collector.fetch(limit=50)
    """
    return _trending_registry.get(name, config)


def list_trending_collectors() -> List[str]:
    """列出所有已注册的采集器名称（便捷函数）"""
    return _trending_registry.list_available()
