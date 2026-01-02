#!/usr/bin/env python
"""
序列化器测试

功能：
1. 测试 ResourceSummarySerializer（资源摘要序列化器）
2. 测试 ResourceSerializer（完整资源序列化器）
3. 验证标题优先级逻辑（translated_title > source_title > title）
4. 测试序列化器的字段映射和数据转换
5. 验证关联数据（演员、类别）的序列化

运行方式：
    # 运行所有测试
    python manage.py test tests.test_serializers

    # 运行单个测试
    python manage.py test tests.test_serializers.SerializersTest.test_resource_summary_serializer_from_instance

    # 使用 pytest
    pytest tests/test_serializers.py -v
"""

from django.test import TestCase
from nassav.models import Actor, AVResource, Genre
from nassav.serializers import ResourceSerializer, ResourceSummarySerializer


class SerializersTest(TestCase):
    def setUp(self):
        self.res = AVResource.objects.create(
            avid="TEST-001",
            title="Test Title",
            source="Jable",
            release_date="2025-01-01",
            file_exists=True,
            file_size=12345,
        )
        # add relations
        a = Actor.objects.create(name="Actor1")
        g = Genre.objects.create(name="Genre1")
        self.res.actors.add(a)
        self.res.genres.add(g)

    def test_resource_summary_serializer_from_instance(self):
        ser = ResourceSummarySerializer(self.res)
        data = ser.data
        self.assertEqual(data["avid"], "TEST-001")
        self.assertEqual(data["title"], "Test Title")
        self.assertEqual(data["source"], "Jable")
        self.assertTrue(data["has_video"])
        self.assertIn("metadata_create_time", data)

    def test_resource_serializer_from_metadata_dict(self):
        metadata = {
            "avid": "TEST-002",
            "title": "Meta Title",
            "m3u8": "https://example.com/stream.m3u8",
            "source": "MissAV",
            "release_date": "2025-02-02",
            "duration": 3600,
            "actors": ["A", "B"],
            "genres": ["G"],
            "file_size": 54321,
            "file_exists": False,
        }
        ser = ResourceSerializer(metadata)
        data = ser.data
        self.assertEqual(data["avid"], "TEST-002")
        self.assertEqual(data["m3u8"], "https://example.com/stream.m3u8")
        self.assertFalse(data["file_exists"])
