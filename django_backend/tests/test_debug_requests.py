"""
测试 HTTP 请求的 Debug 输出

目的：验证所有请求参数（proxy, cookie, referer, impersonate等）是否正确打印到日志
"""
import os
import sys

import django

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置 Django 环境
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

import logging

from loguru import logger
from nassav.source.SourceManager import source_manager


def test_fetch_html_debug():
    """测试获取 HTML 时的 debug 输出"""
    print("\n" + "=" * 100)
    print("测试 1: 获取资源 HTML (SourceManager.get_info_from_any_source)")
    print("=" * 100 + "\n")

    # 使用已知存在的 AVID（请根据实际情况修改）
    test_avid = "SSIS-001"

    # 配置日志级别为 DEBUG（确保 debug 日志能输出）
    logger.remove()
    logger.add(
        sys.stdout,
        level="DEBUG",
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    )

    print(f"开始测试获取 {test_avid} 的信息...\n")

    # 执行获取
    info, source_inst, html, errors = source_manager.get_info_from_any_source(test_avid)

    print("\n" + "-" * 100)
    print("测试结果:")
    print("-" * 100)

    if info:
        print(f"✅ 成功获取资源信息")
        print(f"   源: {source_inst.get_source_name() if source_inst else 'Unknown'}")
        print(f"   标题: {info.title}")
        print(f"   M3U8: {info.m3u8[:50]}..." if info.m3u8 else "   M3U8: (未获取)")
        print(f"   HTML 长度: {len(html)} 字符" if html else "   HTML: (未获取)")
    else:
        print(f"❌ 获取失败")
        print(f"   错误: {errors}")

    print("\n" + "=" * 100 + "\n")


def test_scraper_debug():
    """测试刮削器的 debug 输出"""
    print("\n" + "=" * 100)
    print("测试 2: 刮削 Javbus 元数据 (ScraperManager.scrape)")
    print("=" * 100 + "\n")

    from django.conf import settings
    from nassav.scraper import ScraperManager

    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    scraper = ScraperManager(proxy)

    test_avid = "SSIS-001"

    print(f"开始测试刮削 {test_avid} 的元数据...\n")

    # 执行刮削
    metadata = scraper.scrape(test_avid)

    print("\n" + "-" * 100)
    print("测试结果:")
    print("-" * 100)

    if metadata:
        print(f"✅ 成功刮削元数据")
        print(f"   标题: {metadata.get('title')}")
        print(f"   发行日期: {metadata.get('release_date')}")
        print(f"   时长: {metadata.get('duration')}")
        print(f"   演员: {metadata.get('actors', [])[:3]}...")  # 只显示前3个
        print(f"   类别: {metadata.get('genres', [])[:5]}...")  # 只显示前5个
        print(f"   封面URL: {metadata.get('cover_url')}")
    else:
        print(f"❌ 刮削失败")

    print("\n" + "=" * 100 + "\n")


def test_download_cover_debug():
    """测试下载封面的 debug 输出"""
    print("\n" + "=" * 100)
    print("测试 3: 下载封面图片 (ScraperBase.download_cover)")
    print("=" * 100 + "\n")

    import tempfile
    from pathlib import Path

    from django.conf import settings
    from nassav.scraper import ScraperManager

    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    scraper = ScraperManager(proxy)

    test_avid = "SSIS-001"

    # 先刮削获取封面 URL
    metadata = scraper.scrape(test_avid)

    if metadata and metadata.get("cover_url"):
        cover_url = metadata["cover_url"]
        print(f"封面 URL: {cover_url}\n")

        # 使用临时文件测试下载
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            temp_path = tmp.name

        print(f"开始测试下载封面到临时路径: {temp_path}\n")

        # 获取第一个可用的 scraper 实例
        scrapers = scraper.get_scrapers()
        if scrapers:
            _, scraper_instance = scrapers[0]
            success = scraper_instance.download_cover(cover_url, temp_path)

            print("\n" + "-" * 100)
            print("测试结果:")
            print("-" * 100)

            if success:
                file_size = os.path.getsize(temp_path)
                print(f"✅ 封面下载成功")
                print(f"   文件大小: {file_size} bytes ({file_size / 1024:.2f} KB)")
                print(f"   临时路径: {temp_path}")

                # 清理临时文件
                try:
                    os.remove(temp_path)
                    print(f"   已清理临时文件")
                except:
                    pass
            else:
                print(f"❌ 封面下载失败")
        else:
            print("❌ 没有可用的刮削器实例")
    else:
        print(f"❌ 未获取到封面 URL")

    print("\n" + "=" * 100 + "\n")


def main():
    """运行所有测试"""
    print("\n" + "█" * 100)
    print("█" + " " * 98 + "█")
    print("█" + " " * 30 + "HTTP 请求 Debug 测试套件" + " " * 44 + "█")
    print("█" + " " * 98 + "█")
    print("█" * 100 + "\n")

    print("📝 说明: 此测试将显示所有 HTTP 请求的详细参数（proxy, cookie, referer, impersonate 等）")
    print("🎯 目的: 验证 debug 日志是否正确记录请求参数\n")

    input("按 Enter 键开始测试...")

    try:
        # 测试 1: 获取资源 HTML
        test_fetch_html_debug()

        input("\n按 Enter 键继续下一个测试...")

        # 测试 2: 刮削元数据
        test_scraper_debug()

        input("\n按 Enter 键继续下一个测试...")

        # 测试 3: 下载封面
        test_download_cover_debug()

        print("\n" + "█" * 100)
        print("█" + " " * 98 + "█")
        print("█" + " " * 40 + "测试完成！" + " " * 48 + "█")
        print("█" + " " * 98 + "█")
        print("█" * 100 + "\n")

        print("✅ 所有测试已完成")
        print("📋 请检查上方的 DEBUG 日志输出，确认所有请求参数是否正确显示")

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
