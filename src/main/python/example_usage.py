# -*- coding: utf-8 -*-
"""
THUCNews+BERTopic 主题模型 - 使用示例

这里展示如何在你的Python代码中调用主题模型
"""

from pathlib import Path
from topic_model_trainer import TopicModelTrainer


# ==========================================
# 示例1: 从零开始训练模型
# ==========================================

def example_train_from_scratch():
    """示例：从零开始训练模型"""

    print("\n" + "=" * 80)
    print("示例1: 从零开始训练")
    print("=" * 80)

    # 创建训练器
    trainer = TopicModelTrainer(output_dir="data/my_model")

    # 方式A: 应用预设配置
    # 可选预设: test, small, medium, large, full
    trainer.apply_preset("medium")

    # 方式B: 自定义配置（可选）
    trainer.set_config("n_topics", 50, "model")  # 设置50个主题
    trainer.set_config("sample_size", 50000, "data")  # 使用5万样本

    # 查看配置
    trainer.print_config()

    # 开始训练
    result = trainer.train()

    # 查看结果
    print(f"\n训练完成！")
    print(f"  训练时间: {result.training_time:.1f}秒")
    print(f"  文档数: {result.n_documents}")
    print(f"  主题数: {result.n_topics}")

    # 列出前10个主题
    print(f"\n前10个主题:")
    topics = trainer.list_topics(10)
    for _, row in topics.iterrows():
        print(f"  主题{row['Topic']:3d}: {row['Count']:4d}篇 - {row['Label']}")

    # 保存模型（会自动保存，但也可以显式保存）
    trainer.save()

    return trainer


# ==========================================
# 示例2: 加载已有模型进行预测
# ==========================================

def example_load_and_predict():
    """示例：加载已有模型进行预测"""

    print("\n" + "=" * 80)
    print("示例2: 加载模型并预测")
    print("=" * 80)

    # 加载训练好的模型
    trainer = TopicModelTrainer.load("data/my_model")

    # 单条预测
    text = "北京今天举办了一场重要的科技展览会，吸引了众多企业参与"
    result = trainer.predict(text)

    print(f"\n文本: {text}")
    print(f"预测主题: {result.topic_id}")
    print(f"主题标签: {result.topic_label}")
    if result.probability:
        print(f"置信度: {result.probability:.4f}")
    print(f"主题词:")
    for word, score in result.topic_words:
        print(f"  {word} ({score:.4f})")

    # 批量预测
    texts = [
        "中国股市今日大涨，投资者信心增强",
        "新型人工智能技术在医疗领域取得突破",
        "北京冬奥会开幕式精彩回顾",
        "教育部发布新政策，减轻学生课业负担",
    ]

    print(f"\n批量预测 {len(texts)} 条文本:")
    results = trainer.predict(texts)
    for i, r in enumerate(results):
        print(f"  [{i+1}] 主题{r.topic_id:3d}: {r.topic_label[:30]}...")


# ==========================================
# 示例3: 快速训练不同规模的模型
# ==========================================

def example_different_sizes():
    """示例：训练不同规模的模型"""

    print("\n" + "=" * 80)
    print("示例3: 训练不同规模模型")
    print("=" * 80)

    # 快速测试（使用小模型）
    print("\n--- 测试版: 5000样本 ---")
    trainer_test = TopicModelTrainer("data/model_test")
    trainer_test.apply_preset("test")
    result_test = trainer_test.train()

    # 完整版（生产环境）
    # print("\n--- 完整版: 全量数据 ---")
    # trainer_full = TopicModelTrainer("data/model_full")
    # trainer_full.apply_preset("full")
    # result_full = trainer_full.train()


# ==========================================
# 示例4: 模型分析和导出
# ==========================================

def example_analysis():
    """示例：分析训练好的模型"""

    print("\n" + "=" * 80)
    print("示例4: 模型分析")
    print("=" * 80)

    # 加载模型
    trainer = TopicModelTrainer.load("data/my_model")

    # 获取所有主题信息
    topic_info = trainer.get_topic_info()
    print(f"\n全部主题数: {len(topic_info)}")
    print("\n主题分布:")
    print(topic_info[["Topic", "Count", "Label"]].head(20).to_string(index=False))

    # 查看特定主题详情
    print(f"\n主题5详情:")
    topic5_words = trainer.get_topic_words(5, top_n=10)
    for word, score in topic5_words:
        print(f"  {word:10s} ({score:.4f})")

    # 导出主题摘要
    output_path = Path("data/my_model/topic_summary.csv")
    topic_info.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n主题摘要已导出到: {output_path}")


# ==========================================
# 示例5: 整合到你的项目
# ==========================================

class MyNewsAnalyzer:
    """示例：将主题模型整合到你自己的项目中"""

    def __init__(self, model_path: str = "data/my_model"):
        """初始化，加载模型"""
        print("加载主题模型...")
        self.trainer = TopicModelTrainer.load(model_path)
        print("模型加载完成！")

    def analyze_news(self, news_text: str):
        """分析单条新闻"""
        result = self.trainer.predict(news_text)
        return {
            "topic_id": result.topic_id,
            "topic_label": result.topic_label,
            "keywords": [w for w, s in result.topic_words],
            "confidence": result.probability,
        }

    def batch_analyze(self, news_list: list):
        """批量分析新闻"""
        return [self.analyze_news(news) for news in news_list]


def example_integrate():
    """示例：整合到自己的项目"""

    print("\n" + "=" * 80)
    print("示例5: 整合到你的项目")
    print("=" * 80)

    # 创建你的分析器
    analyzer = MyNewsAnalyzer("data/my_model")

    # 使用
    news = "最新研究显示，气候变暖正在加速北极冰层融化"
    analysis = analyzer.analyze_news(news)

    print(f"\n新闻: {news}")
    print(f"分析结果:")
    print(f"  主题ID: {analysis['topic_id']}")
    print(f"  主题标签: {analysis['topic_label']}")
    print(f"  关键词: {', '.join(analysis['keywords'][:5])}")
    if analysis['confidence']:
        print(f"  置信度: {analysis['confidence']:.4f}")


# ==========================================
# 主程序
# ==========================================

if __name__ == "__main__":

    print("THUCNews+BERTopic 主题模型 - 使用示例")
    print("=" * 80)

    # 先训练一个测试模型（使用小数据集）
    print("\n>>> 第一步: 训练测试模型")
    trainer = TopicModelTrainer("data/model_test")
    trainer.apply_preset("test")
    trainer.train()

    # 示例2: 加载并预测
    print("\n>>> 第二步: 加载模型并预测")
    example_load_and_predict()

    # 示例4: 分析模型
    print("\n>>> 第三步: 分析模型")
    example_analysis()

    # 示例5: 整合到项目
    print("\n>>> 第四步: 项目整合示例")
    example_integrate()

    print("\n" + "=" * 80)
    print("所有示例完成！")
    print("=" * 80)
    print("\n接下来你可以:")
    print(" 1. 修改 example_usage.py 中的代码")
    print(" 2. 使用 'medium' 预设训练更大的模型")
    print(" 3. 查看 'data/model_test/visualizations/' 下的可视化")
    print(" 4. 参考 topic_model_config.py 修改配置")
