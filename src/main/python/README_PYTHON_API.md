# THUCNews+BERTopic Python API

专为其他Python代码调用设计的主题模型API！

## 📦 快速开始

### 3行代码训练模型

```python
from topic_model_trainer import TopicModelTrainer

# 创建训练器，应用预设
trainer = TopicModelTrainer("data/my_model")
trainer.apply_preset("medium")  # 50主题，5万样本

# 开始训练
result = trainer.train()
```

### 3行代码加载并预测

```python
from topic_model_trainer import TopicModelTrainer

# 加载模型
trainer = TopicModelTrainer.load("data/my_model")

# 预测
result = trainer.predict("你的中文新闻文本")
print(f"主题: {result.topic_id}")
```

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| **topic_model_config.py** | 配置文件（修改这里的设置） |
| **topic_model_trainer.py** | 核心训练类（主要API） |
| **example_usage.py** | 使用示例（参考这里） |
| **README_PYTHON_API.md** | 本文档 |

## 🎯 预设配置

| 预设 | 样本 | 主题 | 嵌入模型 | 说明 |
|------|------|------|----------|------|
| test | 5,000 | 20 | small | 快速测试 |
| small | 10,000 | 30 | small | 小型训练 |
| medium | 50,000 | 50 | large | ⭐ 推荐 |
| large | 100,000 | 75 | large | 高质量 |
| full | 全量 | 100 | large | 生产级 |

## 📚 API 参考

### TopicModelTrainer 类

#### 初始化

```python
from topic_model_trainer import TopicModelTrainer

# 创建训练器
trainer = TopicModelTrainer(
    output_dir="data/my_model",  # 输出目录
    use_checkpoint=True          # 启用断点续训
)
```

#### 配置设置

```python
# 应用预设
trainer.apply_preset("medium")

# 自定义配置
trainer.set_config("n_topics", 50, "model")      # 主题数
trainer.set_config("sample_size", 50000, "data") # 样本量
trainer.set_config("embedding_model", "BAAI/bge-large-zh-v1.5", "model")

# 查看配置
trainer.print_config()
```

#### 训练和保存

```python
# 开始训练
result = trainer.train()

# 强制重新开始（忽略检查点）
result = trainer.train(force_restart=True)

# 保存模型
trainer.save("path/to/save")
```

#### 加载模型

```python
# 加载已有模型
trainer = TopicModelTrainer.load("path/to/model")
```

#### 预测

```python
# 单条预测
result = trainer.predict("这里是中文新闻文本")
print(result.topic_id)        # 主题ID
print(result.topic_label)     # 主题标签
print(result.topic_words)     # 主题词列表
print(result.probability)     # 置信度（可选）

# 批量预测
results = trainer.predict(["文本1", "文本2", "文本3"])
```

#### 获取信息

```python
# 获取所有主题信息
topic_info = trainer.get_topic_info()
print(topic_info)

# 列出前N个主题
topics = trainer.list_topics(20)

# 获取特定主题的关键词
words = trainer.get_topic_words(topic_id=5, top_n=10)
```

### TrainingResult 对象

训练后返回的结果对象：

```python
result = trainer.train()

print(result.success)          # 是否成功
print(result.output_dir)       # 输出目录
print(result.topic_model)      # BERTopic模型对象
print(result.topic_info)       # 主题信息DataFrame
print(result.n_topics)         # 主题数
print(result.n_documents)      # 文档数
print(result.training_time)    # 训练时间
```

### PredictionResult 对象

预测返回的结果对象：

```python
result = trainer.predict("新闻文本")

print(result.topic_id)         # 主题ID (int)
print(result.topic_words)      # 主题词 [(word, score), ...]
print(result.topic_label)      # 主题标签 (str)
print(result.probability)      # 置信度 (float或None)
print(result.text)             # 原始文本 (str)
```

## 🔧 配置修改

直接编辑 `topic_model_config.py`：

