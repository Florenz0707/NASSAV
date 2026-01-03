#!/usr/bin/env python
"""
资源列表 API 测试

功能：
1. 测试资源列表查询 API（/api/resources/）
2. 测试资源过滤功能（按下载状态、来源等）
3. 测试分页和排序
4. 验证响应格式和数据结构

运行方式：
    # 使用 pytest
    uv run pytest tests/test_resources_list.py -v
"""

import pytest


@pytest.fixture
def setup_resources(resource_factory):
    """创建测试用的资源数据"""
    # 创建多个资源
    r1 = resource_factory(
        avid="A-1", original_title="A1", source="S1", file_exists=True
    )
    r2 = resource_factory(
        avid="A-2", original_title="A2", source="S2", file_exists=False
    )
    r3 = resource_factory(
        avid="B-1", original_title="B1", source="S1", file_exists=True
    )
    return [r1, r2, r3]


@pytest.mark.django_db
def test_resources_list_no_filter(api_client, setup_resources):
    """测试无过滤条件的资源列表"""
    resp = api_client.get("/nassav/api/resources/")
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 3


@pytest.mark.django_db
def test_resources_filter_file_exists(api_client, setup_resources):
    """测试按文件存在状态过滤"""
    resp = api_client.get("/nassav/api/resources/", {"file_exists": "true"})
    assert resp.status_code == 200

    body = resp.json()
    assert all(item["has_video"] for item in body["data"])


@pytest.mark.django_db
def test_resources_filter_source(api_client, setup_resources):
    """测试按来源过滤"""
    resp = api_client.get("/nassav/api/resources/", {"source": "S2"})
    assert resp.status_code == 200

    body = resp.json()
    assert all(item["source"] == "S2" for item in body["data"])


@pytest.mark.django_db
def test_resources_pagination(api_client, setup_resources):
    """测试分页功能"""
    resp = api_client.get("/nassav/api/resources/", {"page_size": 1, "page": 1})
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["data"]) == 1
