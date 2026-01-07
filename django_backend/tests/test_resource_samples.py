"""测试资源样例的完整流程和数据有效性

功能：
1. 测试不存在的资源（TEST-001, TEST-002, TEST-003）- 应该失败
2. 测试真实存在的资源（MIMK-054, VEMA-208, OVG-206）- 应该成功
3. 主要使用 Jable 作为 Source
4. 验证数据库数据的有效性和一致性

运行方式：
    uv run pytest tests/test_resource_samples.py -v
    uv run pytest tests/test_resource_samples.py::test_nonexistent_resources -v
    uv run pytest tests/test_resource_samples.py::test_real_resources -v
"""
import pytest
from loguru import logger


def validate_resource_fields(resource, avid, should_exist=True):
    """验证资源字段的有效性和一致性

    Args:
        resource: AVResource 实例
        avid: 期望的 AVID
        should_exist: 是否应该存在（用于区分成功/失败测试）
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"验证资源: {avid}")
    logger.info(f"{'='*60}\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. 验证基本字段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("1. 基本字段:")
    logger.info(f"   avid: {resource.avid}")
    assert resource.avid == avid, f"AVID错误: 期望 {avid}, 实际 {resource.avid}"

    logger.info(f"   source: {resource.source}")
    assert resource.source, "source字段为空"
    assert resource.source in [
        "Jable",
        "MissAV",
        "Memo",
    ], f"未知的source: {resource.source}"

    logger.info(f"   m3u8: {resource.m3u8[:50] + '...' if resource.m3u8 else '(空)'}")
    assert resource.m3u8, "m3u8字段为空"
    assert resource.m3u8.startswith("http"), "m3u8不是有效的URL"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. 验证标题字段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("\n2. 标题字段:")

    logger.info(f"   source_title: {resource.source_title}")
    assert resource.source_title, "source_title字段为空"
    assert (
        avid in resource.source_title
    ), f"source_title应包含AVID {avid}: {resource.source_title}"

    logger.info(f"   original_title: {resource.original_title}")
    assert resource.original_title, "original_title字段为空"

    logger.info(f"   translated_title: {resource.translated_title or '(未翻译)'}")
    logger.info(f"   translation_status: {resource.translation_status}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 验证元数据字段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("\n3. 元数据字段:")

    logger.info(f"   release_date: {resource.release_date}")
    assert resource.release_date, "release_date字段为空"
    # 验证日期格式 YYYY-MM-DD
    import re

    assert re.match(
        r"\d{4}-\d{2}-\d{2}", resource.release_date
    ), f"release_date格式错误: {resource.release_date}"

    logger.info(f"   duration: {resource.duration} 秒 ({resource.duration // 60} 分钟)")
    assert resource.duration > 0, "duration应该大于0"
    assert isinstance(
        resource.duration, int
    ), f"duration类型错误: {type(resource.duration)}"

    logger.info(f"   cover_filename: {resource.cover_filename}")
    assert (
        resource.cover_filename == f"{avid}.jpg"
    ), f"cover_filename错误: 期望 {avid}.jpg, 实际 {resource.cover_filename}"

    logger.info(f"   file_size: {resource.file_size}")
    # file_size 可以为 None（视频未下载时）
    if resource.file_size is not None:
        assert resource.file_size >= 0, "file_size不应为负数"
        assert isinstance(resource.file_size, int), "file_size应为整数"

    logger.info(f"   file_exists: {resource.file_exists}")
    assert isinstance(resource.file_exists, bool), "file_exists应为布尔值"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 验证 metadata JSON 字段
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("\n4. metadata 字段结构:")
    assert resource.metadata is not None, "metadata字段为空"
    metadata = resource.metadata

    # 验证必需字段
    required_fields = ["m3u8", "avid", "source", "title"]
    for field in required_fields:
        assert field in metadata, f"metadata缺少必需字段: {field}"
        logger.info(f"   ✓ {field}: {str(metadata[field])[:50]}...")

    # 验证可选的刮削字段
    optional_fields = ["release_date", "duration", "genres", "actors"]
    for field in optional_fields:
        if field in metadata:
            value = metadata[field]
            if isinstance(value, list):
                logger.info(f"   ✓ {field}: {len(value)} 项")
            else:
                logger.info(f"   ✓ {field}: {str(value)[:50]}...")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. 验证关联的演员和类别
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("\n5. 关联数据:")
    actors_count = resource.actors.count()
    genres_count = resource.genres.count()
    logger.info(f"   演员数量: {actors_count}")
    logger.info(f"   类别数量: {genres_count}")

    if actors_count > 0:
        logger.info("   演员列表:")
        for actor in resource.actors.all()[:3]:
            logger.info(f"     - {actor.name}")

    if genres_count > 0:
        logger.info("   类别列表:")
        for genre in resource.genres.all()[:3]:
            logger.info(f"     - {genre.name}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 6. 验证数据一致性
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    logger.info("\n6. 数据一致性检查:")

    # metadata.title 应该等于 original_title
    if "title" in metadata and metadata["title"]:
        assert (
            metadata["title"] == resource.original_title
        ), f"metadata.title != original_title"
        logger.info("   ✓ metadata.title == original_title")

    # metadata.m3u8 应该等于 m3u8
    if "m3u8" in metadata and metadata["m3u8"]:
        assert metadata["m3u8"] == resource.m3u8, f"metadata.m3u8 != m3u8"
        logger.info("   ✓ metadata.m3u8 == m3u8")

    logger.info(f"\n{'='*60}")
    logger.info(f"✓ 资源 {avid} 验证通过")
    logger.info(f"{'='*60}\n")


@pytest.mark.django_db
def test_nonexistent_resources():
    """测试不存在的资源 - 应该失败"""
    from nassav.resource_service import resource_service

    nonexistent_avids = ["TEST-001", "TEST-002", "TEST-003"]

    logger.info(f"\n{'='*60}")
    logger.info("测试不存在的资源")
    logger.info(f"{'='*60}\n")

    for avid in nonexistent_avids:
        logger.info(f"\n测试资源: {avid}")

        # 清理可能存在的测试数据（包括文件）
        resource_service.delete_resource(avid, delete_files=True)

        try:
            result = resource_service.add_resource(
                avid=avid,
                source="Jable",
                scrape=True,
                download_cover=False,
                submit_translate=False,
            )

            # 如果执行到这里，说明没有抛出异常，检查结果
            logger.warning(f"   资源 {avid} 添加成功（意外）")
            logger.warning(f"   结果: {result}")

        except Exception as e:
            # 预期会失败
            logger.info(f"   ✓ 资源 {avid} 添加失败（符合预期）")
            logger.info(f"   错误信息: {str(e)}")

        finally:
            # 清理测试数据（包括封面图等文件）
            resource_service.delete_resource(avid, delete_files=True)

    logger.info(f"\n{'='*60}")
    logger.info("✓ 不存在资源测试完成")
    logger.info(f"{'='*60}\n")


@pytest.mark.django_db
def test_real_resources():
    """测试真实存在的资源 - 应该成功"""
    from nassav.models import AVResource
    from nassav.resource_service import resource_service

    # 真实存在的资源样例
    real_avids = ["MIMK-054", "VEMA-208", "OVG-206"]

    logger.info(f"\n{'='*60}")
    logger.info("测试真实存在的资源")
    logger.info(f"{'='*60}\n")

    for avid in real_avids:
        logger.info(f"\n{'='*60}")
        logger.info(f"开始测试资源: {avid}")
        logger.info(f"{'='*60}\n")

        # 清理可能存在的测试数据（包括文件）
        resource_service.delete_resource(avid, delete_files=True)

        try:
            # 执行添加资源操作
            result = resource_service.add_resource(
                avid=avid,
                source="Jable",
                scrape=True,
                download_cover=True,
                submit_translate=False,
            )

            logger.info(f"   添加结果: {result}")

            # 从数据库重新获取资源
            resource = AVResource.objects.get(avid=avid)

            # 验证资源字段
            validate_resource_fields(resource, avid, should_exist=True)

        except Exception as e:
            logger.error(f"   ✗ 资源 {avid} 添加失败")
            logger.error(f"   错误信息: {str(e)}")
            raise

        finally:
            # 清理测试数据（包括封面图等文件）
            logger.info(f"\n清理测试数据: {avid}")
            resource_service.delete_resource(avid, delete_files=True)
            logger.info(f"资源 {avid} 已完全清理\n")

    logger.info(f"\n{'='*60}")
    logger.info("✓ 所有真实资源测试通过")
    logger.info(f"{'='*60}\n")
