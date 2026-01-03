#!/usr/bin/env python
"""
类别/标签 API 测试

功能：
1. 测试类别列表查询 API
2. 测试按类别过滤资源
3. 测试类别的模糊搜索
4. 测试类别统计和排序功能
5. 验证资源和类别的多对多关系

运行方式：
    # 使用 pytest
    uv run pytest tests/test_genres_api.py -v
"""

import pytest


@pytest.fixture
def setup_genres_with_resources(genre_factory, resource_factory):
    """创建测试用的类别和资源数据"""
    # 创建类别
    g1 = genre_factory(name="中文字幕")
    g2 = genre_factory(name="人妻")
    g3 = genre_factory(name="素人")

    # 创建资源并关联类别
    r1 = resource_factory(
        avid="GEN-1", original_title="With 中文字幕", source="S1", file_exists=True
    )
    r1.genres.add(g1)

    r2 = resource_factory(
        avid="GEN-2", original_title="With 人妻", source="S1", file_exists=False
    )
    r2.genres.add(g2)

    r3 = resource_factory(
        avid="GEN-3", original_title="中文字幕 and 人妻", source="S2", file_exists=True
    )
    r3.genres.add(g1, g2)

    r4 = resource_factory(
        avid="GEN-4", original_title="素人作品", source="S3", file_exists=True
    )
    r4.genres.add(g3)

    return {"中文字幕": g1, "人妻": g2, "素人": g3}


@pytest.mark.django_db
def test_genre_filter_by_name(api_client, setup_genres_with_resources):
    """测试按类别名称过滤资源"""
    resp = api_client.get("/nassav/api/resources/", {"genre": "中文"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200

    # should return resources with genre containing '中文'
    avids = [item["avid"] for item in body["data"]]
    assert "GEN-1" in avids
    assert "GEN-3" in avids


@pytest.mark.django_db
def test_genre_filter_by_id(api_client, setup_genres_with_resources):
    """测试按类别 ID 过滤资源"""
    chs = setup_genres_with_resources["中文字幕"]
    resp = api_client.get("/nassav/api/resources/", {"genre": str(chs.id)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200

    # should include both resources linked to 中文字幕
    avids = [item["avid"] for item in body["data"]]
    assert "GEN-1" in avids
    assert "GEN-3" in avids
    assert len(avids) == 2


@pytest.mark.django_db
def test_genres_list_api(api_client, setup_genres_with_resources):
    """测试类别列表 API"""
    resp = api_client.get("/nassav/api/genres/", {"page_size": 10, "page": 1})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)

    # Each genre entry should contain resource_count
    for item in body["data"]:
        assert "resource_count" in item
        assert "id" in item
        assert "name" in item


@pytest.mark.django_db
def test_genres_list_sorting_by_count(api_client, setup_genres_with_resources):
    """测试类别列表按数量排序"""
    resp = api_client.get(
        "/nassav/api/genres/",
        {"page_size": 10, "page": 1, "order_by": "count", "order": "desc"},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200

    data = body["data"]
    # verify descending order
    counts = [item["resource_count"] for item in data]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.django_db
def test_genres_list_search(api_client, setup_genres_with_resources):
    """测试类别列表搜索"""
    resp = api_client.get("/nassav/api/genres/", {"search": "中文"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200

    # should only return genres matching '中文'
    names = [item["name"] for item in body["data"]]
    assert len(names) == 1
    assert "中文字幕" in names


@pytest.mark.django_db
def test_genres_list_pagination(api_client, setup_genres_with_resources):
    """测试类别列表分页"""
    resp = api_client.get("/nassav/api/genres/", {"page_size": 2, "page": 1})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert len(body["data"]) == 2

    pagination = body.get("pagination", {})
    assert pagination["page"] == 1
    assert pagination["page_size"] == 2
    assert pagination["total"] >= 3
