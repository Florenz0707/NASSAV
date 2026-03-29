#!/usr/bin/env python3
"""
回填 Jable 演员映射

功能：
1. 查找存在 Jable 作品且尚未建立 Jable mapping 的演员
2. 取该演员的一条 Jable 作品页面 HTML
3. 解析页面中的 `.models a.model`，提取 Jable 模型名与 slug
4. 将结果持久化到 ActorSourceMapping

使用方法：
    uv run python scripts/backfill_jable_actor_mappings.py [--limit N] [--dry-run] [--verbose]

选项：
    --limit N       限制处理的演员数量（用于测试）
    --dry-run       仅模拟运行，不实际写入数据库
    --verbose       显示详细日志
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
from django.db.models import Count, Q
from loguru import logger
from nassav.models import Actor, AVResource
from nassav.source import Jable
from nassav.source.jable_actor_mapping import (
    JableModelCandidate,
    parse_jable_model_candidates,
    persist_actor_source_mapping,
    select_best_model_candidate,
)


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


def build_target_actor_queryset():
    return (
        Actor.objects.annotate(
            jable_resource_count=Count(
                "resources",
                filter=Q(resources__source__iexact="Jable"),
                distinct=True,
            ),
            active_jable_mapping_count=Count(
                "source_mappings",
                filter=Q(
                    source_mappings__source_name="jable",
                    source_mappings__is_active=True,
                ),
                distinct=True,
            ),
        )
        .filter(jable_resource_count__gt=0, active_jable_mapping_count=0)
        .order_by("-jable_resource_count", "name")
    )


def pick_jable_resource(actor: Actor) -> AVResource | None:
    return (
        actor.resources.filter(source__iexact="Jable")
        .order_by("-metadata_updated_at", "-created_at")
        .first()
    )


def persist_mapping(
    *,
    actor: Actor,
    candidate: JableModelCandidate,
    confidence: float,
    dry_run: bool,
) -> tuple[bool, str]:
    if dry_run:
        return True, "dry_run"
    return persist_actor_source_mapping(
        actor=actor,
        candidate=candidate,
        confidence=confidence,
        match_method="imported",
    )


def backfill_jable_actor_mappings(
    *,
    limit: int | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    configure_logger(verbose)

    queryset = build_target_actor_queryset()
    total_candidates = queryset.count()
    if limit is not None and limit > 0:
        queryset = queryset[:limit]

    actors = list(queryset)
    logger.info("=" * 60)
    logger.info("回填 Jable 演员映射")
    logger.info("=" * 60)
    logger.info(f"待处理演员数: {len(actors)} / {total_candidates}")
    if dry_run:
        logger.warning("当前为 DRY-RUN 模式，不会实际写入数据库")

    jable = Jable(proxy=get_proxy())
    jable.load_cookie_from_db()

    stats = {
        "processed": 0,
        "saved": 0,
        "dry_run": 0,
        "skipped": 0,
        "failed_fetch": 0,
        "no_models": 0,
        "ambiguous": 0,
        "conflict": 0,
    }

    for index, actor in enumerate(actors, start=1):
        stats["processed"] += 1
        resource = pick_jable_resource(actor)
        logger.info(
            f"[{index}/{len(actors)}] 处理演员: {actor.name} "
            f"(Jable作品数: {getattr(actor, 'jable_resource_count', 0)})"
        )

        if resource is None:
            logger.warning("  跳过: 没有可用的 Jable 作品")
            stats["skipped"] += 1
            continue

        html = jable.get_html(resource.avid)
        if not html:
            logger.warning(f"  获取作品页失败: {resource.avid}")
            stats["failed_fetch"] += 1
            continue

        candidates = parse_jable_model_candidates(
            html,
            base_url=f"https://{jable.domain}/",
        )
        if verbose:
            logger.debug(
                "  解析到 models: "
                + ", ".join(
                    f"{item.source_actor_name}<{item.source_actor_slug}>"
                    for item in candidates
                )
            )
        if not candidates:
            logger.warning(f"  未解析到 models 节点: {resource.avid}")
            stats["no_models"] += 1
            continue

        selected, confidence, reason = select_best_model_candidate(
            actor_name=actor.name,
            candidates=candidates,
        )
        if selected is None:
            logger.warning(
                f"  无法唯一确定 mapping: {reason}，候选="
                + ", ".join(
                    f"{item.source_actor_name}<{item.source_actor_slug}>"
                    for item in candidates
                )
            )
            stats["ambiguous"] += 1
            continue

        ok, result = persist_mapping(
            actor=actor,
            candidate=selected,
            confidence=confidence,
            dry_run=dry_run,
        )
        if not ok:
            logger.warning(f"  跳过: {result}")
            stats["conflict"] += 1
            continue

        logger.info(
            f"  {'[DRY-RUN] ' if dry_run else ''}绑定为 "
            f"{selected.source_actor_name} <{selected.source_actor_slug}> "
            f"(reason={reason}, confidence={confidence:.2f})"
        )
        if dry_run:
            stats["dry_run"] += 1
        else:
            stats["saved"] += 1

    logger.info("=" * 60)
    logger.info("处理完成")
    logger.info("=" * 60)
    logger.info(f"处理:     {stats['processed']}")
    logger.info(f"写入:     {stats['saved']}")
    logger.info(f"预览:     {stats['dry_run']}")
    logger.info(f"跳过:     {stats['skipped']}")
    logger.info(f"抓取失败: {stats['failed_fetch']}")
    logger.info(f"无models:  {stats['no_models']}")
    logger.info(f"歧义:     {stats['ambiguous']}")
    logger.info(f"冲突:     {stats['conflict']}")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="通过 Jable 作品页回填演员 mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 预览前 10 个待回填演员
  uv run python scripts/backfill_jable_actor_mappings.py --dry-run --limit 10

  # 实际执行回填
  uv run python scripts/backfill_jable_actor_mappings.py

  # 开启详细日志
  uv run python scripts/backfill_jable_actor_mappings.py --verbose --limit 20
        """,
    )
    parser.add_argument("--limit", type=int, help="限制处理的演员数量（用于测试）")
    parser.add_argument(
        "--dry-run", action="store_true", help="仅模拟运行，不实际写入数据库"
    )
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")

    args = parser.parse_args()

    try:
        backfill_jable_actor_mappings(
            limit=args.limit,
            dry_run=args.dry_run,
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
