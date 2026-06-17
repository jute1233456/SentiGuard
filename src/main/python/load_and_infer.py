#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型加载和推理脚本
- 加载训练好的BERTopic模型
- 对新文本进行主题预测
- 主题探索和分析
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# 设置HF镜像
import os
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 中文预处理相关
EXTENDED_CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "他", "她", "它们", "我们", "什么", "吗", "呢", "吧", "啊",
}


def preprocess_single_text(text: str, jieba_dict: Optional[Path] = None) -> str:
    """预处理单条中文文本"""
    try:
        import jieba
    except ImportError:
        logging.error("请安装jieba: pip install jieba")
        raise

    if not isinstance(text, str):
        text = str(text)

    # 清理
    import re
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 分词
    tokens = jieba.lcut(text)

    # 过滤
    filtered = []
    for token in tokens:
        token = token.strip()
        if len(token) < 1:
            continue
        if token in EXTENDED_CHINESE_STOPWORDS:
            continue
        if re.match(r"^[一-鿿]+$", token):
            filtered.append(token)
        elif re.match(r"^[a-zA-Z0-9]{2,}$", token):
            filtered.append(token.lower())

    return " ".join(filtered)


class TopicModelInferencer:
    """主题模型推理器"""

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.topic_model = None
        self.topic_info = None
        self.documents_with_topics = None

        self._load_model()

    def _load_model(self):
        """加载模型和相关数据"""
        try:
            from bertopic import BERTopic
        except ImportError:
            logging.error("请安装bertopic: pip install bertopic")
            raise

        logging.info(f"从 {self.model_dir} 加载模型...")
        self.topic_model = BERTopic.load(self.model_dir / "bertopic_model")
        logging.info("模型加载成功")

        # 加载主题信息（如果有）
        topic_info_path = self.model_dir / "topic_info.csv"
        if topic_info_path.exists():
            self.topic_info = pd.read_csv(topic_info_path, encoding="utf-8-sig")
            logging.info(f"已加载主题信息: {len(self.topic_info)} 个主题")

        # 加载文档（如果有）
        docs_path = self.model_dir / "documents_with_topics.csv"
        if docs_path.exists():
            self.documents_with_topics = pd.read_csv(docs_path, encoding="utf-8-sig")
            logging.info(f"已加载文档: {len(self.documents_with_topics)} 条")

    def get_topic_info(self, topic_id: Optional[int] = None) -> pd.DataFrame:
        """获取主题信息"""
        if self.topic_info is not None:
            if topic_id is not None:
                return self.topic_info[self.topic_info["Topic"] == topic_id]
            return self.topic_info
        else:
            # 从模型动态获取
            info = self.topic_model.get_topic_info()
            info["Label"] = info.apply(
                lambda row: " | ".join([w for w, _ in self.topic_model.get_topic(row["Topic"])[:5]])
                if row["Topic"] != -1 else "Outlier",
                axis=1,
            )
            return info

    def get_topic_words(self, topic_id: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """获取主题词"""
        if topic_id == -1:
            return []
        return self.topic_model.get_topic(topic_id)[:top_n]

    def predict_single(self, text: str, preprocess: bool = True) -> Dict[str, Any]:
        """预测单条文本的主题"""
        if preprocess:
            processed = preprocess_single_text(text)
        else:
            processed = text

        topics, probs = self.topic_model.transform([processed])
        topic_id = int(topics[0])

        result = {
            "topic_id": topic_id,
            "text": text,
            "processed_text": processed,
            "topic_words": self.get_topic_words(topic_id, top_n=5),
        }

        # 概率
        if probs is not None and len(probs) > 0:
            if hasattr(probs[0], "__len__") and len(probs[0]) > topic_id:
                result["probability"] = float(probs[0][topic_id])
            elif not hasattr(probs[0], "__len__"):
                result["probability"] = float(probs[0])

        # 主题标签
        if self.topic_info is not None:
            topic_row = self.topic_info[self.topic_info["Topic"] == topic_id]
            if len(topic_row) > 0:
                result["topic_label"] = topic_row.iloc[0].get("Label", "")
                result["topic_count"] = int(topic_row.iloc[0].get("Count", 0))

        return result

    def predict_batch(self, texts: List[str], preprocess: bool = True) -> List[Dict[str, Any]]:
        """批量预测"""
        results = []
        for i, text in enumerate(texts):
            if i % 100 == 0:
                logging.info(f"预测进度: {i}/{len(texts)}")
            results.append(self.predict_single(text, preprocess=preprocess))
        return results

    def find_similar_topics(self, topic_id: int, top_n: int = 5) -> List[Tuple[int, float]]:
        """查找相似主题"""
        try:
            # 尝试获取topic similarity
            topic_similarities = self.topic_model.topic_embeddings_
            if topic_similarities is not None:
                from sklearn.metrics.pairwise import cosine_similarity

                topic_embedding = topic_similarities[topic_id + 1].reshape(1, -1)
                similarities = cosine_similarity(topic_embedding, topic_similarities)[0]

                similar_topics = []
                for i, sim in enumerate(similarities):
                    if i - 1 != topic_id and i - 1 != -1:
                        similar_topics.append((i - 1, float(sim)))

                similar_topics.sort(key=lambda x: x[1], reverse=True)
                return similar_topics[:top_n]
        except Exception as e:
            logging.warning(f"查找相似主题失败: {e}")

        return []

    def get_topic_examples(self, topic_id: int, n: int = 5) -> List[str]:
        """获取主题示例文档"""
        if self.documents_with_topics is None:
            return []

        topic_docs = self.documents_with_topics[
            self.documents_with_topics["topic"] == topic_id
        ]
        if len(topic_docs) == 0:
            return []

        examples = []
        for _, row in topic_docs.head(n).iterrows():
            text = str(row.get("title", "")) + " " + str(row.get("content", ""))
            examples.append(text[:100] + "..." if len(text) > 100 else text)

        return examples

    def visualize_topic(self, topic_id: int, output_path: Optional[Path] = None):
        """可视化单个主题"""
        try:
            fig = self.topic_model.visualize_barchart(topics=[topic_id])
            if output_path:
                fig.write_html(str(output_path))
                logging.info(f"已保存可视化到: {output_path}")
            return fig
        except Exception as e:
            logging.error(f"可视化失败: {e}")
            return None

    def export_topic_summary(self, output_path: Path):
        """导出主题摘要"""
        topic_info = self.get_topic_info()

        # 增强信息
        export_data = []
        for _, row in topic_info.iterrows():
            topic_id = int(row["Topic"])
            words = self.get_topic_words(topic_id, top_n=10)

            export_row = {
                "topic_id": topic_id,
                "count": int(row.get("Count", 0)),
                "name": row.get("Name", ""),
                "label": row.get("Label", ""),
                "top_words": " | ".join([w for w, s in words]),
            }
            export_data.append(export_row)

        df = pd.DataFrame(export_data)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logging.info(f"已导出主题摘要到: {output_path}")

        return df


def main():
    parser = argparse.ArgumentParser(
        description="主题模型推理器"
    )
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # 探索命令
    parser_explore = subparsers.add_parser("explore", help="探索训练好的模型")
    parser_explore.add_argument("model_dir", type=Path, help="模型目录")
    parser_explore.add_argument("--topic_id", type=int, help="查看特定主题")
    parser_explore.add_argument("--export", type=Path, help="导出摘要")

    # 预测命令
    parser_predict = subparsers.add_parser("predict", help="预测文本主题")
    parser_predict.add_argument("model_dir", type=Path, help="模型目录")
    parser_predict.add_argument("--text", type=str, help="单条文本")
    parser_predict.add_argument("--file", type=Path, help="文本文件（每行一条）")
    parser_predict.add_argument("--output", type=Path, help="输出文件")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if args.command == "explore":
        # 探索模式
        inferencer = TopicModelInferencer(args.model_dir)

        print("\n" + "=" * 80)
        print("主题模型概览")
        print("=" * 80)

        topic_info = inferencer.get_topic_info()
        print(f"\n总计发现 {len(topic_info)} 个主题（包含离群点）")

        if args.topic_id is not None:
            # 查看特定主题
            print(f"\n主题 {args.topic_id} 详情:")
            topic_data = inferencer.get_topic_info(args.topic_id)
            if len(topic_data) > 0:
                print(topic_data.iloc[0])

            print("\n主题词:")
            words = inferencer.get_topic_words(args.topic_id, top_n=10)
            for word, score in words:
                print(f"  {word} ({score:.4f})")

            print("\n示例文档:")
            examples = inferencer.get_topic_examples(args.topic_id, n=3)
            for i, ex in enumerate(examples, 1):
                print(f"  [{i}] {ex}")

        else:
            # 列出全部主题
            print("\n主题列表:")
            for _, row in topic_info[topic_info["Topic"] != -1].head(30).iterrows():
                label = row.get("Label", "")
                if not label:
                    words = inferencer.get_topic_words(int(row["Topic"]), top_n=5)
                    label = " | ".join([w for w, s in words])
                print(f"  主题{row['Topic']:3d}: {row['Count']:4d}篇 - {label}")

        if args.export:
            inferencer.export_topic_summary(args.export)

    elif args.command == "predict":
        # 预测模式
        inferencer = TopicModelInferencer(args.model_dir)

        if args.text:
            # 单条预测
            result = inferencer.predict_single(args.text)
            print("\n" + "=" * 80)
            print("预测结果")
            print("=" * 80)
            print(f"\n文本: {result['text']}")
            print(f"主题: {result['topic_id']}")
            if "topic_label" in result:
                print(f"标签: {result['topic_label']}")
            if "probability" in result:
                print(f"置信度: {result['probability']:.4f}")
            print(f"主题词: {' | '.join([w for w, s in result['topic_words']])}")

        elif args.file:
            # 批量预测
            with open(args.file, "r", encoding="utf-8") as f:
                texts = [line.strip() for line in f if line.strip()]

            print(f"从 {args.file} 加载 {len(texts)} 条文本")
            results = inferencer.predict_batch(texts)

            # 输出
            df = pd.DataFrame(results)
            print(df[["topic_id", "text"]].head(20))

            if args.output:
                df.to_csv(args.output, index=False, encoding="utf-8-sig")
                print(f"\n结果已保存到: {args.output}")

        else:
            print("请提供 --text 或 --file 参数")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
