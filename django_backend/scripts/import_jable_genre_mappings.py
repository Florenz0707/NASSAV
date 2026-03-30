#!/usr/bin/env python3
"""
导入 Jable 类别映射

功能：
1. 读取人工整理的 Jable 类别映射 YAML
2. 仅导入 confidence 为 high / medium 的映射
3. 写入 GenreSourceMapping

使用方法：
    uv run python scripts/import_jable_genre_mappings.py [--input PATH] [--dry-run] [--verbose]

选项：
    --input PATH  输入 YAML 路径，默认 doc/jable_genre_manual_matches.yaml
    --dry-run     仅预览，不实际写入数据库
    --verbose     显示详细日志
"""

import argparse
import os
import re
import sys
from pathlib import Path

import django
import yaml

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from loguru import logger
from nassav.models import Genre, GenreSourceMapping

DEFAULT_INPUT_PATH = project_root / "doc" / "jable_genre_manual_matches.yaml"
ALLOWED_CONFIDENCE = {"high", "medium"}


def configure_logger(verbose: bool) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="DEBUG" if verbose else "INFO",
    )


def load_mapping_items(input_path: Path) -> list[dict]:
    payload = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    items = payload.get("matched_local_genres")
    if not isinstance(items, list):
        raise ValueError(f"映射文件格式错误，缺少 matched_local_genres: {input_path}")
    return items


def normalize_jable_mapping_name(raw_name: str) -> str:
    name = str(raw_name or "").strip()
    name = re.sub(r"\s+\d+\s*部影片\s*$", "", name)
    return name.strip()


def extract_jable_slug(source_genre_url: str) -> str:
    match = re.search(r"/(?:tags|categories)/([^/?#]+)/?", str(source_genre_url or ""))
    if not match:
        return ""
    return match.group(1).strip().lower()


def import_jable_genre_mappings(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    configure_logger(verbose)

    if not input_path.exists():
        raise FileNotFoundError(f"未找到映射文件: {input_path}")

    items = load_mapping_items(input_path)
    stats = {
        "total_items": len(items),
        "eligible_items": 0,
        "saved": 0,
        "updated": 0,
        "dry_run": 0,
        "skipped_low_confidence": 0,
        "skipped_missing_genre": 0,
    }

    logger.info(f"读取映射文件: {input_path}")
    if dry_run:
        logger.warning("当前为 DRY-RUN 模式，不会实际写入数据库")

    for item in items:
        confidence = str(item.get("confidence") or "").strip().lower()
        if confidence not in ALLOWED_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            continue

        stats["eligible_items"] += 1
        local_genre_name = str(item.get("local_genre") or "").strip()
        source_genre_name = normalize_jable_mapping_name(item.get("jable_name") or "")
        source_genre_url = str(item.get("jable_url") or "").strip()
        slug = extract_jable_slug(source_genre_url)
        match_method = str(item.get("match_type") or "manual").strip() or "manual"

        slug = extract_jable_slug(str(item.get("jable_url") or "").strip())
        if not slug:
            logger.warning(f"跳过无法提取 slug 的映射: {item}")
            continue

        genre = Genre.objects.filter(name=local_genre_name).first()
        if genre is None:
            logger.warning(f"跳过不存在的本地类别: {local_genre_name}")
            stats["skipped_missing_genre"] += 1
            continue

        defaults = {
            "source_genre_name": source_genre_name,
            "source_genre_url": source_genre_url,
            "source_genre_slug": slug,
            "match_method": match_method,
            "confidence": 1.0 if confidence == "high" else 0.8,
            "is_verified": confidence == "high",
            "is_active": True,
        }

        if dry_run:
            exists = GenreSourceMapping.objects.filter(
                genre=genre,
                source_name="jable",
            ).exists()
            stats["dry_run"] += 1
            logger.info(
                f"[DRY-RUN] {'更新' if exists else '新增'} "
                f"{local_genre_name} -> {source_genre_name}"
            )
            continue

        mapping, created = GenreSourceMapping.objects.update_or_create(
            genre=genre,
            source_name="jable",
            defaults=defaults,
        )
        _ = mapping
        if created:
            stats["saved"] += 1
            logger.info(f"新增映射: {local_genre_name} -> {source_genre_name}")
        else:
            stats["updated"] += 1
            logger.info(f"更新映射: {local_genre_name} -> {source_genre_name}")

    logger.info(
        "导入完成: "
        f"eligible={stats['eligible_items']}, "
        f"saved={stats['saved']}, "
        f"updated={stats['updated']}, "
        f"dry_run={stats['dry_run']}, "
        f"skipped_low_confidence={stats['skipped_low_confidence']}, "
        f"skipped_missing_genre={stats['skipped_missing_genre']}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="导入人工整理的 Jable 类别映射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 按默认映射文件执行导入
  uv run python scripts/import_jable_genre_mappings.py

  # 仅预览
  uv run python scripts/import_jable_genre_mappings.py --dry-run

  # 指定输入文件
  uv run python scripts/import_jable_genre_mappings.py --input doc/jable_genre_manual_matches.yaml
        """,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"输入 YAML 路径，默认 {DEFAULT_INPUT_PATH}",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅预览，不实际写入数据库"
    )
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    try:
        import_jable_genre_mappings(
            input_path=args.input,
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