```python
# 修改数据配置
DATA_CONFIG = {
    "sample_size": 50000,      # 样本量
    ...
}

# 修改模型配置
MODEL_CONFIG = {
    "n_topics": 50,            # 主题数
    "min_topic_size": 30,      # 最小主题大小
    ...
}
```

## 💡 使用示例

### 示例1: 简单训练和预测

```python
from topic_model_trainer import TopicModelTrainer

# 训练
trainer = TopicModelTrainer("data/my_model")
trainer.apply_preset("medium")
trainer.train()

# 预测
result = trainer.predict("北京今天天气晴朗")
print(f"主题: {result.topic_id}")
```

### 示例2: 整合到你的类

```python
from topic_model_trainer import TopicModelTrainer

class NewsAnalyzer:
    def __init__(self):
        self.trainer = TopicModelTrainer.load("data/my_model")

    def analyze(self, text):
        pred = self.trainer.predict(text)
        return {
            "topic": pred.topic_id,
            "keywords": [w for w, s in pred.topic_words],
        }

# 使用
analyzer = NewsAnalyzer()
result = analyzer.analyze("新闻文本")
```

### 示例3: 自定义配置训练

```python
from topic_model_trainer import TopicModelTrainer

trainer = TopicModelTrainer("data/custom_model")

# 逐个配置
trainer.set_config("sample_size", 80000, "data")
trainer.set_config("n_topics", 60, "model")
trainer.set_config("min_topic_size", 40, "model")

# 训练
trainer.train()
```

## 📊 输出目录结构

```
data/my_model/
├── bertopic_model/           # 模型文件
├── checkpoints/              # 检查点（用于断点续训）
│   ├── metadata.json
│   ├── data.pkl
│   ├── processed.pkl
│   └── embeddings.npy
├── visualizations/           # 可视化图表
│   ├── topics_2d.html       # 2D主题图（浏览器打开）
│   ├── topic_barchart.html  # 主题词条形图
│   └── topic_heatmap.html   # 主题相似度热力图
├── topic_info.csv           # 主题信息
├── documents_with_topics.csv # 文档-主题分配
└── training.log             # 训练日志
```

## 🔄 断点续训

训练器自动支持断点续训：

- 按 `Ctrl+C` 停止训练
- 再次调用 `trainer.train()` 自动恢复
- 每个阶段都会保存检查点

## ⚙️ 配置类型

支持的配置类型：

| 类型 | 说明 |
|------|------|
| data | 数据相关配置 |
| model | 模型相关配置 |
| umap | 降维相关配置 |
| hdbscan | 聚类相关配置 |
| preprocess | 预处理相关配置 |
| viz | 可视化相关配置 |

```python
trainer.set_config("key", value, "data")       # 数据配置
trainer.set_config("key", value, "model")      # 模型配置
trainer.set_config("key", value, "umap")       # UMAP配置
# ... 等等
```

## 🎨 查看可视化结果

训练完成后，在浏览器中打开：

```
data/my_model/visualizations/topics_2d.html
```

## 📖 更多示例

详见 `example_usage.py`，包含：

1. 从零开始训练
2. 加载和预测
3. 不同规模训练
4. 模型分析
5. 项目整合示例

## 🆘 常见问题

**Q: 如何更改主题数量？**

```python
trainer.set_config("n_topics", 80, "model")
```

**Q: 训练被中断了怎么办？**

```python
# 再次调用train()即可，会自动恢复
trainer.train()
```

**Q: 如何强制从头开始？**

```python
trainer.train(force_restart=True)
```

**Q: 如何使用更小的模型加快训练？**

```python
trainer.apply_preset("small")
# 或
trainer.set_config("embedding_model", "BAAI/bge-small-zh-v1.5", "model")
```

**Q: 如何获取BERTopic原始对象？**

```python
# result.topic_model 是原始的BERTopic对象
bertopic_model = result.topic_model
# 然后可以调用BERTopic的所有方法
```
