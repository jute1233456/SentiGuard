#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速启动器 - 高级THUCNews+BERTopic训练
提供预设配置一键启动
"""

import argparse
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 预设配置
PRESETS = {
    "test": {
        "name": "测试版",
        "sample": 5000,
        "n_topics": 20,
        "embedding_model": "BAAI/bge-small-zh-v1.5",
        "min_topic_size": 10,
        "description": "快速测试用，5000样本，20主题，小型模型"
    },
    "small": {
        "name": "小型版",
        "sample": 10000,
        "n_topics": 30,
        "embedding_model": "BAAI/bge-small-zh-v1.5",
        "min_topic_size": 20,
        "description": "小型训练，10000样本，30主题"
    },
    "medium": {
        "name": "中型版",
        "sample": 50000,
        "n_topics": 50,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "min_topic_size": 30,
        "description": "推荐配置，50000样本，50主题，大型模型"
    },
    "large": {
        "name": "大型版",
        "sample": 100000,
        "n_topics": 75,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "min_topic_size": 50,
        "description": "高质量训练，100000样本，75主题"
    },
    "full": {
        "name": "完整版",
        "sample": 0,
        "n_topics": 100,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "min_topic_size": 100,
        "description": "全量数据训练，100主题"
    },
}


def print_presets():
    """打印预设配置"""
    print("=" * 80)
    print("可用预设配置:")
    print("=" * 80)
    for key, preset in PRESETS.items():
        print(f"\n  [{key}] - {preset['name']}")
        print(f"      {preset['description']}")
        print(f"      样本: {'全量' if preset['sample'] == 0 else preset['sample']}")
        print(f"      主题: {preset['n_topics']}")
        print(f"      模型: {preset['embedding_model']}")
    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="快速启动器 - THUCNews+BERTopic高级训练",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "preset",
        nargs="?",
        choices=list(PRESETS.keys()) + ["list"],
        help="预设配置 (list=查看全部)"
    )

    # 自定义配置
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="自定义样本量 (覆盖预设)"
    )
    parser.add_argument(
        "--n_topics",
        type=int,
        default=None,
        help="自定义主题数 (覆盖预设)"
    )
    parser.add_argument(
        "--embedding_model",
        type=str,
        default=None,
        help="自定义嵌入模型 (覆盖预设)"
    )
    parser.add_argument(
        "--min_topic_size",
        type=int,
        default=None,
        help="自定义最小主题大小 (覆盖预设)"
    )

    # 输出和控制
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="自定义输出目录"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="重置训练（清除检查点）"
    )
    parser.add_argument(
        "--no_resume",
        action="store_true",
        help="不恢复训练"
    )

    args = parser.parse_args()

    # 列出预设
    if args.preset == "list":
        print_presets()
        return 0

    # 验证选择
    if args.preset not in PRESETS:
        print("错误: 请选择一个预设配置\n")
        print_presets()
        print("\n使用示例:")
        print("  python run_advanced_training.py test          # 测试版")
        print("  python run_advanced_training.py medium        # 推荐版")
        print("  python run_advanced_training.py list          # 查看全部")
        return 1

    # 获取预设配置
    preset = PRESETS[args.preset]

    # 合并自定义配置
    config = {
        "sample": args.sample if args.sample is not None else preset["sample"],
        "n_topics": args.n_topics if args.n_topics is not None else preset["n_topics"],
        "embedding_model": args.embedding_model if args.embedding_model is not None else preset["embedding_model"],
        "min_topic_size": args.min_topic_size if args.min_topic_size is not None else preset["min_topic_size"],
    }

    # 确定输出目录
    if args.output_dir is None:
        output_dir = Path("data/thucnews_advanced") / args.preset
    else:
        output_dir = args.output_dir

    # 打印配置摘要
    print("\n" + "=" * 80)
    print(f"🚀 启动训练: {preset['name']}")
    print("=" * 80)
    print(f"\n配置:")
    print(f"  预设:     {args.preset}")
    print(f"  样本量:   {'全量' if config['sample'] == 0 else config['sample']}")
    print(f"  主题数:   {config['n_topics']}")
    print(f"  嵌入模型: {config['embedding_model']}")
    print(f"  最小主题: {config['min_topic_size']}")
    print(f"  输出目录: {output_dir}")
    print(f"  恢复训练: {'否' if args.no_resume else '是'}")
    print(f"  重置:     {'是' if args.reset else '否'}")
    print("\n" + "=" * 80)
    print(f"\n按 Ctrl+C 可以随时停止训练，下次运行会自动恢复！\n")

    # 询问确认
    try:
        response = input("确认开始训练？[Y/n] ").strip().lower()
        if response and response != "y" and response != "yes":
            print("已取消")
            return 0
    except KeyboardInterrupt:
        print("\n已取消")
        return 0

    # 启动训练
    from train_thucnews_advanced import AdvancedTHUCNewsTrainer

    trainer = AdvancedTHUCNewsTrainer(
        output_dir=output_dir,
        sample_size=config["sample"],
        n_topics=config["n_topics"],
        embedding_model=config["embedding_model"],
        min_topic_size=config["min_topic_size"],
        resume=not args.no_resume,
    )

    if args.reset:
        # 重置检查点
        if trainer.checkpoint_dir.exists():
            import shutil
            import time
            backup_dir = trainer.checkpoint_dir.parent / f"checkpoints_backup_{int(time.time())}"
            shutil.move(trainer.checkpoint_dir, backup_dir)
            print(f"已备份原检查点到: {backup_dir}")

    return trainer.run()


if __name__ == "__main__":
    sys.exit(main())
