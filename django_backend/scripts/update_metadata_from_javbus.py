#!/usr/bin/env python
"""
使用 Javbus 更新现有资源的元数据

功能：
1. 扫描 resource 目录下的所有资源文件夹
2. 读取现有的 JSON 元数据
3. 使用 Javbus 刮削新的元数据
4. 合并/更新元数据（保留原有的 m3u8、source 等字段）
5. 保存更新后的元数据

用法：
    python scripts/update_metadata_from_javbus.py [选项]

选项：
    --avid AVID           只更新指定的 AVID
    --dry-run             预览模式，不实际写入文件
    --force               强制更新所有字段（不保留原有值）
    --delay SECONDS       每次请求之间的延迟（默认 2 秒）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')

import django
django.setup()

from loguru import logger
from django.conf import settings

from nassav.scraper.Javbus import Javbus


# 配置 loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level="INFO"
)


def get_proxy() -> str | None:
    """从配置获取代理"""
    proxy_config = settings.CONFIG.get('Proxy', {})
    if proxy_config.get('Enable', False):
        return proxy_config.get('url')
    return None


def get_resource_dirs(resource_path: Path) -> list[Path]:
    """获取所有资源目录"""
    if not resource_path.exists():
        logger.error(f"资源目录不存在: {resource_path}")
        return []

    dirs = []
    for item in resource_path.iterdir():
        if item.is_dir():
            dirs.append(item)
    return sorted(dirs)


def load_metadata(json_path: Path) -> dict | None:
    """加载现有的元数据 JSON"""
    if not json_path.exists():
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"解析 JSON 失败 {json_path}: {e}")
        return None


def save_metadata(json_path: Path, metadata: dict):
    """保存元数据到 JSON"""
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def merge_metadata(original: dict, scraped: dict, force: bool = False) -> dict:
    """
    合并元数据

    原则：
    - 保留原有的 m3u8、source 字段（这些是本地特有的）
    - 如果 force=False，只更新原来为空的字段
    - 如果 force=True，用刮削的数据覆盖所有字段
    """
    # 需要保留的本地字段
    local_fields = ['m3u8', 'source']

    # 字段映射（Javbus -> 本地 JSON）
    field_mapping = {
        'avid': 'avid',
        'title': 'title',
        'release_date': 'release_date',
        'duration': 'duration',
        'producer': 'studio',      # Javbus 的 producer 对应 studio
        'publisher': 'label',      # Javbus 的 publisher 对应 label
        'series': 'series',
        'genres': 'genres',
        'actors': 'actors',
        'director': 'director',
    }

    result = original.copy()

    for scraped_key, local_key in field_mapping.items():
        scraped_value = scraped.get(scraped_key)

        # 跳过空值
        if not scraped_value:
            continue

        # 跳过本地专有字段
        if local_key in local_fields:
            continue

        # 获取原始值
        original_value = original.get(local_key)

        # 决定是否更新
        if force:
            # 强制模式：直接覆盖
            result[local_key] = scraped_value
        else:
            # 非强制模式：只更新空值
            if not original_value or (isinstance(original_value, list) and len(original_value) == 0):
                result[local_key] = scraped_value

    return result


def update_single_resource(
    avid: str,
    resource_path: Path,
    scraper: Javbus,
    dry_run: bool = False,
    force: bool = False
) -> bool:
    """
    更新单个资源的元数据

    返回是否成功更新
    """
    resource_dir = resource_path / avid
    json_path = resource_dir / f"{avid}.json"

    # 检查资源目录是否存在
    if not resource_dir.exists():
        logger.warning(f"资源目录不存在: {resource_dir}")
        return False

    # 加载现有元数据
    original_metadata = load_metadata(json_path)
    if original_metadata is None:
        logger.warning(f"未找到元数据文件: {json_path}")
        return False

    # 从 Javbus 刮削元数据
    logger.info(f"正在刮削 {avid} 的元数据...")
    scraped_metadata = scraper.scrape(avid)

    if scraped_metadata is None:
        logger.error(f"无法从 Javbus 获取 {avid} 的元数据")
        return False

    # 合并元数据
    merged_metadata = merge_metadata(original_metadata, scraped_metadata, force)

    # 显示变更
    logger.info(f"--- {avid} 元数据变更 ---")
    for key in merged_metadata:
        old_val = original_metadata.get(key)
        new_val = merged_metadata.get(key)
        if old_val != new_val:
            logger.info(f"  {key}: {old_val} -> {new_val}")

    # 保存（如果不是预览模式）
    if not dry_run:
        save_metadata(json_path, merged_metadata)
        logger.info(f"✓ 已更新 {avid} 的元数据")
    else:
        logger.info(f"[预览] 将更新 {avid} 的元数据")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='使用 Javbus 更新现有资源的元数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 更新所有资源
  %(prog)s --avid SSIS-075          # 只更新指定资源
  %(prog)s --dry-run                # 预览模式
  %(prog)s --force                  # 强制更新所有字段
  %(prog)s --delay 3                # 设置请求间隔为 3 秒
        """
    )
    parser.add_argument('--avid', type=str, help='只更新指定的 AVID')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际写入文件')
    parser.add_argument('--force', action='store_true', help='强制更新所有字段')
    parser.add_argument('--delay', type=float, default=2.0, help='每次请求之间的延迟（秒）')

    args = parser.parse_args()

    # 资源目录
    resource_path = project_root / 'resource'

    # 初始化刮削器
    proxy = get_proxy()
    scraper = Javbus(proxy=proxy)

    logger.info(f"资源目录: {resource_path}")
    logger.info(f"代理: {proxy or '未启用'}")
    logger.info(f"预览模式: {'是' if args.dry_run else '否'}")
    logger.info(f"强制更新: {'是' if args.force else '否'}")
    logger.info(f"请求延迟: {args.delay}秒")
    logger.info("-" * 50)

    # 确定要处理的资源列表
    if args.avid:
        avids = [args.avid.upper()]
    else:
        resource_dirs = get_resource_dirs(resource_path)
        avids = [d.name for d in resource_dirs]

    logger.info(f"将处理 {len(avids)} 个资源")

    # 统计
    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, avid in enumerate(avids, 1):
        logger.info(f"\n[{i}/{len(avids)}] 处理 {avid}")

        # 检查是否存在 JSON 文件
        json_path = resource_path / avid / f"{avid}.json"
        if not json_path.exists():
            logger.info(f"跳过 {avid}：无元数据文件")
            skip_count += 1
            continue

        try:
            if update_single_resource(
                avid=avid,
                resource_path=resource_path,
                scraper=scraper,
                dry_run=args.dry_run,
                force=args.force
            ):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"处理 {avid} 时发生错误: {e}")
            fail_count += 1

        # 请求延迟（避免频繁请求）
        if i < len(avids) and not args.dry_run:
            time.sleep(args.delay)

    # 输出统计
    logger.info("\n" + "=" * 50)
    logger.info(f"处理完成！")
    logger.info(f"  成功: {success_count}")
    logger.info(f"  失败: {fail_count}")
    logger.info(f"  跳过: {skip_count}")


if __name__ == '__main__':
    main()
