# -*- coding: utf-8 -*-
"""
THUCNews+BERTopic 配置文件
可以在这里修改所有配置
"""

from pathlib import Path
from typing import Optional


# ==========================================
# 基础配置
# ==========================================

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 默认输出目录
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/thucnews_model"

# 是否启用断点续训
ENABLE_CHECKPOINT = True

# 训练种子（保证可复现）
RANDOM_SEED = 42


# ==========================================
# 数据配置
# ==========================================

DATA_CONFIG = {
    # 样本量：0=全量，其他为采样数量
    "sample_size": 50000,

    # HF数据集仓库
    "hf_dataset": "madao33/new-title-chinese",

    # 数据集split
    "split": "train",

    # 是否使用流式加载（适合超大数据）
    "streaming": False,
}


# ==========================================
# 模型配置
# ==========================================

MODEL_CONFIG = {
    # 主题数量（推荐：30-100）
    "n_topics": 50,

    # 最小主题大小（每个主题至少包含的文档数）
    "min_topic_size": 30,

    # 嵌入模型
    # - 快速: "BAAI/bge-small-zh-v1.5"
    # - 推荐: "BAAI/bge-large-zh-v1.5"
    # - 其他: "paraphrase-multilingual-MiniLM-L12-v2"
    "embedding_model": "BAAI/bge-large-zh-v1.5",
}


# ==========================================
# UMAP降维配置
# ==========================================

UMAP_CONFIG = {
    # 邻居数量
    "n_neighbors": 15,

    # 降维后的维度
    "n_components": 5,

    # 最小距离
    "min_dist": 0.0,

    # 距离度量
    "metric": "cosine",
}


# ==========================================
# HDBSCAN聚类配置
# ==========================================

HDBSCAN_CONFIG = {
    # 最小样本数
    "min_samples": None,  # None表示使用 min_topic_size // 3

    # 聚类选择方法: "eom" or "leaf"
    "cluster_selection_method": "eom",

    # 距离度量
    "metric": "euclidean",
}


# ==========================================
# 预处理配置
# ==========================================

PREPROCESS_CONFIG = {
    # 最小文本长度（分词后）
    "min_text_length": 10,

    # 是否启用扩展停用词
    "use_extended_stopwords": True,

    # 是否使用bigram（二元词组）
    "use_bigrams": True,

    # ngram范围
    "ngram_range": (1, 2),
}


# ==========================================
# 可视化配置
# ==========================================

VIZ_CONFIG = {
    # 是否生成可视化
    "enable_viz": True,

    # 2D图宽度和高度
    "topics_2d_width": 1200,
    "topics_2d_height": 900,

    # 条形图显示前N个主题
    "barchart_top_n": 20,

    # 热力图显示前N个主题
    "heatmap_top_n": 30,
}


# ==========================================
# 扩展中文停用词表
# ==========================================

EXTENDED_CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "他", "她", "它们", "我们", "什么", "吗", "呢", "吧", "啊",
    "把", "被", "从", "到", "对", "对于", "关于", "跟", "与", "同", "给", "让",
    "个", "位", "件", "份", "条", "根", "块", "片", "页", "题", "行", "列",
    "是", "有", "在", "来", "去", "上", "下", "左", "右", "前", "后", "里", "外",
    "将", "已经", "正在", "就要", "刚刚", "忽然", "突然", "终于", "其实",
    "但是", "可是", "不过", "然而", "因此", "所以", "于是", "结果", "因为",
    "可以", "能够", "应该", "会", "要", "想", "希望", "愿意", "打算",
    "这个", "那个", "这些", "那些", "这样", "那样", "怎么", "如何", "为什么",
    "中国", "新闻", "报道", "记者", "表示", "称", "说", "指出", "认为", "透露",
    "日", "月", "年", "今天", "昨天", "明天", "近日", "日前", "目前", "至今",
    "已", "已经", "曾", "曾经", "将", "即将", "正在", "正", "在", "中",
}


# ==========================================
# 预设配置（快速切换）
# ==========================================

PRESETS = {
    # 测试配置
    "test": {
        "data": {"sample_size": 5000},
        "model": {"n_topics": 20, "embedding_model": "BAAI/bge-small-zh-v1.5"},
    },

    # 小型配置
    "small": {
        "data": {"sample_size": 10000},
        "model": {"n_topics": 30, "embedding_model": "BAAI/bge-small-zh-v1.5"},
    },

    # 中型配置（推荐）
    "medium": {
        "data": {"sample_size": 50000},
        "model": {"n_topics": 50, "embedding_model": "BAAI/bge-large-zh-v1.5"},
    },

    # 大型配置
    "large": {
        "data": {"sample_size": 100000},
        "model": {"n_topics": 75, "embedding_model": "BAAI/bge-large-zh-v1.5"},
    },

    # 完整配置
    "full": {
        "data": {"sample_size": 0},
        "model": {"n_topics": 100, "embedding_model": "BAAI/bge-large-zh-v1.5"},
    },
}


def apply_preset(preset_name: str):
    """
    应用预设配置

    Args:
        preset_name: 预设名称，可选: test, small, medium, large, full
    """
    if preset_name not in PRESETS:
        raise ValueError(f"未知预设: {preset_name}，可用: {list(PRESETS.keys())}")

    preset = PRESETS[preset_name]

    # 应用数据配置
    if "data" in preset:
        DATA_CONFIG.update(preset["data"])

    # 应用模型配置
    if "model" in preset:
        MODEL_CONFIG.update(preset["model"])

    print(f"✅ 已应用预设: {preset_name}")


def print_config():
    """打印当前配置"""
    print("\n" + "=" * 80)
    print("当前配置")
    print("=" * 80)
    print(f"\n数据配置:")
    for k, v in DATA_CONFIG.items():
        print(f"  {k}: {v}")
    print(f"\n模型配置:")
    for k, v in MODEL_CONFIG.items():
        print(f"  {k}: {v}")
    print(f"\nUMAP配置:")
    for k, v in UMAP_CONFIG.items():
        print(f"  {k}: {v}")
    print(f"\n可视化配置:")
    for k, v in VIZ_CONFIG.items():
        print(f"  {k}: {v}")
    print("\n" + "=" * 80 + "\n")
