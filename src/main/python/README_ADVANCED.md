# THUCNews+BERTopic 高级训练系统

支持断点续训的完整中文主题建模系统！

## 🌟 特性

- ✅ **断点续训**: 随时停止，随时恢复，不怕断电！
- ✅ **分阶段保存**: 8个阶段分别保存检查点
- ✅ **预设配置**: 5种预设一键启动
- ✅ **固定50主题**: 默认推荐配置（可自定义）
- ✅ **完整可视化**: 多种交互式可视化
- ✅ **中文优化**: 针对中文文本的预处理和模型选择

## 📁 文件说明

```
SentiGuard/src/main/python/
├── train_thucnews_advanced.py    # 核心训练脚本（支持断点续训）
├── run_advanced_training.py       # 快速启动器（推荐使用）
├── load_and_infer.py              # 模型加载和推理
└── README_ADVANCED.md             # 本文档
```

## 🚀 快速开始

### 方式1: 使用快速启动器（推荐）

```bash
# 查看可用预设
python run_advanced_training.py list

# 运行测试版（5000样本，20主题）
python run_advanced_training.py test

# 运行推荐版（50000样本，50主题）⭐
python run_advanced_training.py medium

# 运行大型版（100000样本，75主题）
python run_advanced_training.py large
```

### 方式2: 直接使用核心脚本

```bash
# 基本用法：50000样本，50主题
python train_thucnews_advanced.py --sample 50000 --n_topics 50

# 重置训练（清除检查点）
python train_thucnews_advanced.py --sample 50000 --n_topics 50 --reset

# 不恢复，从头开始
python train_thucnews_advanced.py --sample 50000 --n_topics 50 --no_resume
```

## 📋 预设配置

| 预设 | 样本量 | 主题数 | 嵌入模型 | 说明 |
|------|--------|--------|----------|------|
| test | 5,000 | 20 | bge-small-zh | 快速测试 |
| small | 10,000 | 30 | bge-small-zh | 小型训练 |
| medium | 50,000 | 50 | bge-large-zh | ⭐ 推荐 |
| large | 100,000 | 75 | bge-large-zh | 高质量 |
| full | 全量 | 100 | bge-large-zh | 生产级 |

## 🔄 断点续训说明

### 如何停止训练

在训练过程中按 `Ctrl+C` 即可安全停止。

### 如何恢复训练

直接再次运行相同的命令即可！系统会自动检测上次完成的阶段，从断点继续。

### 训练阶段

系统会依次执行8个阶段，每个阶段完成后都会保存检查点：

1. **数据下载** → 保存原始数据
2. **文本预处理** → 保存分词后的文本
3. **文本嵌入** → 保存嵌入向量
4. **UMAP降维** → (内部)
5. **HDBSCAN聚类** → (内部)
6. **主题建模** → 保存中间模型
7. **保存模型** → 保存最终模型
8. **可视化** → 保存所有图表

## 📊 输出结构

```
data/thucnews_advanced/{preset}/
├── checkpoints/              # 检查点（用于恢复）
│   ├── metadata.json         # 训练元数据
│   ├── data_checkpoint.pkl   # 原始数据
│   ├── preprocessed_checkpoint.pkl  # 预处理后数据
│   ├── embeddings_checkpoint.npy    # 嵌入向量
│   └── bertopic_checkpoint/  # 模型检查点
├── bertopic_model/           # 最终模型
├── data/                     # 数据
│   └── raw_data.csv
├── visualizations/           # 可视化
│   ├── topics_2d.html        # 2D主题图（推荐首先查看）
│   ├── topic_barchart.html   # 主题词条形图
│   ├── topic_heatmap.html    # 主题相似度热力图
│   └── topic_hierarchy.html  # 主题层次结构
├── topic_info.csv            # 主题信息
├── documents_with_topics.csv # 文档-主题分配
└── training.log              # 训练日志
```

## 🔍 模型推理和探索

### 加载模型探索主题

```bash
# 查看所有主题
python load_and_infer.py explore {model_dir}

# 查看特定主题
python load_and_infer.py explore {model_dir} --topic_id 5

# 导出主题摘要
python load_and_infer.py explore {model_dir} --export summary.csv
```

### 预测新文本

```bash
# 单条文本预测
python load_and_infer.py predict {model_dir} --text "这里是中文新闻文本..."

# 批量预测
python load_and_infer.py predict {model_dir} --file input.txt --output results.csv
```

### Python代码使用

```python
from load_and_infer import TopicModelInferencer

# 加载模型
inferencer = TopicModelInferencer(Path("data/thucnews_advanced/medium"))

# 预测
result = inferencer.predict_single("这里是你的中文文本...")
print(f"主题: {result['topic_id']}")
print(f"主题词: {result['topic_words']}")

# 获取主题信息
topic_info = inferencer.get_topic_info()
print(topic_info.head(10))

# 获取主题示例
examples = inferencer.get_topic_examples(topic_id=0, n=5)
```

## ⚙️ 自定义参数

如果预设不符合需求，可以自定义参数：

```bash
# 使用medium预设，但修改主题数为80
python run_advanced_training.py medium --n_topics 80

# 完全自定义
python train_thucnews_advanced.py \
    --sample 80000 \
    --n_topics 60 \
    --embedding_model "BAAI/bge-large-zh-v1.5" \
    --min_topic_size 40 \
    --output_dir "data/my_custom_model"
```

## 🎯 最佳实践

### 第一次使用

1. 先用test预设测试环境
2. 确认无误后使用medium预设
3. 生成结果后查看可视化

### 生产环境训练

```bash
# 推荐配置：50000样本，50主题
python run_advanced_training.py medium

# 或者大型配置
python run_advanced_training.py large
```

### 监控训练

```bash
# 查看训练日志
tail -f data/thucnews_advanced/medium/training.log
```

## 📈 查看结果

训练完成后，按以下顺序查看：

1. **visualizations/topics_2d.html** → 2D主题分布图（在浏览器中打开）
2. **topic_info.csv** → 完整主题列表
3. **visualizations/topic_barchart.html** → 前20个主题的词频图

## 🛠️ 常见问题

### Q: 训练被中断了怎么办？

A: 直接再次运行相同的命令！系统会自动检测断点继续。

### Q: 想从头开始怎么办？

A: 使用 `--reset` 参数：
```bash
python run_advanced_training.py medium --reset
```

### Q: 内存不足怎么办？

A: 减小样本量或使用更小的嵌入模型：
```bash
python run_advanced_training.py test --embedding_model "BAAI/bge-small-zh-v1.5"
```

### Q: 如何选择主题数量？

A: 
- 测试: 20-30
- 标准: 50 (推荐)
- 大量数据: 75-100

### Q: 训练需要多长时间？

| 预设 | 估计时间 |
|------|----------|
| test | 5-10分钟 |
| small | 15-25分钟 |
| medium | 45-90分钟 |
| large | 2-4小时 |
| full | 4-8小时 |

## 📚 相关资源

- [BERTopic官方文档](https://maartengr.github.io/BERTopic/)
- [THUCNews数据集](https://github.com/thunlp/THUCNews)
- [BGE嵌入模型](https://github.com/FlagOpen/FlagEmbedding)

## 🤝 技术支持

如有问题，请查看：
1. training.log - 训练日志
2. checkpoints/ - 检查点
3. 本文档 - 常见问题解答
