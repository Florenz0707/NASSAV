#!/usr/bin/env python
"""
资源视图测试

功能：
1. 测试资源元数据查询（/api/resource/metadata）
2. 测试视频文件路径查询（/api/downloads/abspath）
3. 测试不存在资源的错误处理
4. 验证文件系统相关操作

运行方式：
    # 使用 pytest
    uv run pytest tests/test_views_resource.py -v
"""

from pathlib import Path

import pytest


@pytest.mark.django_db
def test_resource_metadata_missing(api_client):
    """测试不存在的资源元数据查询"""
    resp = api_client.get("/nassav/api/resource/metadata", {"avid": "NOEXIST"})
    assert resp.status_code == 404

    body = resp.json()
    assert body["code"] == 404


@pytest.mark.django_db
def test_downloads_abspath_missing(api_client, tmp_path, settings):
    """测试不存在的文件路径查询"""
    settings.VIDEO_DIR = str(tmp_path)
    resp = api_client.get("/nassav/api/downloads/abspath", {"avid": "NOFILE"})
    assert resp.status_code == 404

    body = resp.json()
    assert body["code"] == 404


@pytest.mark.django_db
def test_downloads_abspath_present(api_client, tmp_path, settings):
    """测试存在的文件路径查询"""
    settings.VIDEO_DIR = str(tmp_path)
    fname = tmp_path / "TST-VID.mp4"

    try:
        with open(fname, "wb") as f:
            f.write(b"dummy")

        # ensure DB has no entry is fine; view checks filesystem first
        resp = api_client.get("/nassav/api/downloads/abspath", {"avid": "TST-VID"})
        assert resp.status_code == 200

        body = resp.json()
        assert body["code"] == 200
        assert "abspath" in body["data"]
    finally:
        if fname.exists():
            fname.unlink()


@pytest.mark.django_db
def test_resource_metadata_with_db(api_client, resource_factory):
    """测试存在的资源元数据查询"""
    resource_factory(avid="DB-001", original_title="D", source="Jable")

    resp = api_client.get("/nassav/api/resource/metadata", {"avid": "DB-001"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["avid"] == "DB-001"
