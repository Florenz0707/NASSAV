#!/usr/bin/env python
"""
资源视图测试

功能：
1. 测试下载列表 API（/api/downloads/list）
2. 测试资源元数据查询（/api/resource/metadata）
3. 测试视频文件路径查询（/api/downloads/abspath）
4. 测试不存在资源的错误处理
5. 验证文件系统相关操作

运行方式：
    # 运行所有测试
    python manage.py test tests.test_views_resource

    # 运行单个测试
    python manage.py test tests.test_views_resource.ViewsResourceTest.test_downloads_list_empty

    # 使用 pytest
    pytest tests/test_views_resource.py -v
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from pathlib import Path
import tempfile
import shutil

from nassav.models import AVResource


class ViewsResourceTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_downloads_list_empty(self):
        resp = self.client.get('/nassav/api/downloads/list')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        self.assertIsInstance(body['data'], list)

    def test_resource_metadata_missing(self):
        resp = self.client.get('/nassav/api/resource/metadata', {'avid': 'NOEXIST'})
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body['code'], 404)

    @override_settings(VIDEO_DIR=str(tempfile.gettempdir()))
    def test_downloads_abspath_missing(self):
        resp = self.client.get('/nassav/api/downloads/abspath', {'avid': 'NOFILE'})
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body['code'], 404)

    @override_settings(VIDEO_DIR=str(tempfile.gettempdir()))
    def test_downloads_abspath_present(self):
        tmpdir = Path(tempfile.gettempdir())
        fname = tmpdir / 'TST-VID.mp4'
        try:
            with open(fname, 'wb') as f:
                f.write(b"dummy")
            # ensure DB has no entry is fine; view checks filesystem first
            resp = self.client.get('/nassav/api/downloads/abspath', {'avid': 'TST-VID'})
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body['code'], 200)
            self.assertIn('abspath', body['data'])
        finally:
            try:
                fname.unlink()
            except Exception:
                pass

    def test_resource_metadata_with_db(self):
        AVResource.objects.create(avid='DB-001', title='D', source='Jable')
        resp = self.client.get('/nassav/api/resource/metadata', {'avid': 'DB-001'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        self.assertEqual(body['data']['avid'], 'DB-001')
