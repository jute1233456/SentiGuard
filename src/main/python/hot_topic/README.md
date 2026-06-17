# Hot Topic Discovery —— 完整管线

热点发现系统，包含：
1. **Stage 1**: 数据接入层（THUCNews / GDELT）
2. **Stage 2**: BERTopic 主题建模（中文）
3. **Stage 3**: 可视化 + 模型持久化

---

## 架构

```
THUCNews (HF datasets, 离线，开发用)  ──┐
                                        ├─► 统一 DataFrame ─► 中文预处理 ─► BERTopic 建模 ─► 可视化/保存
GDELT DOC 2.0 (在线 API，运行用)      ──┘
```

---

## 安装

```bash
cd SentiGuard
pip install -r src/main/python/hot_topic/requirements.txt
```

---

## Stage 1: 数据接入

### 拉取 THUCNews（离线开发用）
```bash
cd src/main/python
python -m hot_topic.scripts.fetch_thucnews              # 默认 1 万条
python -m hot_topic.scripts.fetch_thucnews -n 50000     # 5 万条
```
输出：`data/hot_topic/thucnews_sample.csv`

### 拉取 GDELT（实时运行用）
```bash
python -m hot_topic.scripts.fetch_gdelt                          # 24h 中文新闻 250 条
python -m hot_topic.scripts.fetch_gdelt --timespan 6h --max 250
python -m hot_topic.scripts.fetch_gdelt --min-interval 30        # 更慢的节流防 429
python -m hot_topic.scripts.fetch_gdelt --cool-down 60           # 首次调用前先冷却
python -m hot_topic.scripts.fetch_gdelt --append                 # 增量合并到当日 CSV
```
输出：`data/hot_topic/gdelt_YYYYMMDD.csv`

---

## Stage 2: BERTopic 主题建模

### THUCNews 端到端 Demo
直接用 THUCNews 10k 跑一遍完整建模：
```bash
cd src/main/python
python -m hot_topic.scripts.run_thucnews_demo --sample 10000
```
输出：`data/hot_topic/thucnews_demo/`
- `bertopic_model/` —— 保存的 BERTopic 模型
- `topic_summary.csv` —— 主题摘要表
- `thucnews_with_topics.csv` —— 每个文档的主题分配
- `*.html` —— 交互式可视化（主题分布、条形图、热力图）

### 在 Python 中直接调用

```python
from hot_topic.data_source import THUCNewsLoader
from hot_topic.preprocessing import preprocess_for_bertopic, build_stopwords
from hot_topic.modeling import (
    build_chinese_bertopic,
    train_topic_model,
    save_topic_model,
    get_topic_summary,
)
from hot_topic.visualization import (
    visualize_topics,
    visualize_topic_barchart,
    visualize_heatmap,
    save_figure,
)

# 1. 加载数据
loader = THUCNewsLoader()
docs_df = loader.to_dataframe(sample_size=10_000)
raw_texts = (docs_df["title"] + " " + docs_df["content"]).tolist()

# 2. 预处理中文
stopwords = build_stopwords()
tokenized_texts = preprocess_for_bertopic(raw_texts, stopwords=stopwords)

# 3. 构建并训练主题模型
topic_model = build_chinese_bertopic(
    embedding_model="BAAI/bge-small-zh-v1.5",  # 中文 BGE 小模型
    min_topic_size=20,
    seed=42,
)
result = train_topic_model(topic_model, tokenized_texts, raw_docs=raw_texts)

# 4. 查看主题
topic_summary = get_topic_summary(topic_model)
print(topic_summary[["Topic", "Count", "Label"]].head(10))

# 5. 保存模型和可视化
save_topic_model(topic_model, "models/bertopic_model")
save_figure(visualize_topics(topic_model), "output/topics_2d.html")
save_figure(visualize_topic_barchart(topic_model), "output/topic_bars.html")
```

---

## Stage 3: 模型持久化与推理

### 保存模型
```python
from hot_topic.modeling import save_topic_model
save_topic_model(topic_model, "path/to/model_dir")
```

### 加载模型并预测新文档
```python
from hot_topic.modeling import load_topic_model
from hot_topic.preprocessing import chinese_tokenize

topic_model = load_topic_model("path/to/model_dir")

new_text = "这里是你要预测的新中文新闻文本..."
tokenized = chinese_tokenize(new_text)
topics, probs = topic_model.transform([tokenized])
print(f"Predicted topic: {topics[0]}, probability: {probs[0][topics[0]]:.3f}")
```

---

## 已知限制

- **GDELT 限流**: GDELT 要求 ~1 req/5s，已内置节流和 429 重试；换代理节点或调 `--min-interval`
- **GDELT 正文**: DOC API 只返回元数据（标题/URL），正文要自己爬（后续可加）
- **THUCNews HF 镜像**: 如果默认镜像列名不匹配，设环境变量 `THUCNEWS_HF_REPO=other/repo`

---

## 测试

```bash
cd src/main/python
pytest hot_topic/tests -v
```
Mock 测试，不需要联网。
