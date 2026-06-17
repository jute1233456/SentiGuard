# THUCNews + BERTopic 训练指南

本指南介绍如何使用改进的脚本在THUCNews数据集上训练BERTopic模型。

## 快速开始

### 最简单的方式（推荐）

使用预设配置快速开始训练：

```bash
cd SentiGuard/src/main/python

# 小型测试（10k文档，快速）
python train_thucnews_simple.py --size small

# 中型（50k文档，推荐）
python train_thucnews_simple.py --size medium

# 大型（100k文档，质量更好）
python train_thucnews_simple.py --size large

# 全量数据集
python train_thucnews_simple.py --size full
```

### 使用快速模式

使用更小的嵌入模型加速训练：

```bash
python train_thucnews_simple.py --size medium --fast
```

---

## 完整功能训练脚本

对于需要更精细控制的情况，使用完整的训练脚本：

```bash
cd SentiGuard/src/main/python

# 基本用法
python -m hot_topic.scripts.train_thucnews_improved --sample 50000

# 指定嵌入模型
python -m hot_topic.scripts.train_thucnews_improved \
    --sample 50000 \
    --embedding_model "BAAI/bge-large-zh-v1.5"

# 调整主题数量
python -m hot_topic.scripts.train_thucnews_improved \
    --sample 50000 \
    --min_topic_size 50 \
    --nr_topics 30

# 调整UMAP参数
python -m hot_topic.scripts.train_thucnews_improved \
    --sample 50000 \
    --n_neighbors 20 \
    --n_components 10

# 为运行命名（创建子目录）
python -m hot_topic.scripts.train_thucnews_improved \
    --sample 50000 \
    --name my_experiment_001

# 详细日志
python -m hot_topic.scripts.train_thucnews_improved --sample 50000 -v
```

---

## 参数说明

### 数据参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--sample` | 采样文档数量，0表示全量 | 50000 |
| `--repo` | HuggingFace数据集仓库 | madao33/new-title-chinese |
| `--split` | 数据集分割 | train |
| `--streaming` | 使用流式加载（适合超大数据） | False |

### 模型参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--embedding_model` | 嵌入模型 | BAAI/bge-large-zh-v1.5 |
| `--min_topic_size` | 最小主题大小 | 30 |
| `--nr_topics` | 目标主题数（None=自动） | None |
| `--n_neighbors` | UMAP邻居数 | 15 |
| `--n_components` | UMAP维度 | 5 |

### 预处理参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--min_text_len` | 最小分词后长度 | 15 |
| `--use_extended_stopwords` | 使用扩展停用词表 | True |

### 输出参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output_dir` | 输出目录 | data/hot_topic/thucnews_improved |
| `--name` | 运行名称（子目录） | None |

---

## 输出文件结构

训练完成后，输出目录包含：

```
thucnews_improved/{name}/
├── bertopic_model/              # 保存的BERTopic模型
│   ├── model.safetensors
│   └── ...
├── thucnews_raw.csv             # 原始数据
├── preprocessed_texts.txt       # 预处理后的文本
├── topic_summary.csv            # 主题摘要
├── thucnews_with_topics.csv     # 文档-主题分配
├── evaluation_report.csv        # 评估报告
│
├── topics_2d.html               # 2D主题可视化
├── topic_barchart.html          # 主题词条形图
├── topic_hierarchy.html         # 主题层次结构
├── topic_similarity_heatmap.html # 主题相似度热力图
├── term_rank.html               # 词排名
└── topic_distribution.html      # 主题分布
```

---

## 推荐配置

### 开发/测试阶段

```bash
python train_thucnews_simple.py --size small --fast
```

- 10k文档
- 小型嵌入模型
- 快速迭代

### 标准训练

```bash
python train_thucnews_simple.py --size medium
```

- 50k文档
- 大型嵌入模型
- 质量与速度平衡

### 高质量训练

```bash
python train_thucnews_simple.py --size large
```

- 100k文档
- 大型嵌入模型
- 更大的最小主题规模

### 生产级训练

```bash
python -m hot_topic.scripts.train_thucnews_improved \
    --sample 0 \
    --min_topic_size 100 \
    --embedding_model "BAAI/bge-large-zh-v1.5" \
    --name production_v1
```

---

## 嵌入模型选择

| 模型 | 说明 | 速度 | 质量 |
|------|------|------|------|
| `BAAI/bge-small-zh-v1.5` | 小型中文嵌入模型 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| `BAAI/bge-base-zh-v1.5` | 中型中文嵌入模型 | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| `BAAI/bge-large-zh-v1.5` | 大型中文嵌入模型 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| `paraphrase-multilingual-MiniLM-L12-v2` | 多语言模型 | ⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 加载和使用训练好的模型

```python
from pathlib import Path
from hot_topic.modeling import load_topic_model
from hot_topic.preprocessing import chinese_tokenize, build_extended_stopwords

# 加载模型
model_path = Path("data/hot_topic/thucnews_improved/medium/bertopic_model")
topic_model = load_topic_model(model_path)

# 预处理新文本
stopwords = build_extended_stopwords()
text = "这里是你的中文新闻文本..."
tokenized = chinese_tokenize(text, stopwords=stopwords)

# 预测
topics, probs = topic_model.transform([tokenized])
topic_id = topics[0]

# 查看主题信息
topic_words = topic_model.get_topic(topic_id)
topic_info = topic_model.get_topic_info()

print(f"预测主题: {topic_id}")
print(f"主题词: {topic_words}")
```

---

## 常见问题

### Q: 训练太慢怎么办？

A: 
1. 使用 `--fast` 标志或 `--embedding_model "BAAI/bge-small-zh-v1.5"`
2. 减少采样数量 `--sample 10000`
3. 增加 `--min_topic_size` 减少聚类复杂度

### Q: 主题质量不好怎么办？

A:
1. 增加训练数据量
2. 使用更大的嵌入模型
3. 调整 `--min_topic_size` 和 `--n_neighbors`
4. 检查停用词表是否合适

### Q: 内存不足怎么办？

A:
1. 减少采样数量
2. 使用更小的嵌入模型
3. 使用 `--streaming` 模式
4. 调整 `--n_components` 到更低的值

### Q: 如何恢复中断的训练？

A: 目前不支持直接恢复，但你可以：
1. 使用之前保存的预处理数据
2. 或者从原始数据重新开始（推荐）

---

## 高级用法

### 自定义停用词

```python
from hot_topic.scripts.train_thucnews_improved import build_extended_stopwords

# 从文件加载额外停用词
my_stopwords = build_extended_stopwords(
    stopwords_path=Path("my_stopwords.txt")
)

# 或者在代码中直接修改训练脚本
```

### 自定义预处理

修改 `hot_topic/preprocessing/text.py` 来自定义分词和清理逻辑。

### 自定义可视化

参考 `hot_topic/visualization/plots.py` 添加新的可视化。

---

## 相关资源

- [BERTopic 官方文档](https://maartengr.github.io/BERTopic/)
- [THUCNews 数据集](https://github.com/thunlp/THUCNews)
- [BGE 嵌入模型](https://github.com/FlagOpen/FlagEmbedding)
