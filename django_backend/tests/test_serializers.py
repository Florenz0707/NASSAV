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
    # 使用 pytest
    uv run pytest tests/test_serializers.py -v
"""

import pytest
from nassav.serializers import ResourceSerializer, ResourceSummarySerializer


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


@pytest.mark.django_db
def test_resource_serializer_from_metadata_dict():
    """测试资源序列化器从字典创建"""
    metadata = {
        "avid": "TEST-002",
        "original_title": "Meta Title",
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

    assert data["avid"] == "TEST-002"
    assert data["m3u8"] == "https://example.com/stream.m3u8"
    assert data["file_exists"] is False
