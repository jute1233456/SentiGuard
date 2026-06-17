#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
高级THUCNews+BERTopic训练脚本 - 支持断点续训
特征：
- 分阶段保存检查点
- 支持停止/恢复训练
- 自动检测已完成阶段
- 固定训练50个主题
- 完整的日志记录
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import numpy as np

# 设置HF镜像
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 导入项目模块
sys.path.insert(0, str(Path(__file__).parent))
from hot_topic.data_source import THUCNewsLoader
from hot_topic.storage.csv_writer import write_csv

# 扩展中文停用词
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


class TrainingStage(Enum):
    """训练阶段枚举"""
    INITIALIZING = auto()
    DATA_DOWNLOAD = auto()
    PREPROCESSING = auto()
    EMBEDDING = auto()
    DIMENSIONALITY_REDUCTION = auto()
    CLUSTERING = auto()
    TOPIC_MODELING = auto()
    SAVING_MODEL = auto()
    VISUALIZATION = auto()
    COMPLETED = auto()


@dataclass
class CheckpointMetadata:
    """检查点元数据"""
    stage: TrainingStage
    stage_completed: bool
    timestamp: str
    sample_size: int
    n_topics: int
    embedding_model: str
    min_topic_size: int

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.name,
            "stage_completed": self.stage_completed,
            "timestamp": self.timestamp,
            "sample_size": self.sample_size,
            "n_topics": self.n_topics,
            "embedding_model": self.embedding_model,
            "min_topic_size": self.min_topic_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CheckpointMetadata:
        return cls(
            stage=TrainingStage[data["stage"]],
            stage_completed=data["stage_completed"],
            timestamp=data["timestamp"],
            sample_size=data["sample_size"],
            n_topics=data["n_topics"],
            embedding_model=data["embedding_model"],
            min_topic_size=data["min_topic_size"],
        )


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.metadata_path = checkpoint_dir / "metadata.json"
        self.data_checkpoint = checkpoint_dir / "data_checkpoint.pkl"
        self.preprocessed_checkpoint = checkpoint_dir / "preprocessed_checkpoint.pkl"
        self.embeddings_checkpoint = checkpoint_dir / "embeddings_checkpoint.npy"
        self.umap_checkpoint = checkpoint_dir / "umap_checkpoint.pkl"
        self.model_checkpoint = checkpoint_dir / "bertopic_checkpoint"

    def ensure_dir(self):
        """确保检查点目录存在"""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_metadata(self, metadata: CheckpointMetadata):
        """保存元数据"""
        self.ensure_dir()
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, ensure_ascii=False, indent=2)

    def load_metadata(self) -> Optional[CheckpointMetadata]:
        """加载元数据"""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    return CheckpointMetadata.from_dict(json.load(f))
            except Exception as e:
                logging.warning(f"无法加载元数据: {e}")
        return None

    def save_data(self, df: pd.DataFrame):
        """保存数据检查点"""
        self.ensure_dir()
        df.to_pickle(self.data_checkpoint)
        logging.info(f"数据检查点已保存: {self.data_checkpoint}")

    def load_data(self) -> Optional[pd.DataFrame]:
        """加载数据检查点"""
        if self.data_checkpoint.exists():
            try:
                return pd.read_pickle(self.data_checkpoint)
            except Exception as e:
                logging.warning(f"无法加载数据检查点: {e}")
        return None

    def save_preprocessed(self, texts: List[str], raw_texts: List[str]):
        """保存预处理检查点"""
        self.ensure_dir()
        with open(self.preprocessed_checkpoint, "wb") as f:
            pickle.dump({"texts": texts, "raw_texts": raw_texts}, f)
        logging.info(f"预处理检查点已保存: {self.preprocessed_checkpoint}")

    def load_preprocessed(self) -> Optional[Dict]:
        """加载预处理检查点"""
        if self.preprocessed_checkpoint.exists():
            try:
                with open(self.preprocessed_checkpoint, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logging.warning(f"无法加载预处理检查点: {e}")
        return None

    def save_embeddings(self, embeddings: np.ndarray):
        """保存嵌入检查点"""
        self.ensure_dir()
        np.save(self.embeddings_checkpoint, embeddings)
        logging.info(f"嵌入检查点已保存: {self.embeddings_checkpoint}")

    def load_embeddings(self) -> Optional[np.ndarray]:
        """加载嵌入检查点"""
        if self.embeddings_checkpoint.exists():
            try:
                return np.load(self.embeddings_checkpoint)
            except Exception as e:
                logging.warning(f"无法加载嵌入检查点: {e}")
        return None

    def save_umap(self, umap_embeddings: np.ndarray):
        """保存UMAP检查点"""
        self.ensure_dir()
        np.save(self.checkpoint_dir / "umap_embeddings.npy", umap_embeddings)
        logging.info(f"UMAP检查点已保存")

    def load_umap(self) -> Optional[np.ndarray]:
        """加载UMAP检查点"""
        umap_path = self.checkpoint_dir / "umap_embeddings.npy"
        if umap_path.exists():
            try:
                return np.load(umap_path)
            except Exception as e:
                logging.warning(f"无法加载UMAP检查点: {e}")
        return None

    def backup_checkpoints(self):
        """备份当前检查点"""
        backup_dir = self.checkpoint_dir / f"backup_{int(time.time())}"
        if self.checkpoint_dir.exists():
            shutil.copytree(self.checkpoint_dir, backup_dir)
            logging.info(f"检查点已备份到: {backup_dir}")


class AdvancedTHUCNewsTrainer:
    """高级THUCNews+BERTopic训练器 - 支持断点续训"""

    def __init__(
        self,
        output_dir: Path,
        sample_size: int = 50000,
        n_topics: int = 50,
        embedding_model: str = "BAAI/bge-large-zh-v1.5",
        min_topic_size: int = 30,
        resume: bool = True,
    ):
        self.output_dir = output_dir
        self.checkpoint_dir = output_dir / "checkpoints"
        self.sample_size = sample_size
        self.n_topics = n_topics
        self.embedding_model = embedding_model
        self.min_topic_size = min_topic_size
        self.resume = resume

        self.checkpoint_manager = CheckpointManager(self.checkpoint_dir)
        self.current_stage = TrainingStage.INITIALIZING

        # 数据存储
        self.df = None
        self.raw_texts = None
        self.texts = None
        self.embeddings = None
        self.umap_embeddings = None
        self.topic_model = None
        self.topics = None
        self.probabilities = None

        # 设置日志
        self._setup_logging()

    def _setup_logging(self):
        """设置日志"""
        log_file = self.output_dir / "training.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _get_metadata(self, stage: TrainingStage, completed: bool = True) -> CheckpointMetadata:
        """获取元数据对象"""
        return CheckpointMetadata(
            stage=stage,
            stage_completed=completed,
            timestamp=datetime.now().isoformat(),
            sample_size=self.sample_size,
            n_topics=self.n_topics,
            embedding_model=self.embedding_model,
            min_topic_size=self.min_topic_size,
        )

    def _check_resume(self) -> Optional[TrainingStage]:
        """检查是否可以恢复，返回上一次完成的阶段"""
        if not self.resume:
            return None

        metadata = self.checkpoint_manager.load_metadata()
        if metadata:
            logging.info("=" * 80)
            logging.info(f"发现之前的训练记录！")
            logging.info(f"上次训练时间: {metadata.timestamp}")
            logging.info(f"上次完成阶段: {metadata.stage.name}")
            logging.info(f"样本量: {metadata.sample_size}")
            logging.info(f"主题数: {metadata.n_topics}")
            logging.info("=" * 80)

            # 验证参数一致性
            if (metadata.sample_size != self.sample_size or
                metadata.n_topics != self.n_topics or
                metadata.embedding_model != self.embedding_model):
                logging.warning("警告：当前参数与之前训练不一致！")
                logging.warning(f"之前: 样本={metadata.sample_size}, 主题={metadata.n_topics}, 模型={metadata.embedding_model}")
                logging.warning(f"当前: 样本={self.sample_size}, 主题={self.n_topics}, 模型={self.embedding_model}")

            return metadata.stage
        return None

    def run(self):
        """运行完整训练流程"""
        logging.info("=" * 80)
        logging.info("高级THUCNews+BERTopic训练启动")
        logging.info(f"输出目录: {self.output_dir}")
        logging.info(f"样本量: {self.sample_size if self.sample_size > 0 else '全量'}")
        logging.info(f"主题数: {self.n_topics}")
        logging.info(f"嵌入模型: {self.embedding_model}")
        logging.info("=" * 80)

        # 检查恢复点
        last_completed_stage = self._check_resume()

        try:
            # 阶段1: 数据下载
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.DATA_DOWNLOAD.value:
                self._stage_data_download()
            else:
                logging.info("跳过数据下载阶段（已完成）")
                self.df = self.checkpoint_manager.load_data()
                if self.df is None:
                    logging.warning("数据检查点损坏，重新下载")
                    self._stage_data_download()

            # 阶段2: 预处理
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.PREPROCESSING.value:
                self._stage_preprocessing()
            else:
                logging.info("跳预处理段（已完成）")
                preprocessed = self.checkpoint_manager.load_preprocessed()
                if preprocessed:
                    self.texts = preprocessed["texts"]
                    self.raw_texts = preprocessed["raw_texts"]
                else:
                    logging.warning("预处理检查点损坏，重新处理")
                    self._stage_preprocessing()

            # 阶段3: 嵌入
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.EMBEDDING.value:
                self._stage_embedding()
            else:
                logging.info("跳过嵌入阶段（已完成）")
                self.embeddings = self.checkpoint_manager.load_embeddings()
                if self.embeddings is None:
                    logging.warning("嵌入检查点损坏，重新生成")
                    self._stage_embedding()

            # 阶段4-6: BERTopic建模（包含降维、聚类、主题建模）
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.TOPIC_MODELING.value:
                self._stage_topic_modeling()
            else:
                logging.info("跳过主题建模阶段（已完成）")
                try:
                    from bertopic import BERTopic
                    model_path = self.checkpoint_manager.model_checkpoint
                    if model_path.exists():
                        self.topic_model = BERTopic.load(model_path)
                        logging.info("已加载保存的模型")
                    else:
                        self._stage_topic_modeling()
                except Exception as e:
                    logging.warning(f"加载模型失败: {e}，重新训练")
                    self._stage_topic_modeling()

            # 阶段7: 保存模型
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.SAVING_MODEL.value:
                self._stage_save_model()
            else:
                logging.info("跳过模型保存阶段（已完成）")

            # 阶段8: 可视化
            if last_completed_stage is None or last_completed_stage.value < TrainingStage.VISUALIZATION.value:
                self._stage_visualization()
            else:
                logging.info("跳过可视化阶段（已完成）")

            # 完成
            self._finalize()

        except KeyboardInterrupt:
            logging.warning("训练被用户中断！")
            logging.info(f"当前阶段: {self.current_stage.name}")
            logging.info("下次运行时可以恢复训练")
            return 1
        except Exception as e:
            logging.error(f"训练出错: {e}", exc_info=True)
            return 1

        return 0

    def _stage_data_download(self):
        """阶段1: 数据下载"""
        self.current_stage = TrainingStage.DATA_DOWNLOAD
        logging.info("\n" + "=" * 80)
        logging.info("阶段1/8: 数据下载")
        logging.info("=" * 80)

        start_time = time.time()

        # 下载数据
        loader = THUCNewsLoader()
        sample_size = None if self.sample_size == 0 else self.sample_size
        self.df = loader.to_dataframe(sample_size=sample_size, streaming=False)

        logging.info(f"下载了 {len(self.df)} 条记录")

        # 保存原始数据
        raw_data_dir = self.output_dir / "data"
        raw_data_dir.mkdir(parents=True, exist_ok=True)
        write_csv(self.df, raw_data_dir / "raw_data.csv")

        # 保存检查点
        self.checkpoint_manager.save_data(self.df)
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.DATA_DOWNLOAD, True)
        )

        logging.info(f"数据下载完成，耗时: {time.time() - start_time:.1f}秒")

    def _stage_preprocessing(self):
        """阶段2: 预处理"""
        self.current_stage = TrainingStage.PREPROCESSING
        logging.info("\n" + "=" * 80)
        logging.info("阶段2/8: 文本预处理")
        logging.info("=" * 80)

        start_time = time.time()

        # 合并标题和内容
        self.raw_texts = (self.df["title"] + " " + self.df["content"]).tolist()

        # 分词和清理
        self.texts = self._preprocess_texts(self.raw_texts)

        logging.info(f"预处理完成，获得 {len(self.texts)} 条有效文本")

        # 保存检查点
        self.checkpoint_manager.save_preprocessed(self.texts, self.raw_texts)
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.PREPROCESSING, True)
        )

        logging.info(f"预处理完成，耗时: {time.time() - start_time:.1f}秒")

    def _preprocess_texts(self, raw_texts: List[str]) -> List[str]:
        """预处理文本"""
        try:
            import jieba
        except ImportError:
            logging.error("请先安装jieba: pip install jieba")
            raise

        processed = []
        for i, text in enumerate(raw_texts):
            if i % 5000 == 0:
                logging.info(f"处理进度: {i}/{len(raw_texts)}")

            if not isinstance(text, str):
                text = str(text)

            # 基本清理
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

            tokenized = " ".join(filtered)
            if len(tokenized) >= 10:
                processed.append(tokenized)

        return processed

    def _stage_embedding(self):
        """阶段3: 文本嵌入"""
        self.current_stage = TrainingStage.EMBEDDING
        logging.info("\n" + "=" * 80)
        logging.info("阶段3/8: 文本嵌入")
        logging.info("=" * 80)

        start_time = time.time()

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logging.error("请先安装sentence-transformers")
            raise

        logging.info(f"加载嵌入模型: {self.embedding_model}")
        model = SentenceTransformer(self.embedding_model)

        logging.info(f"开始编码 {len(self.texts)} 条文本...")
        self.embeddings = model.encode(
            self.texts,
            show_progress_bar=True,
            batch_size=32,
            convert_to_numpy=True,
        )

        logging.info(f"嵌入完成，shape: {self.embeddings.shape}")

        # 保存检查点
        self.checkpoint_manager.save_embeddings(self.embeddings)
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.EMBEDDING, True)
        )

        logging.info(f"嵌入完成，耗时: {time.time() - start_time:.1f}秒")

    def _stage_topic_modeling(self):
        """阶段4-6: 完整主题建模"""
        self.current_stage = TrainingStage.TOPIC_MODELING
        logging.info("\n" + "=" * 80)
        logging.info("阶段4-6/8: BERTopic主题建模")
        logging.info("=" * 80)

        start_time = time.time()

        try:
            from bertopic import BERTopic
            from bertopic.representation import KeyBERTInspired, MaximalMarginalRelevance
            from umap import UMAP
            from hdbscan import HDBSCAN
            from sentence_transformers import SentenceTransformer
            from sklearn.feature_extraction.text import CountVectorizer
        except ImportError as e:
            logging.error("请安装所需包: pip install bertopic umap-learn hdbscan")
            raise

        logging.info("初始化模型组件...")

        # 重新加载嵌入模型（用于BERTopic内部）
        embedding_model_obj = SentenceTransformer(self.embedding_model)

        # UMAP
        umap_model = UMAP(
            n_neighbors=15,
            n_components=5,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
            verbose=True,
        )

        # HDBSCAN
        hdbscan_model = HDBSCAN(
            min_cluster_size=self.min_topic_size,
            min_samples=max(5, self.min_topic_size // 3),
            metric="euclidean",
            prediction_data=True,
            cluster_selection_method="eom",
        )

        # Vectorizer
        vectorizer_model = CountVectorizer(
            token_pattern=r"(?u)\S\S+",
            ngram_range=(1, 2),
            min_df=2,
        )

        # Representation
        representation_model = {
            "KeyBERT": KeyBERTInspired(),
            "MMR": MaximalMarginalRelevance(diversity=0.3),
        }

        logging.info(f"初始化BERTopic，目标主题数: {self.n_topics}")

        # 构建和训练模型
        self.topic_model = BERTopic(
            embedding_model=embedding_model_obj,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            representation_model=representation_model,
            nr_topics=self.n_topics,
            top_n_words=10,
            n_gram_range=(1, 2),
            calculate_probabilities=True,
            verbose=True,
        )

        logging.info("开始训练模型...")
        self.topics, self.probabilities = self.topic_model.fit_transform(
            self.texts,
            embeddings=self.embeddings,
        )

        # 输出主题信息
        topic_info = self.topic_model.get_topic_info()
        logging.info(f"发现 {len(topic_info)} 个主题（包含离群点）")
        logging.info(f"离群点数量: {(pd.Series(self.topics) == -1).sum()}")

        # 保存检查点
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.TOPIC_MODELING, True)
        )

        logging.info(f"主题建模完成，耗时: {time.time() - start_time:.1f}秒")

    def _stage_save_model(self):
        """阶段7: 保存模型"""
        self.current_stage = TrainingStage.SAVING_MODEL
        logging.info("\n" + "=" * 80)
        logging.info("阶段7/8: 保存模型和结果")
        logging.info("=" * 80)

        start_time = time.time()

        model_dir = self.output_dir / "bertopic_model"
        logging.info(f"保存模型到: {model_dir}")
        self.topic_model.save(model_dir, serialization="safetensors", save_embedding_model=True)

        # 同时保存到检查点
        if not self.checkpoint_manager.model_checkpoint.exists():
            shutil.copytree(model_dir, self.checkpoint_manager.model_checkpoint)

        # 保存主题信息
        topic_info = self.topic_model.get_topic_info()
        topic_info["Label"] = topic_info.apply(
            lambda row: " | ".join([w for w, _ in self.topic_model.get_topic(row["Topic"])[:5]])
            if row["Topic"] != -1 else "Outlier",
            axis=1,
        )
        topic_info.to_csv(self.output_dir / "topic_info.csv", index=False, encoding="utf-8-sig")
        logging.info("主题信息已保存")

        # 保存文档-主题分配
        docs_with_topics = self.df.iloc[:len(self.topics)].copy()
        docs_with_topics["topic"] = self.topics
        docs_with_topics.to_csv(self.output_dir / "documents_with_topics.csv", index=False, encoding="utf-8-sig")
        logging.info("文档-主题分配已保存")

        # 更新检查点元数据
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.SAVING_MODEL, True)
        )

        logging.info(f"模型保存完成，耗时: {time.time() - start_time:.1f}秒")

    def _stage_visualization(self):
        """阶段8: 可视化"""
        self.current_stage = TrainingStage.VISUALIZATION
        logging.info("\n" + "=" * 80)
        logging.info("阶段8/8: 生成可视化")
        logging.info("=" * 80)

        start_time = time.time()

        viz_dir = self.output_dir / "visualizations"
        viz_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 2D主题图
            logging.info("生成2D主题图...")
            fig = self.topic_model.visualize_topics(width=1200, height=900)
            fig.write_html(str(viz_dir / "topics_2d.html"))

            # 2. 条形图
            logging.info("生成主题条形图...")
            fig = self.topic_model.visualize_barchart(top_n_topics=20)
            fig.write_html(str(viz_dir / "topic_barchart.html"))

            # 3. 热力图
            logging.info("生成主题热力图...")
            fig = self.topic_model.visualize_heatmap(top_n_topics=30)
            fig.write_html(str(viz_dir / "topic_heatmap.html"))

            # 4. 层次结构
            logging.info("生成主题层次结构...")
            try:
                hierarchical_topics = self.topic_model.hierarchical_topics()
                fig = self.topic_model.visualize_hierarchy(hierarchical_topics=hierarchical_topics)
                fig.write_html(str(viz_dir / "topic_hierarchy.html"))
            except Exception as e:
                logging.warning(f"层次结构可视化失败: {e}")

            logging.info("可视化生成完成")

        except Exception as e:
            logging.warning(f"部分可视化生成失败: {e}")

        # 更新检查点
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.VISUALIZATION, True)
        )

        logging.info(f"可视化完成，耗时: {time.time() - start_time:.1f}秒")

    def _finalize(self):
        """完成训练"""
        self.current_stage = TrainingStage.COMPLETED

        logging.info("\n" + "=" * 80)
        logging.info("🎉 训练完成！")
        logging.info("=" * 80)

        # 输出最终主题摘要
        topic_info = self.topic_model.get_topic_info()
        logging.info(f"\nTop 20主题摘要:")
        for _, row in topic_info[topic_info["Topic"] != -1].head(20).iterrows():
            topic_words = [w for w, _ in self.topic_model.get_topic(row["Topic"])[:5]]
            logging.info(f"  主题{row['Topic']:3d}: {row['Count']:4d}篇 - {' | '.join(topic_words)}")

        # 最终检查点
        self.checkpoint_manager.save_metadata(
            self._get_metadata(TrainingStage.COMPLETED, True)
        )

        logging.info(f"\n输出位置: {self.output_dir.resolve()}")
        logging.info("查看 visualizations/topics_2d.html 开始探索主题！")


