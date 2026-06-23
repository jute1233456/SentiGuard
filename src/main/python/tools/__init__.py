#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具模块
"""
from src.main.python.tools.retrieve import search_retrieve_news

# 导入搜索引擎实现以完成注册
from src.main.python.tools import search_anspire
from src.main.python.tools.search_base import (
    BaseSearchEngine,
    SearchResult,
    SearchQuery,
    SearchEngineRegistry,
    register_search_engine,
    get_search_engine,
    list_search_engines,
)

# 搜索服务模块（两种搜索策略）
from src.main.python.tools import search_service
