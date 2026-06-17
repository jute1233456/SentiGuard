# -*- coding: utf-8 -*-
"""
THUCNews+BERTopic 主题模型训练器
提供简洁的Python API供其他代码调用

使用示例:

    from topic_model_trainer import TopicModelTrainer

    # 创建训练器
    trainer = TopicModelTrainer()

    # 使用预设配置（可选）
    trainer.apply_preset("medium")

    # 开始训练
    result = trainer.train()

    # 预测新文本
    topics = trainer.predict(["文本1", "文本2"])

    # 保存/加载模型
    trainer.save("path/to/model")
    trainer = TopicModelTrainer.load("path/to/model")
"""

from __future__ import annotations

import json
import logging
import pickle
import shutil
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
import numpy as np

# 设置HF镜像
import os
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 导入配置
import topic_model_config as config
from topic_model_config import (
    DATA_CONFIG,
    MODEL_CONFIG,
    UMAP_CONFIG,
    HDBSCAN_CONFIG,
    PREPROCESS_CONFIG,
    VIZ_CONFIG,
    EXTENDED_CHINESE_STOPWORDS,
    RANDOM_SEED,
    ENABLE_CHECKPOINT,
    DEFAULT_OUTPUT_DIR,
)


# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TopicModelTrainer")


class TrainingStage(Enum):
    """训练阶段"""
    INITIALIZED = auto()
    DATA_LOADED = auto()
    PREPROCESSED = auto()
    EMBEDDED = auto()
    TOPIC_MODEL_READY = auto()
    SAVED = auto()
    COMPLETED = auto()


@dataclass
class TrainingResult:
    """训练结果"""
    success: bool
    output_dir: Path
    topic_model: Any
    topic_info: pd.DataFrame
    topics: np.ndarray
    probabilities: Optional[np.ndarray]
    n_topics: int
    n_documents: int
    training_time: float


@dataclass
class PredictionResult:
    """预测结果"""
    topic_id: int
    topic_words: List[Tuple[str, float]]
    topic_label: str
    probability: Optional[float]
    text: str


