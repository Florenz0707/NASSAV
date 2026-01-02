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
    # 运行所有测试
    python manage.py test tests.test_genres_api

    # 运行单个测试
    python manage.py test tests.test_genres_api.GenresAPITest.test_genre_filter_by_name

    # 使用 pytest
    pytest tests/test_genres_api.py -v
"""

from django.test import TestCase
from nassav.models import AVResource, Genre
from rest_framework.test import APIClient


class GenresAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # create genres
        g1 = Genre.objects.create(name="中文字幕")
        g2 = Genre.objects.create(name="人妻")
        g3 = Genre.objects.create(name="素人")

        # create resources and link genres
        r1 = AVResource.objects.create(
            avid="GEN-1", title="With 中文字幕", source="S1", file_exists=True
        )
        r1.genres.add(g1)

        r2 = AVResource.objects.create(
            avid="GEN-2", title="With 人妻", source="S1", file_exists=False
        )
        r2.genres.add(g2)

        r3 = AVResource.objects.create(
            avid="GEN-3", title="中文字幕 and 人妻", source="S2", file_exists=True
        )
        r3.genres.add(g1, g2)

        r4 = AVResource.objects.create(
            avid="GEN-4", title="素人作品", source="S3", file_exists=True
        )
        r4.genres.add(g3)

    def test_genre_filter_by_name(self):
        resp = self.client.get("/nassav/api/resources/", {"genre": "中文"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        # should return resources with genre containing '中文'
        avids = [item["avid"] for item in body["data"]]
        self.assertIn("GEN-1", avids)
        self.assertIn("GEN-3", avids)

    def test_genre_filter_by_id(self):
        chs = Genre.objects.get(name="中文字幕")
        resp = self.client.get("/nassav/api/resources/", {"genre": str(chs.id)})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        # should include both resources linked to 中文字幕
        avids = [item["avid"] for item in body["data"]]
        self.assertIn("GEN-1", avids)
        self.assertIn("GEN-3", avids)
        self.assertEqual(len(avids), 2)

    def test_genres_list_api(self):
        resp = self.client.get("/nassav/api/genres/", {"page_size": 10, "page": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        self.assertIsInstance(body["data"], list)
        # Each genre entry should contain resource_count
        for item in body["data"]:
            self.assertIn("resource_count", item)
            self.assertIn("id", item)
            self.assertIn("name", item)

    def test_genres_list_sorting_by_count(self):
        resp = self.client.get(
            "/nassav/api/genres/",
            {"page_size": 10, "page": 1, "order_by": "count", "order": "desc"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        data = body["data"]
        # verify descending order
        counts = [item["resource_count"] for item in data]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_genres_list_search(self):
        resp = self.client.get("/nassav/api/genres/", {"search": "中文"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        # should only return genres matching '中文'
        names = [item["name"] for item in body["data"]]
        self.assertEqual(len(names), 1)
        self.assertIn("中文字幕", names)

    def test_genres_list_pagination(self):
        resp = self.client.get("/nassav/api/genres/", {"page_size": 2, "page": 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 2)
        pagination = body.get("pagination", {})
        self.assertEqual(pagination["page"], 1)
        self.assertEqual(pagination["page_size"], 2)
        self.assertGreaterEqual(pagination["total"], 3)
