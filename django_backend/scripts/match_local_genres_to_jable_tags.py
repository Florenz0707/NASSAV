#!/usr/bin/env python3
"""
匹配本地类别与 Jable 首页标签

功能：
1. 读取本地 Genre 类别
2. 加载 export_jable_home_tags.py 生成的标签 JSON
3. 为每个类别计算最可能的 Jable 标签候选
4. 将匹配建议保存到本地临时文件

使用方法：
    uv run python scripts/match_local_genres_to_jable_tags.py [--input PATH] [--output PATH] [--min-score FLOAT] [--candidate-limit N] [--verbose]

选项：
    --input PATH            Jable 标签 JSON 输入文件，默认 /tmp/nassav_jable_home_tags.json
    --output PATH           输出文件路径，默认 /tmp/nassav_jable_genre_tag_matches.json
    --min-score FLOAT       候选最低分数阈值，默认 0.6
    --candidate-limit N     每个类别保留的候选数量，默认 5
    --verbose               显示详细日志
"""

import argparse
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
import os
import re
import sys
from pathlib import Path

import django

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.db.models import Count
from loguru import logger
from nassav.models import Genre

DEFAULT_INPUT_PATH = Path("/tmp/nassav_jable_home_tags.json")
DEFAULT_OUTPUT_PATH = Path("/tmp/nassav_jable_genre_tag_matches.json")


@dataclass(frozen=True)
class GenreTagCandidate:
    name: str
    url: str
    kind: str


@dataclass(frozen=True)
class GenreTagMatchCandidate:
    name: str
    url: str
    kind: str
    score: float
    method: str


def configure_logger(verbose: bool) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="DEBUG" if verbose else "INFO",
    )


def normalize_genre_text(raw_value: str) -> str:
    value = str(raw_value or "").strip().casefold()
    value = re.sub(r"[\s\u3000]+", "", value)
    value = re.sub(r"[-_/]+", "", value)
    value = re.sub(r"[()（）\[\]【】・·.,，、]+", "", value)
    return value


def _score_candidate(genre_name: str, candidate_name: str) -> tuple[float, str]:
    raw_genre = str(genre_name or "").strip()
    raw_candidate = str(candidate_name or "").strip()
    if not raw_genre or not raw_candidate:
        return 0.0, "empty"

    if raw_genre.casefold() == raw_candidate.casefold():
        return 1.0, "exact"

    normalized_genre = normalize_genre_text(raw_genre)
    normalized_candidate = normalize_genre_text(raw_candidate)
    if not normalized_genre or not normalized_candidate:
        return 0.0, "empty_normalized"

    if normalized_genre == normalized_candidate:
        return 0.98, "normalized_exact"

    if (
        normalized_genre in normalized_candidate
        or normalized_candidate in normalized_genre
    ):
        ratio = min(len(normalized_genre), len(normalized_candidate)) / max(
            len(normalized_genre), len(normalized_candidate)
        )
        return max(0.78, ratio), "substring"

    ratio = SequenceMatcher(None, normalized_genre, normalized_candidate).ratio()
    return ratio, "similarity"


def build_genre_tag_candidates(items: list[dict]) -> list[GenreTagCandidate]:
    candidates: list[GenreTagCandidate] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not name or not url or not kind:
            continue
        token = url.casefold()
        if token in seen:
            continue
        seen.add(token)
        candidates.append(GenreTagCandidate(name=name, url=url, kind=kind))
    return candidates


def match_genre_to_tags(
    genre_name: str,
    candidates: list[GenreTagCandidate],
    *,
    min_score: float = 0.6,
    limit: int = 5,
) -> list[GenreTagMatchCandidate]:
    ranked: list[GenreTagMatchCandidate] = []
    for item in candidates:
        score, method = _score_candidate(genre_name, item.name)
        if score < min_score:
            continue
        ranked.append(
            GenreTagMatchCandidate(
                name=item.name,
                url=item.url,
                kind=item.kind,
                score=round(score, 4),
                method=method,
            )
        )

    ranked.sort(key=lambda item: (-item.score, item.name, item.url))
    return ranked[: max(int(limit), 1)]


def dump_genre_tag_matches(matches: list[GenreTagMatchCandidate]) -> list[dict]:
    return [asdict(item) for item in matches]


def load_jable_tags(input_path: Path) -> list[dict]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(f"标签文件格式错误，缺少 items 数组: {input_path}")
    return items


def build_match_payload(
    *,
    tag_items: list[dict],
    min_score: float,
    candidate_limit: int,
) -> dict[str, object]:
    tag_candidates = build_genre_tag_candidates(tag_items)
    genres = list(
        Genre.objects.annotate(resource_count=Count("resources"))
        .order_by("-resource_count", "name")
        .values("id", "name", "resource_count")
    )

    matched_count = 0
    items: list[dict[str, object]] = []
    for genre in genres:
        matches = match_genre_to_tags(
            str(genre["name"]),
            tag_candidates,
            min_score=min_score,
            limit=candidate_limit,
        )
        if matches:
            matched_count += 1

        items.append(
            {
                "genre_id": genre["id"],
                "genre_name": genre["name"],
                "resource_count": genre["resource_count"],
                "matched": bool(matches),
                "best_match": dump_genre_tag_matches(matches[:1])[0]
                if matches
                else None,
                "candidates": dump_genre_tag_matches(matches),
            }
        )

    return {
        "source": "Jable",
        "input_tag_count": len(tag_candidates),
        "genre_count": len(genres),
        "matched_genre_count": matched_count,
        "unmatched_genre_count": len(genres) - matched_count,
        "min_score": min_score,
        "candidate_limit": candidate_limit,
        "items": items,
    }


def match_local_genres_to_jable_tags(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    min_score: float = 0.6,
    candidate_limit: int = 5,
    verbose: bool = False,
) -> dict[str, object]:
    configure_logger(verbose)

    if not input_path.exists():
        raise FileNotFoundError(f"未找到 Jable 标签输入文件: {input_path}")

    tag_items = load_jable_tags(input_path)
    payload = build_match_payload(
        tag_items=tag_items,
        min_score=min_score,
        candidate_limit=candidate_limit,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    logger.info(
        f"已为 {payload['genre_count']} 个本地类别生成匹配建议，命中 {payload['matched_genre_count']} 个，输出到: {output_path}"
    )
    return {
        "output_path": str(output_path),
        "genre_count": payload["genre_count"],
        "matched_genre_count": payload["matched_genre_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为本地 Genre 生成 Jable 标签匹配建议",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认输入输出
  uv run python scripts/match_local_genres_to_jable_tags.py

  # 指定输入与输出
  uv run python scripts/match_local_genres_to_jable_tags.py --input /tmp/jable-tags.json --output /tmp/jable-genre-matches.json

  # 调整相似度阈值
  uv run python scripts/match_local_genres_to_jable_tags.py --min-score 0.72 --candidate-limit 3
        """,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Jable 标签 JSON 输入文件，默认 {DEFAULT_INPUT_PATH}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"输出文件路径，默认 {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.6,
        help="候选最低分数阈值，默认 0.6",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=5,
        help="每个类别保留的候选数量，默认 5",
    )
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    try:
        match_local_genres_to_jable_tags(
            input_path=args.input,
            output_path=args.output,
            min_score=args.min_score,
            candidate_limit=args.candidate_limit,
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
