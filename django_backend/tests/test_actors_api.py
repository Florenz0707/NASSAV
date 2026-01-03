#!/usr/bin/env python
"""
演员 API 测试

功能：
1. 测试演员列表查询 API
2. 测试按演员名称过滤资源
3. 测试演员相关的多对多关系
4. 验证资源和演员的关联查询

运行方式：
    # 使用 pytest
    uv run pytest tests/test_actors_api.py -v
"""

import pytest


@pytest.fixture
def setup_actors_with_resources(actor_factory, resource_factory):
    """创建测试用的演员和资源数据"""
    # 创建演员
    alice = actor_factory(name="Alice")
    bob = actor_factory(name="Bob")

    # 创建资源并关联演员
    r1 = resource_factory(
        avid="ACT-1", original_title="With Alice", source="S1", file_exists=True
    )
    r1.actors.add(alice)

    r2 = resource_factory(
        avid="ACT-2", original_title="With Bob", source="S1", file_exists=False
    )
    r2.actors.add(bob)

    r3 = resource_factory(
        avid="ACT-3", original_title="Alice and Bob", source="S2", file_exists=True
    )
    r3.actors.add(alice, bob)

    return {"alice": alice, "bob": bob}


@pytest.mark.django_db
def test_actor_filter_by_name(api_client, setup_actors_with_resources):
    """测试按演员名称过滤资源"""
    resp = api_client.get("/nassav/api/resources/", {"actor": "Alice"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200

    # 检查三个标题字段中是否有包含 "Alice" 的
    items = body["data"]
    found_alice = any(
        "Alice" in (item.get("original_title") or "")
        or "Alice" in (item.get("source_title") or "")
        or "Alice" in (item.get("translated_title") or "")
        for item in items
    )
    assert found_alice


@pytest.mark.django_db
def test_actor_filter_by_id(api_client, setup_actors_with_resources):
    """测试按演员 ID 过滤资源"""
    alice = setup_actors_with_resources["alice"]
    resp = api_client.get("/nassav/api/resources/", {"actor": str(alice.id)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    # should include both resources linked to Alice
    assert len(body["data"]) >= 2


@pytest.mark.django_db
def test_actors_list_api(api_client, setup_actors_with_resources):
    """测试演员列表 API"""
    resp = api_client.get("/nassav/api/actors/", {"page_size": 10, "page": 1})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)

    # Each actor entry should contain resource_count
    for item in body["data"]:
        assert "resource_count" in item
