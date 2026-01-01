"""管理命令：import_resources

用法示例：
  python manage.py import_resources --dry-run --limit 100
  python manage.py import_resources --backup

功能：遍历 settings.RESOURCE_DIR 下的子目录，读取 {avid}.json 并写入 AVResource/Actor/Genre。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from nassav.models import AVResource, Actor, Genre


def _parse_int_duration(dur) -> int | None:
    if dur is None:
        return None
    if isinstance(dur, int):
        return dur
    s = str(dur)
    # 尝试提取数字（分钟/秒）
    import re
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    n = int(m.group(1))
    # 如果包含 '分' 或 '分钟'，视为分钟
    if '分' in s or '分钟' in s:
        return n * 60
    # 否则作为分钟转换（保守处理）
    return n * 60


class Command(BaseCommand):
    help = 'Import resources from resource/ JSON files into database'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Do not write to DB, only simulate')
        parser.add_argument('--backup', action='store_true', help='Backup original json/html to resource_backup/')
        parser.add_argument('--limit', type=int, default=0,
                            help='Limit number of resources to import (0 means no limit)')
        parser.add_argument('--skip-missing-json', action='store_true', help='Skip directories without JSON files')
        parser.add_argument('--force', action='store_true', help='Force overwrite existing DB records')

    def handle(self, *args, **options):
        dry_run: bool = options.get('dry_run', False)
        do_backup: bool = options.get('backup', False)
        limit: int = options.get('limit', 0)
        skip_missing = options.get('skip_missing_json', False)

        resource_dir: Path = getattr(settings, 'RESOURCE_DIR', None)
        if resource_dir is None:
            self.stderr.write('settings.RESOURCE_DIR 未配置')
            return

        if not resource_dir.exists():
            self.stderr.write(f'Resource dir 不存在: {resource_dir}')
            return

        backup_root = Path(settings.BASE_DIR) / 'resource_backup' / datetime.date.today().isoformat()
        if do_backup:
            backup_root.mkdir(parents=True, exist_ok=True)

        processed = 0
        skipped = 0
        errors: List[str] = []

        for item in sorted(resource_dir.iterdir()):
            if limit and processed >= limit:
                break
            if not item.is_dir():
                continue

            avid = item.name.upper()
            json_path = item / f"{avid}.json"
            html_path = item / f"{avid}.html"

            # DB-first: 如果 DB 中已存在记录，默认跳过（除非 --force）
            try:
                existing = AVResource.objects.filter(avid=avid).first()
            except Exception:
                existing = None

            if existing and not options.get('force'):
                self.stdout.write(f'已存在 DB 记录，跳过 {avid}（使用 --force 强制覆盖）')
                skipped += 1
                continue

            if not json_path.exists():
                if skip_missing and not existing:
                    skipped += 1
                    continue
                # 若 JSON 不存在但 DB 有记录，则我们仍可更新文件信息（mp4/cover）
                if not json_path.exists() and not existing:
                    self.stdout.write(f'警告: {avid} 缺失 JSON, 跳过')
                    skipped += 1
                    continue

            data = None
            if json_path.exists():
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception as e:
                    errors.append(f'{avid}: 读取 JSON 失败: {e}')
                    continue

            # 解析常用字段（兼容性处理）
            title = data.get('title') or data.get('name') or ''
            source = data.get('source') or data.get('downloader') or ''
            release_date = data.get('release_date') or data.get('release') or ''
            duration_raw = data.get('duration') or data.get('time') or None
            duration = _parse_int_duration(duration_raw)
            m3u8 = data.get('m3u8') or data.get('m3u8_url') or data.get('play_url') or None

            # actors/genres 可能为逗号分隔字符串或列表
            def _ensure_list(v):
                if v is None:
                    return []
                if isinstance(v, list):
                    return [str(x).strip() for x in v if x]
                if isinstance(v, str):
                    return [x.strip() for x in v.split(',') if x.strip()]
                return []

            actors_list = _ensure_list(data.get('actors') or data.get('cast') or data.get('starring'))
            genres_list = _ensure_list(data.get('genres') or data.get('categories') or data.get('tags'))

            # 检查封面文件（新布局：COVER_DIR/{AVID}.jpg）
            cover_filename = None
            for ext in ('.jpg', '.jpeg', '.png', '.webp'):
                p = Path(settings.COVER_DIR) / f"{avid}{ext}"
                if p.exists():
                    cover_filename = p.name
                    break

            # 检查 mp4（新布局：VIDEO_DIR/{AVID}.mp4）
            mp4_path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"
            file_exists = mp4_path.exists()
            file_size = mp4_path.stat().st_size if file_exists else None

            if do_backup:
                try:
                    dest = backup_root / avid
                    dest.mkdir(parents=True, exist_ok=True)
                    if json_path.exists():
                        shutil.copy2(json_path, dest / json_path.name)
                    # 备份原来可能存在的封面与 mp4（来自旧布局）
                    old_cover = item / f"{avid}.jpg"
                    old_mp4 = item / f"{avid}.mp4"
                    if old_cover.exists():
                        shutil.copy2(old_cover, dest / old_cover.name)
                    if old_mp4.exists():
                        shutil.copy2(old_mp4, dest / old_mp4.name)
                except Exception as e:
                    self.stdout.write(f'备份 {avid} 失败: {e}')

            if dry_run:
                if data is not None:
                    self.stdout.write(
                        f'[dry-run] 导入 {avid}: title="{title}", actors={actors_list}, genres={genres_list}, file_exists={file_exists}')
                else:
                    self.stdout.write(
                        f'[dry-run] 更新文件状态 {avid}: file_exists={file_exists}, cover={cover_filename}')
                processed += 1
                continue

            # 写入 DB
            try:
                with transaction.atomic():
                    defaults = {
                        'title': title,
                        'source': source,
                        'release_date': release_date,
                        'duration': duration,
                        'metadata': data,
                        'm3u8': m3u8,
                        'cover_filename': cover_filename,
                        'file_exists': file_exists,
                        'file_size': file_size,
                    }

                    if existing and options.get('force'):
                        # 覆盖已有记录
                        resource, created = AVResource.objects.update_or_create(avid=avid, defaults=defaults)
                    elif existing and not data:
                        # 仅更新文件信息
                        resource = existing
                        resource.file_exists = file_exists
                        resource.file_size = file_size
                        if cover_filename:
                            resource.cover_filename = cover_filename
                        resource.save()
                        created = False
                    else:
                        resource, created = AVResource.objects.update_or_create(avid=avid, defaults=defaults)

                    # actors
                    if data is not None:
                        resource.actors.clear()
                        for a in actors_list:
                            actor_obj, _ = Actor.objects.get_or_create(name=a)
                            resource.actors.add(actor_obj)

                        # genres
                        resource.genres.clear()
                        for g in genres_list:
                            genre_obj, _ = Genre.objects.get_or_create(name=g)
                            resource.genres.add(genre_obj)

                    # ensure timestamps
                    if file_exists:
                        resource.video_saved_at = datetime.datetime.fromtimestamp(mp4_path.stat().st_mtime)
                        resource.file_size = file_size
                    resource.save()

                processed += 1
                self.stdout.write(f'已导入或更新 {avid} (created={created})')
            except Exception as e:
                errors.append(f'{avid}: 写入 DB 失败: {e}')

        self.stdout.write('\n导入完成。')
        self.stdout.write(f'已处理: {processed}, 跳过: {skipped}, 错误: {len(errors)}')
        if errors:
            self.stdout.write('\n错误详情:')
            for e in errors:
                self.stderr.write(f'  - {e}')