def main():
    parser = argparse.ArgumentParser(
        description="高级THUCNews+BERTopic训练脚本 - 支持断点续训"
    )

    # 数据参数
    parser.add_argument(
        "--sample",
        type=int,
        default=50000,
        help="样本量 (0=全量, 默认: 50000)"
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path("data/thucnews_advanced"),
        help="输出目录 (默认: data/thucnews_advanced)"
    )

    # 模型参数
    parser.add_argument(
        "--n_topics",
        type=int,
        default=50,
        help="主题数量 (默认: 50)"
    )
    parser.add_argument(
        "--embedding_model",
        type=str,
        default="BAAI/bge-large-zh-v1.5",
        help="嵌入模型 (默认: BAAI/bge-large-zh-v1.5)"
    )
    parser.add_argument(
        "--min_topic_size",
        type=int,
        default=30,
        help="最小主题大小 (默认: 30)"
    )

    # 控制参数
    parser.add_argument(
        "--no_resume",
        action="store_true",
        help="不恢复训练，从头开始"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="重置训练（清除所有检查点）"
    )

    args = parser.parse_args()

    # 处理重置
    checkpoint_dir = args.output_dir / "checkpoints"
    if args.reset and checkpoint_dir.exists():
        logging.info("重置训练，清除现有检查点...")
        backup_dir = checkpoint_dir.parent / f"checkpoints_backup_{int(time.time())}"
        shutil.move(checkpoint_dir, backup_dir)
        logging.info(f"已备份到: {backup_dir}")

    # 创建训练器
    trainer = AdvancedTHUCNewsTrainer(
        output_dir=args.output_dir,
        sample_size=args.sample,
        n_topics=args.n_topics,
        embedding_model=args.embedding_model,
        min_topic_size=args.min_topic_size,
        resume=not args.no_resume,
    )

    # 运行训练
    return trainer.run()


if __name__ == "__main__":
    sys.exit(main())
