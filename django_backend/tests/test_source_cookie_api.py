"""
测试 Source Cookie API (GET /api/source/cookie)
验证返回数据包含 source, cookie, mtime 字段
"""

import pytest
from django.utils import timezone
from nassav.models import SourceCookie


@pytest.mark.django_db
def test_get_source_cookie_empty_list(client):
    """测试获取空的 Cookie 列表"""
    response = client.get("/nassav/api/source/cookie")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "success"
    assert data["data"] == []


@pytest.mark.django_db
def test_get_source_cookie_list(client):
    """测试获取 Cookie 列表，验证字段格式"""
    # 创建测试数据
    SourceCookie.objects.create(
        source_name="MissAV", cookie="test_cookie_1; session=abc123"
    )
    SourceCookie.objects.create(
        source_name="Jable", cookie="test_cookie_2; token=xyz789"
    )

    response = client.get("/nassav/api/source/cookie")
    assert response.status_code == 200

    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "success"
    assert len(data["data"]) == 2

    # 验证字段存在
    first_cookie = data["data"][0]
    assert "source" in first_cookie
    assert "cookie" in first_cookie
    assert "mtime" in first_cookie

    # 验证字段类型和内容
    assert isinstance(first_cookie["source"], str)
    assert isinstance(first_cookie["cookie"], str)
    assert isinstance(first_cookie["mtime"], str)  # 日期时间格式字符串

    # 验证 source 按字母排序（Jable < MissAV）
    assert data["data"][0]["source"] == "Jable"
    assert data["data"][1]["source"] == "MissAV"


@pytest.mark.django_db
def test_get_source_cookie_mtime_format(client):
    """测试 mtime 字段格式为 ISO 8601 日期时间"""
    SourceCookie.objects.create(source_name="TestSource", cookie="test_cookie")

    response = client.get("/nassav/api/source/cookie")
    data = response.json()

    mtime = data["data"][0]["mtime"]
    # 验证格式类似 "2026-01-03T12:34:56.789Z" 或 "2026-01-03T12:34:56+00:00"
    assert "T" in mtime  # ISO 8601 格式包含 T 分隔符
    assert any(char in mtime for char in ["Z", "+", "-"])  # 包含时区信息


@pytest.mark.django_db
def test_post_cookie_then_get_list(client):
    """测试 POST 设置 Cookie 后，GET 能获取到"""
    # 先 POST 设置 Cookie
    post_response = client.post(
        "/nassav/api/source/cookie",
        data={"source": "MissAV", "cookie": "my_test_cookie"},
        content_type="application/json",
    )
    assert post_response.status_code == 200

    # 再 GET 获取列表
    get_response = client.get("/nassav/api/source/cookie")
    data = get_response.json()

    assert len(data["data"]) == 1
    # source_name 会被转为小写存储（见 SourceManager.set_source_cookie）
    assert data["data"][0]["source"] == "missav"
    assert data["data"][0]["cookie"] == "my_test_cookie"
    assert "mtime" in data["data"][0]
