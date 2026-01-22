"""
测试数据库查询优化
验证 N+1 查询问题已被解决
"""

import pytest
from django.test import TestCase
from nassav.models import AVResource, Genre
from nassav.serializers import ResourceSummarySerializer
from nassav.services import list_resources


@pytest.mark.django_db
class TestQueryOptimization(TestCase):
    """测试查询优化效果"""

    def setUp(self):
        """创建测试数据"""
        # 创建一些 genres
        self.genres = [Genre.objects.create(name=f"Genre{i}") for i in range(5)]

        # 创建一些资源，每个资源关联多个 genres
        self.resources = []
        for i in range(10):
            resource = AVResource.objects.create(
                avid=f"TEST-{i:03d}",
                original_title=f"Test Resource {i}",
                source_title=f"Test Resource {i}",
                source="test",
            )
            # 每个资源关联 2-3 个 genres
            resource.genres.set(self.genres[i % 3 : (i % 3) + 2])
            self.resources.append(resource)

    def test_list_resources_query_count(self):
        """测试 list_resources 的查询次数"""
        # 使用 prefetch_related 优化后，应该只有 3 次查询：
        # 1. COUNT 查询（分页器需要）
        # 2. 查询资源列表
        # 3. 预加载所有 genres（一次性查询）
        # 如果没有优化，会是 1 + 1 + 10 = 12 次查询
        with self.assertNumQueries(3):
            objs, pagination = list_resources({"page": 1, "page_size": 10})
            # 序列化资源列表，访问 genres
            serializer = ResourceSummarySerializer(objs, many=True)
            data = serializer.data
            # 验证数据正确
            self.assertEqual(len(data), 10)
            # 验证每个资源都有 genres
            for item in data:
                self.assertIn("genres", item)

    def test_without_optimization_would_be_n_plus_1(self):
        """
        演示：如果不使用 prefetch_related，会产生 N+1 查询
        这个测试用于对比，展示优化前的情况
        """
        # 直接查询，不使用 prefetch_related
        resources = AVResource.objects.all()[:10]

        # 这会产生 N+1 查询：1次查询资源 + N次查询genres
        # 预期查询次数：1 (资源列表) + 10 (每个资源的genres) = 11
        with self.assertNumQueries(11):
            for resource in resources:
                # 访问 genres 会触发额外查询
                list(resource.genres.all())
