#!/usr/bin/env python
"""
资源列表 API 测试

功能：
1. 测试资源列表查询 API（/api/resources/）
2. 测试资源过滤功能（按下载状态、来源等）
3. 测试分页和排序
4. 验证响应格式和数据结构

运行方式：
    # 运行所有测试
    python manage.py test tests.test_resources_list

    # 运行单个测试
    python manage.py test tests.test_resources_list.ResourcesListTest.test_resources_list_no_filter

    # 使用 pytest
    pytest tests/test_resources_list.py -v
"""

from django.test import TestCase
from nassav.models import AVResource
from rest_framework.test import APIClient


class ResourcesListTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # create several resources
        AVResource.objects.create(
            avid="A-1", original_title="A1", source="S1", file_exists=True
        )
        AVResource.objects.create(
            avid="A-2", original_title="A2", source="S2", file_exists=False
        )
        AVResource.objects.create(
            avid="B-1", original_title="B1", source="S1", file_exists=True
        )

    def test_resources_list_no_filter(self):
        resp = self.client.get("/nassav/api/resources/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        self.assertIsInstance(body["data"], list)
        self.assertGreaterEqual(len(body["data"]), 3)

    def test_resources_filter_file_exists(self):
        resp = self.client.get("/nassav/api/resources/", {"file_exists": "true"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all(item["has_video"] for item in body["data"]))

    def test_resources_filter_source(self):
        resp = self.client.get("/nassav/api/resources/", {"source": "S2"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all(item["source"] == "S2" for item in body["data"]))

    def test_resources_pagination(self):
        resp = self.client.get("/nassav/api/resources/", {"page_size": 1, "page": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["data"]), 1)
