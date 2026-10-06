#!/usr/bin/env python3
"""
直接使用推荐 seed 黑名单召回 Jable 资源，并检测推荐黑名单过滤是否生效。

功能：
1. 读取 RecommendationSeedProfile 中 is_blocked=true 的 actor / genre 黑名单
2. 对 Jable source slug 直接请求 model / tag / category 页面
3. 对只有名称的黑名单回退到 Jable 搜索
4. 复用推荐过滤逻辑检测候选是否会被过滤，输出漏过滤样本

使用方法：
    uv run python scripts/check_recommendation_blacklist_filter.py [--verbose]

选项：
    --limit-profiles N      限制检测的黑名单条目数，默认 20
    --per-profile-limit N   每个黑名单条目最多检测多少个候选，默认 8
    --max-pages N           每个召回入口最多翻页数，默认 1
    --detail-limit N        最多补详情的候选数，默认 50
    --force-refresh         跳过外部源缓存，重新抓取 Jable
    --json-output PATH      将检测结果写入 JSON 文件
    --verbose               显示详细日志
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import django

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings
from loguru import logger
from nassav.models import RecommendationSeedProfile
from nassav.recommendation.entities import (
    RecommendationCandidate,
    RecommendationRequest,
    RecommendationSeed,
)
from nassav.recommendation.jable_search import JableSearchRecommender
from nassav.recommendation.seed_profiles import recommendation_seed_profile_repository
from nassav.source import Jable


@dataclass
class ProbeRecord:
    seed_type: str
    value: str
    source_name: str
    source_identifier: str
    recall_mode: str
    avid: str
    title: str
    detail_url: str
    filtered: bool
    raw_metrics: dict[str, Any]


class EmptySeedProvider:
    def get_seeds(self, request: RecommendationRequest) -> list[RecommendationSeed]:
        return []

    def get_additional_seeds(
        self,
        request: RecommendationRequest,
        existing_seeds: list[RecommendationSeed],
        limit: int,
    ) -> list[RecommendationSeed]:
        return []


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


def collect_blocked_profiles(limit: int) -> list[RecommendationSeedProfile]:
    queryset = (
        RecommendationSeedProfile.objects.filter(
            seed_type__in=["actor", "genre"],
            is_blocked=True,
        )
        .only(
            "seed_type",
            "value",
            "normalized_value",
            "source_name",
            "source_identifier",
        )
        .order_by("seed_type", "source_name", "source_identifier", "normalized_value")
    )
    if limit > 0:
        queryset = queryset[:limit]
    return list(queryset)


def build_probe_request(
    detail_limit: int, force_refresh: bool
) -> RecommendationRequest:
    blocked_name_keys, blocked_source_keys = (
        recommendation_seed_profile_repository.build_blocked_seed_keys()
    )
    return RecommendationRequest(
        limit=0,
        per_seed_limit=0,
        actor_seed_limit=0,
        genre_seed_limit=0,
        include_hot_board=False,
        include_latest_updates=False,
        discovery_limit=0,
        detail_enrichment_limit=max(int(detail_limit), 0),
        force_refresh_external=bool(force_refresh),
        seed_blacklist_active=bool(blocked_name_keys or blocked_source_keys),
        blocked_seed_name_keys=blocked_name_keys,
        blocked_seed_source_keys=blocked_source_keys,
    )


def recall_profile_items(
    *,
    jable: Jable,
    profile: RecommendationSeedProfile,
    max_pages: int,
    per_profile_limit: int,
    force_refresh: bool,
) -> list[tuple[str, dict]]:
    source_name = str(profile.source_name or "").strip().lower()
    source_identifier = str(profile.source_identifier or "").strip().lower()
    seed_type = str(profile.seed_type or "").strip().lower()
    value = str(profile.value or "").strip()
    max_pages = max(int(max_pages), 1)
    per_profile_limit = max(int(per_profile_limit), 1)

    fetchers = []
    if source_name == "jable" and source_identifier:
        if seed_type == "actor":
            fetchers.append(
                (
                    f"model:{source_identifier}",
                    lambda page: jable.get_model_videos(
                        source_identifier,
                        page=page,
                        force_refresh=force_refresh,
                    ),
                )
            )
        elif seed_type == "genre":
            fetchers.extend(
                [
                    (
                        f"tag:{source_identifier}",
                        lambda page: jable.get_tag_videos(
                            source_identifier,
                            page=page,
                            force_refresh=force_refresh,
                        ),
                    ),
                    (
                        f"category:{source_identifier}",
                        lambda page: jable.get_category_videos(
                            source_identifier,
                            page=page,
                            force_refresh=force_refresh,
                        ),
                    ),
                ]
            )

    if value:
        fetchers.append(
            (
                f"search:{value}",
                lambda page: jable.search(
                    value,
                    page=page,
                    force_refresh=force_refresh,
                ),
            )
        )

    seen: set[tuple[str, str]] = set()
    output: list[tuple[str, dict]] = []
    for recall_mode, fetch_page in fetchers:
        for page in range(1, max_pages + 1):
            try:
                page_items = fetch_page(page)
            except Exception as exc:
                logger.warning(
                    f"召回失败: {profile} mode={recall_mode} page={page}: {exc}"
                )
                break
            if not page_items:
                break
            for item in page_items:
                avid = str(item.get("avid", "")).strip().upper()
                if not avid:
                    continue
                key = (recall_mode, avid)
                if key in seen:
                    continue
                seen.add(key)
                output.append((recall_mode, item))
                if len(output) >= per_profile_limit:
                    return output
    return output


def make_candidate(item: dict) -> RecommendationCandidate:
    return RecommendationCandidate(
        avid=str(item.get("avid", "")).strip().upper(),
        title=str(item.get("title", "")).strip(),
        detail_url=str(item.get("detail_url", "")).strip(),
        cover_url=str(item.get("cover_url", "")).strip(),
        source=str(item.get("source", "Jable")).strip() or "Jable",
        raw_metrics=dict(item.get("metrics") or {}),
    )


def make_probe_record(
    *,
    profile: RecommendationSeedProfile,
    recall_mode: str,
    candidate: RecommendationCandidate,
    filtered: bool,
) -> ProbeRecord:
    return ProbeRecord(
        seed_type=str(profile.seed_type or "").strip(),
        value=str(profile.value or "").strip(),
        source_name=str(profile.source_name or "").strip(),
        source_identifier=str(profile.source_identifier or "").strip(),
        recall_mode=recall_mode,
        avid=candidate.avid,
        title=candidate.title,
        detail_url=candidate.detail_url,
        filtered=filtered,
        raw_metrics=dict(candidate.raw_metrics or {}),
    )


def check_recommendation_blacklist_filter(
    *,
    limit_profiles: int = 20,
    per_profile_limit: int = 8,
    max_pages: int = 1,
    detail_limit: int = 50,
    force_refresh: bool = False,
    json_output: str = "",
    verbose: bool = False,
) -> dict:
    configure_logger(verbose)

    profiles = collect_blocked_profiles(limit=max(int(limit_profiles), 0))
    request = build_probe_request(
        detail_limit=detail_limit,
        force_refresh=force_refresh,
    )

    logger.info("=" * 60)
    logger.info("推荐黑名单过滤检测")
    logger.info("=" * 60)
    logger.info(f"黑名单条目: {len(profiles)}")
    logger.info(f"名称黑名单 key: {len(request.blocked_seed_name_keys)}")
    logger.info(f"Source 黑名单 key: {len(request.blocked_seed_source_keys)}")

    if not profiles:
        result = {
            "profiles": 0,
            "candidates": 0,
            "filtered": 0,
            "leaked": 0,
            "items": [],
        }
        write_json_output(json_output, result)
        return result

    jable = Jable(proxy=get_proxy())
    jable.load_cookie_from_db()
    recommender = JableSearchRecommender(
        jable=jable,
        seed_provider=EmptySeedProvider(),
        max_pages_per_query=max(int(max_pages), 1),
    )

    records: list[ProbeRecord] = []
    for profile in profiles:
        logger.info(f"检测黑名单: {profile}")
        recalled_items = recall_profile_items(
            jable=jable,
            profile=profile,
            max_pages=max_pages,
            per_profile_limit=per_profile_limit,
            force_refresh=force_refresh,
        )
        if not recalled_items:
            logger.warning(f"未召回候选: {profile}")
            continue

        candidates = [make_candidate(item) for _, item in recalled_items]
        candidates = recommender.enrich_candidates(candidates, request)
        allowed_by_avid = {
            candidate.avid
            for candidate in recommender.filter_blocklisted_candidates(
                candidates,
                request,
            )
        }

        for (recall_mode, _), candidate in zip(
            recalled_items, candidates, strict=False
        ):
            filtered = candidate.avid not in allowed_by_avid
            record = make_probe_record(
                profile=profile,
                recall_mode=recall_mode,
                candidate=candidate,
                filtered=filtered,
            )
            records.append(record)
            marker = "FILTERED" if filtered else "LEAK"
            log_func = logger.debug if filtered else logger.warning
            log_func(
                f"{marker} {record.seed_type}:{record.value} "
                f"[{record.recall_mode}] {record.avid} {record.title}"
            )

    leaked_records = [record for record in records if not record.filtered]
    result = {
        "profiles": len(profiles),
        "candidates": len(records),
        "filtered": len(records) - len(leaked_records),
        "leaked": len(leaked_records),
        "items": [asdict(record) for record in records],
        "leaks": [asdict(record) for record in leaked_records],
    }

    logger.info("=" * 60)
    logger.info("检测完成")
    logger.info("=" * 60)
    logger.info(f"候选总数: {result['candidates']}")
    logger.info(f"已过滤:   {result['filtered']}")
    logger.info(f"漏过滤:   {result['leaked']}")
    if leaked_records:
        logger.warning("发现漏过滤候选，请查看上方 LEAK 日志或 JSON 输出")

    write_json_output(json_output, result)
    return result


def write_json_output(path: str, payload: dict) -> None:
    output_path = str(path or "").strip()
    if not output_path:
        return
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"JSON 结果已写入: {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="直接使用推荐 seed 黑名单召回 Jable 资源并检测过滤效果",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 检测前 20 个黑名单，每个最多取 8 个候选
  uv run python scripts/check_recommendation_blacklist_filter.py

  # 强制刷新 Jable，输出详细日志
  uv run python scripts/check_recommendation_blacklist_filter.py --force-refresh --verbose

  # 重点验证 tag/category 差异，并保存结果
  uv run python scripts/check_recommendation_blacklist_filter.py --max-pages 2 --json-output /tmp/blacklist-check.json
        """,
    )
    parser.add_argument(
        "--limit-profiles",
        type=int,
        default=20,
        help="限制检测的黑名单条目数，默认 20；0 表示不限制",
    )
    parser.add_argument(
        "--per-profile-limit",
        type=int,
        default=8,
        help="每个黑名单条目最多检测多少个候选，默认 8",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="每个召回入口最多翻页数，默认 1",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=50,
        help="最多补详情的候选数，默认 50",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="跳过外部源缓存，重新抓取 Jable",
    )
    parser.add_argument("--json-output", default="", help="将检测结果写入 JSON 文件")
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    try:
        result = check_recommendation_blacklist_filter(
            limit_profiles=args.limit_profiles,
            per_profile_limit=args.per_profile_limit,
            max_pages=args.max_pages,
            detail_limit=args.detail_limit,
            force_refresh=args.force_refresh,
            json_output=args.json_output,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(130)
    except Exception as exc:
        logger.exception(f"执行失败: {exc}")
        sys.exit(1)

    sys.exit(1 if result.get("leaked") else 0)


if __name__ == "__main__":
    main()