class TopicModelTrainer:
    """
    主题模型训练器 - 简洁的Python API

    使用示例:

        # 方式1: 从零开始训练
        trainer = TopicModelTrainer()
        trainer.apply_preset("medium")
        result = trainer.train()

        # 方式2: 加载已有模型
        trainer = TopicModelTrainer.load("path/to/model")
        topics = trainer.predict(["新闻文本1", "新闻文本2"])

        # 方式3: 修改配置
        trainer = TopicModelTrainer()
        trainer.set_config("n_topics", 80)
        trainer.set_config("sample_size", 100000)
        trainer.train()
    """

    def __init__(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        use_checkpoint: bool = True,
    ):
        """
        初始化训练器

        Args:
            output_dir: 输出目录，默认为 data/thucnews_model
            use_checkpoint: 是否启用断点续训
        """
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.use_checkpoint = use_checkpoint and ENABLE_CHECKPOINT

        # 状态
        self.stage = TrainingStage.INITIALIZED
        self.topic_model = None
        self.raw_df = None
        self.raw_texts = None
        self.processed_texts = None
        self.embeddings = None
        self.topics = None
        self.probabilities = None

        # 检查点目录
        self._checkpoint_dir = self.output_dir / "checkpoints"

        # 确保目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化日志文件
        self._setup_log_file()

    def _setup_log_file(self):
        """设置日志文件"""
        log_file = self.output_dir / "training.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(file_handler)

    # ==========================================
    # 配置管理
    # ==========================================

    def apply_preset(self, preset_name: str):
        """
        应用预设配置

        Args:
            preset_name: 预设名称: test, small, medium, large, full
        """
        config.apply_preset(preset_name)
        logger.info(f"已应用预设: {preset_name}")

    def set_config(self, key: str, value: Any, config_type: str = "model"):
        """
        修改单个配置

        Args:
            key: 配置键名
            value: 配置值
            config_type: 配置类型: data, model, umap, hdbscan, preprocess, viz
        """
        config_maps = {
            "data": DATA_CONFIG,
            "model": MODEL_CONFIG,
            "umap": UMAP_CONFIG,
            "hdbscan": HDBSCAN_CONFIG,
            "preprocess": PREPROCESS_CONFIG,
            "viz": VIZ_CONFIG,
        }

        if config_type not in config_maps:
            raise ValueError(f"未知配置类型: {config_type}，可用: {list(config_maps.keys())}")

        config_maps[config_type][key] = value
        logger.info(f"已设置配置: {config_type}.{key} = {value}")

    def print_config(self):
        """打印当前配置"""
        config.print_config()

    # ==========================================
    # 检查点管理
    # ==========================================

    def _save_checkpoint_metadata(self, stage: TrainingStage):
        """保存检查点元数据"""
        if not self.use_checkpoint:
            return

        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "stage": stage.name,
            "timestamp": time.time(),
            "config": {
                "data": DATA_CONFIG.copy(),
                "model": MODEL_CONFIG.copy(),
            }
        }
        with open(self._checkpoint_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _load_checkpoint_metadata(self) -> Optional[Dict]:
        """加载检查点元数据"""
        if not self.use_checkpoint:
            return None

        metadata_path = self._checkpoint_dir / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _check_can_resume(self) -> Optional[TrainingStage]:
        """检查是否可以恢复训练"""
        if not self.use_checkpoint:
            return None

        metadata = self._load_checkpoint_metadata()
        if metadata:
            stage_name = metadata.get("stage", "INITIALIZED")
            try:
                stage = TrainingStage[stage_name]
                logger.info(f"发现检查点，上次完成: {stage.name}")
                return stage
            except KeyError:
                logger.warning(f"未知阶段: {stage_name}")

        return None

    # ==========================================
    # 训练流程
    # ==========================================

    def train(self, force_restart: bool = False) -> TrainingResult:
        """
        开始训练

        Args:
            force_restart: 是否强制从头开始，忽略检查点

        Returns:
            TrainingResult: 训练结果
        """
        start_time = time.time()
        logger.info("=" * 80)
        logger.info("主题模型训练开始")
        logger.info("=" * 80)

        # 检查恢复
        last_stage = None
        if not force_restart:
            last_stage = self._check_can_resume()

        # 阶段1: 加载数据
        if not last_stage or last_stage.value < TrainingStage.DATA_LOADED.value:
            self._load_data()
            self._save_checkpoint_metadata(TrainingStage.DATA_LOADED)
        else:
            self._load_data_from_checkpoint()

        # 阶段2: 预处理
        if not last_stage or last_stage.value < TrainingStage.PREPROCESSED.value:
            self._preprocess()
            self._save_checkpoint_metadata(TrainingStage.PREPROCESSED)
        else:
            self._load_preprocessed_from_checkpoint()

        # 阶段3: 嵌入
        if not last_stage or last_stage.value < TrainingStage.EMBEDDED.value:
            self._embed()
            self._save_checkpoint_metadata(TrainingStage.EMBEDDED)
        else:
            self._load_embeddings_from_checkpoint()

        # 阶段4: 主题建模
        if not last_stage or last_stage.value < TrainingStage.TOPIC_MODEL_READY.value:
            self._build_topic_model()
            self._save_checkpoint_metadata(TrainingStage.TOPIC_MODEL_READY)
        else:
            self._load_topic_model_from_checkpoint()

        # 阶段5: 保存
        self._save_model_and_data()
        self._save_checkpoint_metadata(TrainingStage.SAVED)

        # 阶段6: 可视化
        if VIZ_CONFIG["enable_viz"]:
            self._generate_visualizations()

        # 完成
        self._save_checkpoint_metadata(TrainingStage.COMPLETED)
        self.stage = TrainingStage.COMPLETED

        training_time = time.time() - start_time

        # 构建结果
        result = TrainingResult(
            success=True,
            output_dir=self.output_dir,
            topic_model=self.topic_model,
            topic_info=self.get_topic_info(),
            topics=self.topics,
            probabilities=self.probabilities,
            n_topics=len(self.get_topic_info()),
            n_documents=len(self.processed_texts),
            training_time=training_time,
        )

        logger.info("\n" + "=" * 80)
        logger.info(f"🎉 训练完成！耗时: {training_time:.1f}秒")
        logger.info(f"   文档数: {result.n_documents}")
        logger.info(f"   主题数: {result.n_topics}")
        logger.info(f"   输出目录: {self.output_dir}")
        logger.info("=" * 80)

        return result

    # ==========================================
    # 内部训练步骤
    # ==========================================

    def _load_data(self):
        """加载THUCNews数据"""
        logger.info("步骤 1/6: 加载数据")

        sample_size = DATA_CONFIG["sample_size"]

        # 使用hot_topic模块的THUCNewsLoader
        from hot_topic.data_source import THUCNewsLoader

        loader = THUCNewsLoader(
            hf_repo=DATA_CONFIG["hf_dataset"],
            split=DATA_CONFIG["split"],
        )
        self.raw_df = loader.to_dataframe(
            sample_size=sample_size if sample_size > 0 else None,
            seed=RANDOM_SEED,
            streaming=DATA_CONFIG["streaming"],
        )

        self.raw_texts = (self.raw_df["title"] + " " + self.raw_df["content"]).tolist()
        logger.info(f"已加载 {len(self.raw_df)} 条数据")

        # 保存检查点
        if self.use_checkpoint:
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
            self.raw_df.to_pickle(self._checkpoint_dir / "data.pkl")

    def _load_data_from_checkpoint(self):
        """从检查点加载数据"""
        logger.info("从检查点加载数据")
        data_path = self._checkpoint_dir / "data.pkl"
        if data_path.exists():
            self.raw_df = pd.read_pickle(data_path)
            self.raw_texts = (self.raw_df["title"] + " " + self.raw_df["content"]).tolist()
            logger.info(f"已加载 {len(self.raw_df)} 条数据")
        else:
            logger.warning("检查点不存在，重新加载")
            self._load_data()

    def _preprocess(self):
        """预处理文本"""
        logger.info("步骤 2/6: 文本预处理")

        try:
            import jieba
        except ImportError:
            raise ImportError("请安装jieba: pip install jieba")

        stopwords = EXTENDED_CHINESE_STOPWORDS if PREPROCESS_CONFIG["use_extended_stopwords"] else set()

        processed = []
        for i, text in enumerate(self.raw_texts):
            if i % 5000 == 0:
                logger.info(f"  预处理进度: {i}/{len(self.raw_texts)}")

            tokenized = self._preprocess_single_text(text, stopwords, jieba)
            if len(tokenized) >= PREPROCESS_CONFIG["min_text_length"]:
                processed.append(tokenized)

        self.processed_texts = processed
        logger.info(f"预处理完成，有效文本: {len(processed)}")

        # 保存检查点
        if self.use_checkpoint:
            with open(self._checkpoint_dir / "processed.pkl", "wb") as f:
                pickle.dump(processed, f)

    def _load_preprocessed_from_checkpoint(self):
        """从检查点加载预处理结果"""
        logger.info("从检查点加载预处理结果")
        processed_path = self._checkpoint_dir / "processed.pkl"
        if processed_path.exists():
            with open(processed_path, "rb") as f:
                self.processed_texts = pickle.load(f)
            logger.info(f"已加载 {len(self.processed_texts)} 条预处理文本")
        else:
            logger.warning("检查点不存在，重新预处理")
            self._preprocess()

    def _embed(self):
        """生成嵌入向量"""
        logger.info("步骤 3/6: 文本嵌入")

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("请安装sentence-transformers")

        model_name = MODEL_CONFIG["embedding_model"]
        logger.info(f"加载嵌入模型: {model_name}")

        model = SentenceTransformer(model_name)
        logger.info(f"开始编码 {len(self.processed_texts)} 条文本")

        self.embeddings = model.encode(
            self.processed_texts,
            show_progress_bar=True,
            batch_size=32,
            convert_to_numpy=True,
        )

        logger.info(f"嵌入完成，shape: {self.embeddings.shape}")

        # 保存检查点
        if self.use_checkpoint:
            np.save(self._checkpoint_dir / "embeddings.npy", self.embeddings)

    def _load_embeddings_from_checkpoint(self):
        """从检查点加载嵌入"""
        logger.info("从检查点加载嵌入")
        embed_path = self._checkpoint_dir / "embeddings.npy"
        if embed_path.exists():
            self.embeddings = np.load(embed_path)
            logger.info(f"已加载嵌入，shape: {self.embeddings.shape}")
        else:
            logger.warning("检查点不存在，重新嵌入")
            self._embed()

    def _build_topic_model(self):
        """构建BERTopic模型"""
        logger.info("步骤 4/6: 主题建模")

        try:
            from bertopic import BERTopic
            from bertopic.representation import KeyBERTInspired, MaximalMarginalRelevance
            from umap import UMAP
            from hdbscan import HDBSCAN
            from sentence_transformers import SentenceTransformer
            from sklearn.feature_extraction.text import CountVectorizer
        except ImportError as e:
            raise ImportError("请安装所需包: bertopic umap-learn hdbscan")

        # 初始化组件
        logger.info("初始化模型组件")

        embedding_model = SentenceTransformer(MODEL_CONFIG["embedding_model"])

        umap_model = UMAP(
            n_neighbors=UMAP_CONFIG["n_neighbors"],
            n_components=UMAP_CONFIG["n_components"],
            min_dist=UMAP_CONFIG["min_dist"],
            metric=UMAP_CONFIG["metric"],
            random_state=RANDOM_SEED,
            verbose=True,
        )

        min_samples = HDBSCAN_CONFIG["min_samples"]
        if min_samples is None:
            min_samples = max(5, MODEL_CONFIG["min_topic_size"] // 3)

        hdbscan_model = HDBSCAN(
            min_cluster_size=MODEL_CONFIG["min_topic_size"],
            min_samples=min_samples,
            metric=HDBSCAN_CONFIG["metric"],
            prediction_data=True,
            cluster_selection_method=HDBSCAN_CONFIG["cluster_selection_method"],
        )

        ngram_range = PREPROCESS_CONFIG["ngram_range"]
        vectorizer_model = CountVectorizer(
            token_pattern=r"(?u)\S\S+",
            ngram_range=ngram_range,
            min_df=2,
        )

        representation_model = {
            "KeyBERT": KeyBERTInspired(),
            "MMR": MaximalMarginalRelevance(diversity=0.3),
        }

        # 构建BERTopic
        logger.info(f"构建BERTopic，目标主题数: {MODEL_CONFIG['n_topics']}")

        self.topic_model = BERTopic(
            embedding_model=embedding_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            representation_model=representation_model,
            nr_topics=MODEL_CONFIG["n_topics"],
            top_n_words=10,
            n_gram_range=ngram_range,
            calculate_probabilities=True,
            verbose=True,
        )

        # 训练
        logger.info("开始训练...")
        self.topics, self.probabilities = self.topic_model.fit_transform(
            self.processed_texts,
            embeddings=self.embeddings,
        )

        topic_info = self.topic_model.get_topic_info()
        logger.info(f"发现 {len(topic_info)} 个主题（包含离群点）")

    def _load_topic_model_from_checkpoint(self):
        """从检查点加载模型"""
        logger.info("从检查点加载主题模型")
        try:
            from bertopic import BERTopic
        except ImportError:
            raise ImportError("请安装bertopic")

        model_path = self._checkpoint_dir / "bertopic_model"
        if model_path.exists():
            self.topic_model = BERTopic.load(model_path)
            logger.info("主题模型加载成功")

            # 同时也需要预处理文本和嵌入
            if self.processed_texts is None:
                self._load_preprocessed_from_checkpoint()
            if self.embeddings is None:
                self._load_embeddings_from_checkpoint()
        else:
            logger.warning("检查点不存在，重新建模")
            self._build_topic_model()

    def _save_model_and_data(self):
        """保存模型和数据"""
        logger.info("步骤 5/6: 保存模型和数据")

        # 保存模型
        model_dir = self.output_dir / "bertopic_model"
        self.topic_model.save(model_dir, serialization="safetensors", save_embedding_model=True)
        logger.info(f"模型已保存: {model_dir}")

        # 保存主题信息
        topic_info = self.get_topic_info()
        topic_info.to_csv(self.output_dir / "topic_info.csv", index=False, encoding="utf-8-sig")
        logger.info("主题信息已保存")

        # 保存文档-主题分配
        if self.raw_df is not None:
            docs_with_topics = self.raw_df.iloc[:len(self.topics)].copy()
            docs_with_topics["topic"] = self.topics
            docs_with_topics.to_csv(self.output_dir / "documents_with_topics.csv", index=False, encoding="utf-8-sig")
            logger.info("文档-主题分配已保存")

        # 同时保存到检查点
        if self.use_checkpoint:
            ckpt_model_dir = self._checkpoint_dir / "bertopic_model"
            if not ckpt_model_dir.exists():
                shutil.copytree(model_dir, ckpt_model_dir)

    def _generate_visualizations(self):
        """生成可视化"""
        logger.info("步骤 6/6: 生成可视化")

        viz_dir = self.output_dir / "visualizations"
        viz_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 2D主题图
            fig = self.topic_model.visualize_topics(
                width=VIZ_CONFIG["topics_2d_width"],
                height=VIZ_CONFIG["topics_2d_height"],
            )
            fig.write_html(str(viz_dir / "topics_2d.html"))
            logger.info("  2D主题图已生成")
        except Exception as e:
            logger.warning(f"  2D主题图生成失败: {e}")

        try:
            # 条形图
            fig = self.topic_model.visualize_barchart(top_n_topics=VIZ_CONFIG["barchart_top_n"])
            fig.write_html(str(viz_dir / "topic_barchart.html"))
            logger.info("  主题条形图已生成")
        except Exception as e:
            logger.warning(f"  条形图生成失败: {e}")

        try:
            # 热力图
            fig = self.topic_model.visualize_heatmap(top_n_topics=VIZ_CONFIG["heatmap_top_n"])
            fig.write_html(str(viz_dir / "topic_heatmap.html"))
            logger.info("  主题热力图已生成")
        except Exception as e:
            logger.warning(f"  热力图生成失败: {e}")

        logger.info(f"可视化完成，保存在: {viz_dir}")

    # ==========================================
    # 预测和推理
    # ==========================================

    def predict(self, texts: Union[str, List[str]]) -> Union[PredictionResult, List[PredictionResult]]:
        """
        预测文本主题

        Args:
            texts: 单条文本或文本列表

        Returns:
            PredictionResult或其列表
        """
        if self.topic_model is None:
            raise ValueError("模型未训练或未加载，请先调用train()或load()")

        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else texts

        # 预处理
        try:
            import jieba
        except ImportError:
            raise ImportError("请安装jieba: pip install jieba")

        results = []
        for text in text_list:
            processed = self._preprocess_single_text(text, EXTENDED_CHINESE_STOPWORDS, jieba)
            topics, probs = self.topic_model.transform([processed])
            topic_id = int(topics[0])

            # 获取主题词
            topic_words = self._get_topic_words(topic_id, top_n=5)

            # 概率
            prob = None
            if probs is not None and len(probs) > 0:
                if hasattr(probs[0], "__len__") and topic_id < len(probs[0]):
                    prob = float(probs[0][topic_id])
                elif not hasattr(probs[0], "__len__"):
                    prob = float(probs[0])

            # 标签
            topic_label = " | ".join([w for w, s in topic_words])

            results.append(PredictionResult(
                topic_id=topic_id,
                topic_words=topic_words,
                topic_label=topic_label,
                probability=prob,
                text=text,
            ))

        return results[0] if is_single else results

    # ==========================================
    # 模型管理
    # ==========================================

    def save(self, save_dir: Optional[Union[str, Path]] = None):
        """
        保存模型

        Args:
            save_dir: 保存目录，None表示使用当前输出目录
        """
        if self.topic_model is None:
            raise ValueError("没有可保存的模型")

        save_path = Path(save_dir) if save_dir else self.output_dir
        model_dir = save_path / "bertopic_model"

        logger.info(f"保存模型到: {model_dir}")
        self.topic_model.save(model_dir, serialization="safetensors", save_embedding_model=True)

        # 保存主题信息
        topic_info = self.get_topic_info()
        topic_info.to_csv(save_path / "topic_info.csv", index=False, encoding="utf-8-sig")

        logger.info("模型保存成功")

    @classmethod
    def load(cls, model_dir: Union[str, Path]) -> "TopicModelTrainer":
        """
        加载已保存的模型

        Args:
            model_dir: 模型目录

        Returns:
            TopicModelTrainer: 加载后的训练器
        """
        try:
            from bertopic import BERTopic
        except ImportError:
            raise ImportError("请安装bertopic: pip install bertopic")

        model_dir = Path(model_dir)
        logger.info(f"从 {model_dir} 加载模型")

        # 创建训练器
        trainer = cls(output_dir=model_dir.parent, use_checkpoint=False)
        trainer.stage = TrainingStage.COMPLETED

        # 加载模型
        trainer.topic_model = BERTopic.load(model_dir / "bertopic_model")

        # 尝试加载数据
        data_path = model_dir.parent / "documents_with_topics.csv"
        if data_path.exists():
            trainer.raw_df = pd.read_csv(data_path, encoding="utf-8-sig")

        logger.info("模型加载成功")
        return trainer

    # ==========================================
    # 信息获取
    # ==========================================

    def get_topic_info(self) -> pd.DataFrame:
        """获取主题信息"""
        if self.topic_model is None:
            raise ValueError("模型未训练或未加载")

        topic_info = self.topic_model.get_topic_info().copy()
        topic_info["Label"] = topic_info.apply(
            lambda row: " | ".join([w for w, _ in self._get_topic_words(row["Topic"], top_n=5)])
            if row["Topic"] != -1 else "Outlier",
            axis=1,
        )
        return topic_info

    def get_topic_words(self, topic_id: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """获取指定主题的关键词"""
        return self._get_topic_words(topic_id, top_n)

    def list_topics(self, n: int = 20) -> pd.DataFrame:
        """列出前N个主题"""
        info = self.get_topic_info()
        info = info[info["Topic"] != -1]
        return info.head(n)

    # ==========================================
    # 辅助方法
    # ==========================================

    def _preprocess_single_text(self, text: str, stopwords: Set[str], jieba) -> str:
        """预处理单条文本"""
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
            if token in stopwords:
                continue
            if re.match(r"^[一-鿿]+$", token):
                filtered.append(token)
            elif re.match(r"^[a-zA-Z0-9]{2,}$", token):
                filtered.append(token.lower())

        return " ".join(filtered)

    def _get_topic_words(self, topic_id: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """获取主题词"""
        if topic_id == -1:
            return []
        try:
            return self.topic_model.get_topic(topic_id)[:top_n]
        except Exception:
            return []
