#!/usr/bin/env python3
"""
基于推荐历史同步 Jable 演员映射

功能：
1. 从 RecommendationItem 中读取最近推荐过的 Jable 作品
2. 逐个 avid 通过 JavBus + Jable 双源对齐补写 ActorSourceMapping
3. 适合作为定时任务运行，不阻塞推荐接口

使用方法：
    uv run python scripts/sync_recommendation_actor_mappings.py [--limit N] [--verbose]

选项：
    --limit N   限制处理的去重 avid 数量，默认 100
    --verbose   显示详细日志
"""

import argparse
import os
import sys
from pathlib import Path

import django

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings
from loguru import logger
from nassav.models import RecommendationItem
from nassav.recommendation.lazy_actor_mapping import (
    recommendation_actor_mapping_learner,
)
from nassav.source import Jable


def configure_logger(verbose: bool) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="DEBUG" if verbose else "INFO",
    )


def get_proxy() -> str | None:
    if getattr(settings, "PROXY_ENABLED", False):
        return getattr(settings, "PROXY_URL", None)
    return None


def collect_target_avids(limit: int) -> list[str]:
    seen: set[str] = set()
    avids: list[str] = []
    queryset = RecommendationItem.objects.filter(source__iexact="Jable").order_by(
        "-created_at", "-id"
    )
    for avid in queryset.values_list("avid", flat=True):
        normalized = str(avid or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        avids.append(normalized)
        if len(avids) >= limit:
            break
    return avids


def sync_recommendation_actor_mappings(
    *,
    limit: int = 100,
    verbose: bool = False,
) -> dict[str, int]:
    configure_logger(verbose)

    target_avids = collect_target_avids(limit=max(1, int(limit)))
    logger.info("=" * 60)
    logger.info("基于推荐历史同步 Jable 演员映射")
    logger.info("=" * 60)
    logger.info(f"待处理 avid 数: {len(target_avids)}")

    if not target_avids:
        return {
            "target_avids": 0,
            "javbus_fetched": 0,
            "jable_fetched": 0,
            "saved": 0,
            "unmatched": 0,
            "conflict": 0,
            "skipped_errors": 0,
        }

    jable = Jable(proxy=get_proxy())
    jable.load_cookie_from_db()

    stats = recommendation_actor_mapping_learner.sync_from_avids(
        jable=jable,
        avids=target_avids,
    )
    result = {
        "target_avids": len(target_avids),
        **stats,
    }

    logger.info("=" * 60)
    logger.info("处理完成")
    logger.info("=" * 60)
    logger.info(f"作品:     {result['target_avids']}")
    logger.info(f"JavBus:   {result['javbus_fetched']}")
    logger.info(f"Jable:    {result['jable_fetched']}")
    logger.info(f"写入:     {result['saved']}")
    logger.info(f"未匹配:   {result['unmatched']}")
    logger.info(f"冲突:     {result['conflict']}")
    logger.info(f"错误跳过: {result['skipped_errors']}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="基于推荐历史回填 Jable 演员映射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 同步最近 100 个推荐结果
  uv run python scripts/sync_recommendation_actor_mappings.py

  # 仅同步最近 20 个推荐结果
  uv run python scripts/sync_recommendation_actor_mappings.py --limit 20

  # 输出详细日志
  uv run python scripts/sync_recommendation_actor_mappings.py --verbose
        """,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="限制处理的去重 avid 数量，默认 100",
    )
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    try:
        sync_recommendation_actor_mappings(
            limit=args.limit,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(0)
    except Exception as exc:
        logger.exception(f"执行失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
