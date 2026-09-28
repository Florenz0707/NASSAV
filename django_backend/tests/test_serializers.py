#!/usr/bin/env python
"""
序列化器测试

功能：
1. 测试 ResourceSummarySerializer（资源摘要序列化器）
2. 测试资源摘要字段映射和数据转换
3. 验证关联数据（演员、类别）的序列化

运行方式：
    # 使用 pytest
    uv run pytest tests/test_serializers.py -v
"""

import pytest
from nassav.serializers import ResourceSummarySerializer


@pytest.fixture
def resource_with_relations(resource_factory, actor_factory, genre_factory):
    """创建一个带有演员和类别的资源"""
    res = resource_factory(
        avid="TEST-001",
        original_title="Test Title",
        source="Jable",
        release_date="2025-01-01",
        file_exists=True,
        file_size=12345,
    )
    # 添加关联
    actor = actor_factory(name="Actor1")
    genre = genre_factory(name="Genre1")
    res.actors.add(actor)
    res.genres.add(genre)
    return res


@pytest.mark.django_db
def test_resource_summary_serializer_from_instance(resource_with_relations):
    """测试资源摘要序列化器"""
    ser = ResourceSummarySerializer(resource_with_relations)
    data = ser.data

    assert data["avid"] == "TEST-001"
    assert data["original_title"] == "Test Title"
    assert data["source"] == "Jable"
    assert data["has_video"] is True
    assert "metadata_create_time" in data

    # 验证同时返回三个标题字段
    assert "original_title" in data
    assert "source_title" in data
    assert "translated_title" in data
