#!/usr/bin/env python3
"""
资源文件迁移脚本（历史脚本）

警告：
    此脚本用于早期文件结构迁移，已经不再需要。
    现在的文件结构：
    - resource/cover/{AVID}.{ext}  - 封面图片
    - resource/video/{AVID}.mp4    - 视频文件

原功能：
    从 resource_backup/{AVID}/ 目录中迁移文件到新的结构：
    - 封面拷贝到 resource/cover/{AVID}.{ext}
    - 视频拷贝到 resource/video/{AVID}.mp4

历史用法：
    # 预览模式
    python scripts/migrate_resource_paths.py --dry-run

    # 实际执行
    python scripts/migrate_resource_paths.py --apply

    # 强制覆盖 + 限制数量
    python scripts/migrate_resource_paths.py --apply --force --limit 10

    # 生成报告
    python scripts/migrate_resource_paths.py --apply --report migration_report.json

注意：
    - 新项目不需要执行此脚本
    - 仅保留作为历史参考
"""

from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from typing import Optional

IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'JPG', 'JPEG', 'PNG', 'WEBP']


def find_cover_in_dir(d: Path) -> Optional[Path]:
    """查找可能的封面文件，优先按 {avid}.{ext} 名称匹配"""
    if not d.exists() or not d.is_dir():
        return None
    name = d.name
    # 1) 尝试 name.ext
    for ext in IMAGE_EXTS:
        p = d / f"{name}.{ext}"
        if p.exists():
            return p
    # 2) 尝试任意图片文件
    for p in d.iterdir():
        if p.suffix.lstrip('.').lower() in [e.lower() for e in IMAGE_EXTS] and p.is_file():
            return p
    return None


def find_mp4_in_dir(d: Path) -> Optional[Path]:
    name = d.name
    p = d / f"{name}.mp4"
    if p.exists():
        return p
    # 备选：任意 mp4
    for f in d.glob('*.mp4'):
        if f.is_file():
            return f
    return None


def main():
    parser = argparse.ArgumentParser(description='Migrate resource files from resource_backup to new layout')
    parser.add_argument('--apply', action='store_true', help='Perform actual file copy (default: dry-run)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing destination files')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of dirs to process (0 = all)')
    parser.add_argument('--report', type=str, default=None, help='Write JSON report to file')

    args = parser.parse_args()
    do_apply = args.apply
    do_force = args.force
    limit = args.limit or None
    report_path = args.report

    root = Path(__file__).resolve().parents[1]
    src_root = root / 'resource_backup'
    dst_root = root / 'resource'
    cover_root = dst_root / 'cover'
    video_root = dst_root / 'video'

    cover_root.mkdir(parents=True, exist_ok=True)
    video_root.mkdir(parents=True, exist_ok=True)

    if not src_root.exists():
        print(f"Source resource_backup not found: {src_root}")
        return

    entries = [p for p in sorted(src_root.iterdir()) if p.is_dir()]
    total = len(entries)
    if limit:
        entries = entries[:limit]

    summary = {
        'total_dirs': total,
        'processed': 0,
        'copied': 0,
        'skipped': 0,
        'errors': [],
        'items': []
    }

    for i, d in enumerate(entries, start=1):
        avid = d.name
        avid_upper = avid.upper()
        cover_src = find_cover_in_dir(d)
        mp4_src = find_mp4_in_dir(d)

        item = {'avid': avid_upper, 'cover_src': str(cover_src) if cover_src else None,
                'mp4_src': str(mp4_src) if mp4_src else None, 'actions': []}

        if not cover_src and not mp4_src:
            item['note'] = 'no_files'
            summary['skipped'] += 1
            summary['items'].append(item)
            continue

        # cover dest
        if cover_src:
            ext = cover_src.suffix.lstrip('.')
            cover_dest = cover_root / f"{avid_upper}.{ext}"
            if cover_dest.exists() and not do_force:
                item['actions'].append({'type': 'cover', 'action': 'skip', 'dest': str(cover_dest)})
            else:
                item['actions'].append(
                    {'type': 'cover', 'action': 'copy' if do_apply else 'would_copy', 'src': str(cover_src),
                     'dest': str(cover_dest)})
                if do_apply:
                    try:
                        shutil.copy2(cover_src, cover_dest)
                        summary['copied'] += 1
                    except Exception as e:
                        summary['errors'].append({'avid': avid_upper, 'file': str(cover_src), 'error': str(e)})

        # mp4 dest
        if mp4_src:
            mp4_dest = video_root / f"{avid_upper}.mp4"
            if mp4_dest.exists() and not do_force:
                item['actions'].append({'type': 'mp4', 'action': 'skip', 'dest': str(mp4_dest)})
            else:
                item['actions'].append(
                    {'type': 'mp4', 'action': 'copy' if do_apply else 'would_copy', 'src': str(mp4_src),
                     'dest': str(mp4_dest)})
                if do_apply:
                    try:
                        shutil.copy2(mp4_src, mp4_dest)
                        summary['copied'] += 1
                    except Exception as e:
                        summary['errors'].append({'avid': avid_upper, 'file': str(mp4_src), 'error': str(e)})

        summary['processed'] += 1
        summary['items'].append(item)

        # print progress line
        print(f"[{i}/{len(entries)}] {avid_upper}: ", end='')
        acts = [a for a in item.get('actions', [])]
        if not acts:
            print('no actions')
        else:
            parts = []
            for a in acts:
                if a['type'] == 'cover':
                    if a['action'].startswith('would'):
                        parts.append(f"COVER->{Path(a['dest']).name}")
                    elif a['action'] == 'copy':
                        parts.append(f"COVER COPIED->{Path(a['dest']).name}")
                    else:
                        parts.append(f"COVER SKIP->{Path(a['dest']).name}")
                if a['type'] == 'mp4':
                    if a['action'].startswith('would'):
                        parts.append(f"MP4->{Path(a['dest']).name}")
                    elif a['action'] == 'copy':
                        parts.append(f"MP4 COPIED->{Path(a['dest']).name}")
                    else:
                        parts.append(f"MP4 SKIP->{Path(a['dest']).name}")
            print(', '.join(parts))

    # final summary
    print('\n=== Summary ===')
    print(f"Total dirs: {summary['total_dirs']}")
    print(f"Processed: {summary['processed']}")
    print(f"Copied files: {summary['copied']}")
    print(f"Skipped dirs: {summary['skipped']}")
    print(f"Errors: {len(summary['errors'])}")

    if report_path:
        try:
            with open(report_path, 'w', encoding='utf-8') as rf:
                json.dump(summary, rf, ensure_ascii=False, indent=2)
            print(f"Report written to {report_path}")
        except Exception as e:
            print(f"Failed to write report: {e}")


if __name__ == '__main__':
    main()
