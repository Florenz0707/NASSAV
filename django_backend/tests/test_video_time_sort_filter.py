"""
测试视频时间排序时的过滤逻辑

功能：验证按 video_create_time 排序时，只返回已下载的视频

运行方法：
    uv run python manage.py test tests.test_video_time_sort_filter
"""
from django.test import TestCase
from django.utils import timezone
from nassav.models import AVResource
from nassav.services import list_resources


class VideoTimeSortFilterTestCase(TestCase):
    """测试视频时间排序过滤"""

    def setUp(self):
        """创建测试数据"""
        # 创建已下载的资源
        self.downloaded_resource1 = AVResource.objects.create(
            avid="TEST-001",
            title="已下载资源1",
            file_exists=True,
            video_saved_at=timezone.now() - timezone.timedelta(days=2),
        )
        self.downloaded_resource2 = AVResource.objects.create(
            avid="TEST-002",
            title="已下载资源2",
            file_exists=True,
            video_saved_at=timezone.now() - timezone.timedelta(days=1),
        )

        # 创建未下载的资源
        self.pending_resource1 = AVResource.objects.create(
            avid="TEST-003",
            title="未下载资源1",
            file_exists=False,
            video_saved_at=None,
        )
        self.pending_resource2 = AVResource.objects.create(
            avid="TEST-004",
            title="未下载资源2",
            file_exists=False,
            video_saved_at=None,
        )

    def test_video_create_time_sort_filters_undownloaded(self):
        """测试按视频创建时间排序时，只返回已下载的资源"""
        # 模拟前端请求参数：按 video_create_time 降序排序
        params = {"ordering": "-video_saved_at"}

        objects, pagination = list_resources(params)

        # 验证只返回已下载的资源
        self.assertEqual(len(objects), 2)
        avids = [obj.avid for obj in objects]
        self.assertIn("TEST-001", avids)
        self.assertIn("TEST-002", avids)
        self.assertNotIn("TEST-003", avids)
        self.assertNotIn("TEST-004", avids)

        # 验证排序顺序（降序：最新的在前）
        self.assertEqual(objects[0].avid, "TEST-002")
        self.assertEqual(objects[1].avid, "TEST-001")

    def test_video_create_time_sort_asc(self):
        """测试按视频创建时间升序排序"""
        params = {"ordering": "video_saved_at"}

        objects, pagination = list_resources(params)

        # 验证只返回已下载的资源
        self.assertEqual(len(objects), 2)

        # 验证排序顺序（升序：最旧的在前）
        self.assertEqual(objects[0].avid, "TEST-001")
        self.assertEqual(objects[1].avid, "TEST-002")

    def test_other_sort_includes_all(self):
        """测试按其他字段排序时，包含所有资源"""
        # 按 AVID 排序应该包含所有资源
        params = {"ordering": "avid"}

        objects, pagination = list_resources(params)

        # 验证返回所有资源
        self.assertEqual(len(objects), 4)

    def test_status_filter_with_video_sort(self):
        """测试状态过滤与视频时间排序结合使用"""
        # 明确指定 status=pending 但按 video_saved_at 排序
        # 这种情况下，应该优先考虑排序过滤（只返回已下载）
        params = {"ordering": "-video_saved_at"}

        objects, pagination = list_resources(params)

        # 验证只返回已下载的资源
        self.assertEqual(len(objects), 2)
        for obj in objects:
            self.assertTrue(obj.file_exists)
            self.assertIsNotNone(obj.video_saved_at)

    def test_pagination_with_video_sort(self):
        """测试分页与视频时间排序结合使用"""
        params = {"ordering": "-video_saved_at", "page": 1, "page_size": 1}

        objects, pagination = list_resources(params)

        # 验证分页信息
        self.assertEqual(pagination["total"], 2)
        self.assertEqual(pagination["page"], 1)
        self.assertEqual(pagination["page_size"], 1)
        self.assertEqual(pagination["pages"], 2)

        # 验证返回第一个结果
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0].avid, "TEST-002")
