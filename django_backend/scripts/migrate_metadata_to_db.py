#!/usr/bin/env python3
"""
元数据迁移脚本（历史脚本）

警告：
    此脚本用于早期 JSON 元数据迁移到数据库，已经不再需要。
    现在的项目采用 Database-First 架构，直接在数据库中管理元数据。

原功能：
    将 resource/{AVID}/{AVID}.json 元数据导入到 AVResource 模型中
    （不会删除原始 JSON 文件）

历史用法：
    # 预览模式（默认）
    python scripts/migrate_metadata_to_db.py --dry-run

    # 实际执行迁移
    python scripts/migrate_metadata_to_db.py --apply

    # 限制处理数量
    python scripts/migrate_metadata_to_db.py --apply --limit 100

    # 强制覆盖现有数据
    python scripts/migrate_metadata_to_db.py --apply --force

    # 生成报告
    python scripts/migrate_metadata_to_db.py --apply --report migration_report.json

注意：
    - 新项目不需要执行此脚本
    - 仅保留作为历史参考
    - 脚本会执行完整性校验：读取 JSON -> 写入 DB -> 读回比较
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def setup_django():
    # Ensure project root is on PYTHONPATH so `django_project` 可被找到
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    import django

    django.setup()


def normalize_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if i]
    if isinstance(x, str):
        return [i.strip() for i in x.split(",") if i.strip()]
    return [str(x)]


def load_json_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return None


def migrate(dry_run=True, limit=None, report_path=None, force=False):
    force_overwrite = bool(force)
    setup_django()
    from django.conf import settings
    from django.db import transaction
    from django.utils import timezone
    from nassav.models import Actor, AVResource, Genre

    resource_root = Path(settings.RESOURCE_DIR)
    total_dirs = 0
    processed = 0
    created = 0
    updated = 0
    skipped_no_json = 0
    errors = []
    mismatches = []
    actor_cache = {}
    genre_cache = {}

    report = {
        "total_dirs": 0,
        "processed": 0,
        "created": 0,
        "updated": 0,
        "skipped_no_json": 0,
        "errors": [],
        "mismatches": [],
    }

    if not resource_root.exists():
        print(f"资源目录不存在: {resource_root}")
        return

    dirs = [p for p in resource_root.iterdir() if p.is_dir()]
    report["total_dirs"] = len(dirs)

    if limit:
        dirs = dirs[:limit]

    for d in dirs:
        total_dirs += 1
        avid = d.name
        json_file = d / f"{avid}.json"
        if not json_file.exists():
            skipped_no_json += 1
            report["skipped_no_json"] = skipped_no_json
            continue

        data = load_json_file(json_file)
        if data is None:
            errors.append({"avid": avid, "error": "json_load_failed"})
            continue

        # 如果 DB 中已存在，默认跳过，除非启用 force_overwrite（通过 --force）
        try:
            if AVResource.objects.filter(avid=avid).exists() and not force_overwrite:
                skipped_no_json += 1
                report["skipped_no_json"] = skipped_no_json
                continue
        except Exception:
            # 在干运行或 DB 无法访问时忽略此检查
            pass

        # 提取字段
        title = data.get("title") or data.get("name") or data.get("avid")
        source = data.get("source") or data.get("from") or data.get("downloader")
        m3u8 = data.get("m3u8")
        release_date = data.get("release_date") or data.get("date")
        duration = data.get("duration")
        actors = normalize_list(
            data.get("actors") or data.get("actresses") or data.get("cast")
        )
        genres = normalize_list(data.get("genres") or data.get("tags"))
        cover = (
            data.get("cover") or data.get("cover_filename") or data.get("cover_file")
        )

        # 文件存在性检查
        mp4_file = d / f"{avid}.mp4"
        file_exists = mp4_file.exists()
        file_size = mp4_file.stat().st_size if file_exists else None

        # 解析时长为秒，优先使用 mp4 的真实时长（如果可用）
        try:
            duration_seconds = parse_duration_to_seconds(
                duration, mp4_path=mp4_file if file_exists else None
            )
        except Exception:
            duration_seconds = None

        # 构建元数据字段（保存原始 JSON）
        metadata = data

        try:
            if dry_run:
                # 模拟：仅记录操作
                processed += 1
                report["processed"] = processed
                print(
                    f"[DRY] 处理 {avid} -> title={title} actors={len(actors)} genres={len(genres)} file_exists={file_exists}"
                )
            else:
                with transaction.atomic():
                    obj, created_flag = AVResource.objects.update_or_create(
                        avid=avid,
                        defaults={
                            "title": title,
                            "source": source or "",
                            "release_date": release_date if release_date else None,
                            "duration": duration_seconds,
                            "m3u8": m3u8 or None,
                            "metadata": metadata,
                            "cover_filename": cover or None,
                            "file_exists": file_exists,
                            "file_size": file_size,
                            "metadata_saved_at": timezone.now(),
                        },
                    )

                    # 关联演员
                    actor_objs = []
                    for a in actors:
                        if a in actor_cache:
                            actor_objs.append(actor_cache[a])
                        else:
                            actor_obj, _ = Actor.objects.get_or_create(name=a)
                            actor_cache[a] = actor_obj
                            actor_objs.append(actor_obj)
                    obj.actors.set(actor_objs)

                    # 关联类型
                    genre_objs = []
                    for g in genres:
                        if g in genre_cache:
                            genre_objs.append(genre_cache[g])
                        else:
                            genre_obj, _ = Genre.objects.get_or_create(name=g)
                            genre_cache[g] = genre_obj
                            genre_objs.append(genre_obj)
                    obj.genres.set(genre_objs)

                    if created_flag:
                        created += 1
                    else:
                        updated += 1

                    processed += 1
                    report["processed"] = processed
                    report["created"] = created
                    report["updated"] = updated

                    # 读回并校验关键字段
                    obj.refresh_from_db()
                    mismatch = {}
                    # 比较元数据的某些关键字段
                    if (obj.title or "") != (title or ""):
                        mismatch["title"] = {"json": title, "db": obj.title}
                    if (obj.m3u8 or "") != (m3u8 or ""):
                        mismatch["m3u8"] = {"json": m3u8, "db": obj.m3u8}
                    db_actors = sorted([a.name for a in obj.actors.all()])
                    if sorted(actors) != db_actors:
                        mismatch["actors"] = {"json": actors, "db": db_actors}
                    db_genres = sorted([g.name for g in obj.genres.all()])
                    if sorted(genres) != db_genres:
                        mismatch["genres"] = {"json": genres, "db": db_genres}
                    if mismatch:
                        mismatches.append({"avid": avid, "mismatch": mismatch})

        except Exception as e:
            errors.append({"avid": avid, "error": str(e)})

    # 报告
    report["errors"] = errors
    report["mismatches"] = mismatches
    report["skipped_no_json"] = skipped_no_json

    print("\n=== 迁移报告 ===")
    print(f"total_dirs: {total_dirs}")
    print(f"processed: {processed}")
    print(f"created: {created}")
    print(f"updated: {updated}")
    print(f"skipped_no_json: {skipped_no_json}")
    print(f"errors: {len(errors)}")
    print(f"mismatches: {len(mismatches)}")

    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as rf:
                json.dump(report, rf, ensure_ascii=False, indent=2)
            print(f"报告已写入: {report_path}")
        except Exception as e:
            print(f"写报告失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="迁移 resource 元数据到数据库 (AVResource)")
    parser.add_argument("--apply", action="store_true", help="写入数据库（默认仅干运行）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的数据库记录")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个条目")
    parser.add_argument("--report", type=str, default=None, help="将报告写入到文件 (JSON)")

    args = parser.parse_args()
    dry_run = not args.apply
    # 将 force 标志传递给 migrate
    print(f"迁移脚本启动，dry_run={dry_run}, force={args.force}, limit={args.limit}")
    migrate(
        dry_run=dry_run, limit=args.limit, report_path=args.report, force=args.force
    )


if __name__ == "__main__":
    main()
