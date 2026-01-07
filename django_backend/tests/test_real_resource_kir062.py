"""测试实际资源KIR-062的完整流程和字段值"""
import pytest
from loguru import logger


@pytest.mark.django_db
def test_kir062_full_workflow():
    """测试KIR-062的完整添加流程，验证所有字段"""
    from nassav.models import AVResource
    from nassav.resource_service import resource_service

    avid = "KIR-062"

    # 确保测试前数据库中没有该资源
    AVResource.objects.filter(avid=avid).delete()

    try:
        # 执行添加资源操作
        logger.info(f"\n{'='*60}")
        logger.info(f"开始测试资源: {avid}")
        logger.info(f"{'='*60}\n")

        result = resource_service.add_resource(
            avid=avid,
            source="any",
            scrape=True,
            download_cover=True,
            submit_translate=False,  # 不提交翻译任务
        )

        # 从数据库重新获取资源
        resource = AVResource.objects.get(avid=avid)

        logger.info(f"\n{'='*60}")
        logger.info("字段验证结果:")
        logger.info(f"{'='*60}\n")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. 验证基本字段
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("1. 基本字段:")
        logger.info(f"   avid: {resource.avid}")
        assert resource.avid == avid, f"AVID错误: {resource.avid}"

        logger.info(f"   source: {resource.source}")
        assert resource.source, "source字段为空"
        assert resource.source in [
            "Jable",
            "MissAV",
            "Memo",
        ], f"未知的source: {resource.source}"

        logger.info(
            f"   m3u8: {resource.m3u8[:50]}..." if resource.m3u8 else "   m3u8: (空)"
        )
        assert resource.m3u8, "m3u8字段为空"

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2. 验证标题字段（重点检查）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("\n2. 标题字段（重点）:")

        logger.info(f"   source_title: {resource.source_title}")
        assert resource.source_title, "❌ source_title字段为空"
        assert resource.source_title.startswith(
            avid
        ), f"❌ source_title未以{avid}开头: {resource.source_title}"
        logger.info(f"   ✓ source_title正确且以{avid}开头")

        logger.info(f"   original_title: {resource.original_title}")
        assert resource.original_title, "❌ original_title字段为空"
        logger.info(f"   ✓ original_title已设置")

        logger.info(f"   translated_title: {resource.translated_title or '(未翻译)'}")
        logger.info(f"   translation_status: {resource.translation_status}")
        # translation_status应该是pending，因为我们没有提交翻译任务
        assert resource.translation_status in [
            "pending",
            "skipped",
        ], f"意外的translation_status: {resource.translation_status}"

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3. 验证元数据字段
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("\n3. 元数据字段:")
        logger.info(f"   release_date: {resource.release_date}")
        assert resource.release_date, "release_date字段为空"

        logger.info(
            f"   duration: {resource.duration} 秒 ({resource.duration // 60} 分钟)"
        )
        assert resource.duration > 0, "duration字段为0"
        assert isinstance(
            resource.duration, int
        ), f"duration类型错误: {type(resource.duration)}"

        logger.info(f"   cover_filename: {resource.cover_filename}")
        assert (
            resource.cover_filename == f"{avid}.jpg"
        ), f"cover_filename错误: {resource.cover_filename}"

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4. 验证metadata JSON字段
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("\n4. metadata字段结构:")
        assert resource.metadata is not None, "metadata字段为空"
        metadata = resource.metadata

        # 验证必需字段
        required_fields = ["m3u8", "avid", "source", "title"]
        logger.info(f"   必需字段: {required_fields}")
        for field in required_fields:
            assert field in metadata, f"metadata缺少字段: {field}"
            logger.info(f"   ✓ {field}: {str(metadata[field])[:50]}...")

        # 验证可选的刮削字段
        optional_fields = [
            "release_date",
            "duration",
            "director",
            "studio",
            "label",
            "series",
            "genres",
            "actors",
            "actor_avatars",
        ]
        logger.info(f"\n   可选刮削字段:")
        for field in optional_fields:
            if field in metadata:
                value = metadata[field]
                if isinstance(value, list):
                    logger.info(f"   ✓ {field}: {len(value)} 项")
                elif isinstance(value, dict):
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
            for actor in resource.actors.all()[:5]:  # 只显示前5个
                logger.info(f"     - {actor.name}")

        if genres_count > 0:
            logger.info("   类别列表:")
            for genre in resource.genres.all()[:5]:  # 只显示前5个
                logger.info(f"     - {genre.name}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 6. 验证metadata与数据库字段的一致性
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info("\n6. 字段一致性检查:")

        # metadata中的title应该等于数据库的original_title
        if "title" in metadata and metadata["title"]:
            assert (
                metadata["title"] == resource.original_title
            ), f"metadata.title ({metadata['title']}) != original_title ({resource.original_title})"
            logger.info(f"   ✓ metadata.title == original_title")

        # metadata中的release_date应该等于数据库的release_date
        if "release_date" in metadata and metadata["release_date"]:
            assert (
                metadata["release_date"] == resource.release_date
            ), f"metadata.release_date != release_date"
            logger.info(f"   ✓ metadata.release_date == release_date")

        # metadata中的m3u8应该等于数据库的m3u8
        if "m3u8" in metadata and metadata["m3u8"]:
            assert metadata["m3u8"] == resource.m3u8, f"metadata.m3u8 != m3u8"
            logger.info(f"   ✓ metadata.m3u8 == m3u8")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 7. 详细打印metadata内容（用于调试）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        logger.info(f"\n7. 完整metadata内容:")
        import json

        logger.info(json.dumps(metadata, ensure_ascii=False, indent=2))

        logger.info(f"\n{'='*60}")
        logger.info("✓ 所有字段验证通过")
        logger.info(f"{'='*60}\n")

    finally:
        # 清理：删除测试数据
        logger.info(f"\n{'='*60}")
        logger.info("清理测试数据...")
        deleted_count, _ = AVResource.objects.filter(avid=avid).delete()
        logger.info(f"已删除 {deleted_count} 条记录")
        logger.info(f"{'='*60}\n")
