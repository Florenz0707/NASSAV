#!/usr/bin/env python3
"""
演示脚本：测试从Javbus提取封面URL

用于确认封面URL在HTML中的位置和格式
"""

import os
import sys

import django

# 配置Django环境
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from loguru import logger
from nassav.scraper.Javbus import Javbus


def test_cover_extraction():
    """测试封面URL提取"""
    logger.info("=" * 60)
    logger.info("测试从Javbus提取封面URL")
    logger.info("=" * 60)

    test_avid = "ABP-001"
    scraper = Javbus()

    # 获取HTML
    logger.info(f"获取 {test_avid} 的HTML...")
    html = scraper.fetch_html(test_avid)

    if not html:
        logger.error("获取HTML失败")
        return False

    logger.info(f"HTML长度: {len(html)} 字符")

    # 查找封面URL相关的HTML结构
    import re

    # 尝试多种可能的模式
    patterns = [
        (r'<a[^>]*class="bigImage"[^>]*href="([^"]+)"', "bigImage class"),
        (r'<a[^>]*href="([^"]+)"[^>]*class="bigImage"', "bigImage class (reverse)"),
        (r'<img[^>]*id="video_jacket_img"[^>]*src="([^"]+)"', "video_jacket_img id"),
        (r'<img[^>]*class="video-jacket"[^>]*src="([^"]+)"', "video-jacket class"),
        (r'<div[^>]*class="screencap"[^>]*>.*?<img[^>]*src="([^"]+)"', "screencap div"),
    ]

    logger.info("\n尝试不同的正则模式:")
    for pattern, desc in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            url = match.group(1)
            logger.info(f"✓ [{desc}] 找到: {url}")
        else:
            logger.info(f"✗ [{desc}] 未找到")

    # 查找所有包含.jpg的img标签
    logger.info("\n查找所有.jpg图片:")
    img_matches = re.findall(r'<img[^>]*src="([^"]+\.jpg[^"]*)"', html)
    for i, img in enumerate(img_matches[:5], 1):  # 只显示前5个
        logger.info(f"  {i}. {img}")

    if len(img_matches) > 5:
        logger.info(f"  ... 还有 {len(img_matches) - 5} 个")

    logger.info("\n测试完成")
    return True


if __name__ == "__main__":
    try:
        test_cover_extraction()
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"测试失败: {e}")
        sys.exit(1)
