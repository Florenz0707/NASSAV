"""
测试演员列表 API 过滤功能

功能：验证演员列表只返回有作品的演员

运行方法：
    uv run python manage.py test tests.test_actors_list_filter
"""
from django.test import TestCase
from django.urls import reverse
from nassav.models import Actor, AVResource
from rest_framework.test import APIClient


class ActorsListFilterTestCase(TestCase):
    """测试演员列表过滤"""

    def setUp(self):
        """创建测试数据"""
        self.client = APIClient()

        # 创建有作品的演员
        self.actor_with_works = Actor.objects.create(name="有作品的演员")
        self.resource1 = AVResource.objects.create(
            avid="TEST-001", original_title="测试资源1"
        )
        self.resource1.actors.add(self.actor_with_works)

        # 创建有多个作品的演员
        self.actor_with_multiple_works = Actor.objects.create(name="多作品演员")
        self.resource2 = AVResource.objects.create(
            avid="TEST-002", original_title="测试资源2"
        )
        self.resource3 = AVResource.objects.create(
            avid="TEST-003", original_title="测试资源3"
        )
        self.resource2.actors.add(self.actor_with_multiple_works)
        self.resource3.actors.add(self.actor_with_multiple_works)

        # 创建没有作品的演员（如被截断的旧演员名）
        self.actor_without_works_1 = Actor.objects.create(name="めぐり（藤")
        self.actor_without_works_2 = Actor.objects.create(name="ミュウ（夏")
        self.actor_without_works_3 = Actor.objects.create(name="森沢かな（")

    def test_actors_list_excludes_zero_count(self):
        """测试演员列表不包含作品数为0的演员"""
        url = reverse("nassav:actors-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # 验证响应结构
        self.assertIn("code", data)
        self.assertIn("data", data)
        self.assertEqual(data["code"], 200)

        actors = data["data"]

        # 验证只返回有作品的演员
        self.assertEqual(len(actors), 2)

        # 验证演员信息
        actor_names = [a["name"] for a in actors]
        self.assertIn("有作品的演员", actor_names)
        self.assertIn("多作品演员", actor_names)

        # 验证不包含无作品的演员
        self.assertNotIn("めぐり（藤", actor_names)
        self.assertNotIn("ミュウ（夏", actor_names)
        self.assertNotIn("森沢かな（", actor_names)

        # 验证作品数正确
        for actor in actors:
            self.assertGreater(actor["resource_count"], 0)
            if actor["name"] == "有作品的演员":
                self.assertEqual(actor["resource_count"], 1)
            elif actor["name"] == "多作品演员":
                self.assertEqual(actor["resource_count"], 2)

    def test_actors_list_with_search_excludes_zero_count(self):
        """测试搜索演员时也过滤掉作品数为0的演员"""
        url = reverse("nassav:actors-list")

        # 搜索"演员"（会匹配所有演员名）
        response = self.client.get(url, {"search": "演员"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        actors = data["data"]

        # 只应该返回有作品的演员
        self.assertEqual(len(actors), 2)
        for actor in actors:
            self.assertGreater(actor["resource_count"], 0)

    def test_actors_list_by_id_allows_zero_count(self):
        """测试按ID查询时允许返回作品数为0的演员"""
        url = reverse("nassav:actors-list")

        # 按ID查询无作品的演员
        response = self.client.get(url, {"id": self.actor_without_works_1.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        actors = data["data"]

        # 应该返回该演员，即使作品数为0
        self.assertEqual(len(actors), 1)
        self.assertEqual(actors[0]["name"], "めぐり（藤")
        self.assertEqual(actors[0]["resource_count"], 0)

    def test_actors_list_pagination_excludes_zero_count(self):
        """测试分页时也过滤掉作品数为0的演员"""
        url = reverse("nassav:actors-list")

        response = self.client.get(url, {"page": 1, "page_size": 10})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # 验证分页信息
        self.assertIn("pagination", data)
        pagination = data["pagination"]

        # 总数应该是2（只有有作品的演员）
        self.assertEqual(pagination["total"], 2)

        # 所有返回的演员都有作品
        for actor in data["data"]:
            self.assertGreater(actor["resource_count"], 0)

    def test_actors_list_order_by_count_excludes_zero(self):
        """测试按作品数排序时过滤掉0作品的演员"""
        url = reverse("nassav:actors-list")

        # 按作品数降序
        response = self.client.get(url, {"order_by": "count", "order": "desc"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        actors = data["data"]

        # 验证排序正确且没有0作品演员
        self.assertEqual(len(actors), 2)
        self.assertEqual(actors[0]["name"], "多作品演员")
        self.assertEqual(actors[0]["resource_count"], 2)
        self.assertEqual(actors[1]["name"], "有作品的演员")
        self.assertEqual(actors[1]["resource_count"], 1)

    def test_database_has_zero_count_actors(self):
        """验证数据库中确实存在作品数为0的演员（测试数据完整性）"""
        zero_count_actors = Actor.objects.filter(resources__isnull=True)
        self.assertEqual(zero_count_actors.count(), 3)

        # 验证是被截断的演员名
        zero_names = [a.name for a in zero_count_actors]
        self.assertIn("めぐり（藤", zero_names)
        self.assertIn("ミュウ（夏", zero_names)
        self.assertIn("森沢かな（", zero_names)
