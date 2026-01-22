"""
测试事件驱动架构
验证信号发布和接收器工作正常
"""

from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from nassav.models import AVResource
from nassav.signals import metadata_refreshed, resource_added, resource_deleted


@pytest.mark.django_db
class TestEventDrivenArchitecture(TestCase):
    """测试事件驱动架构"""

    def test_resource_added_signal_emitted(self):
        """测试资源添加时发出信号"""
        # 创建一个 mock 接收器
        receiver = Mock()
        resource_added.connect(receiver)

        try:
            # 创建测试资源
            resource = AVResource.objects.create(
                avid="TEST-001",
                original_title="Test Resource",
                source_title="Test Resource",
                source="test",
            )

            # 手动发送信号（模拟 ResourceService 的行为）
            resource_added.send(
                sender=self.__class__,
                avid="TEST-001",
                resource=resource,
                result={"resource": resource},
            )

            # 验证接收器被调用
            receiver.assert_called_once()
            call_kwargs = receiver.call_args[1]
            self.assertEqual(call_kwargs["avid"], "TEST-001")
            self.assertEqual(call_kwargs["resource"], resource)

        finally:
            resource_added.disconnect(receiver)

    def test_resource_deleted_signal_emitted(self):
        """测试资源删除时发出信号"""
        # 创建一个 mock 接收器
        receiver = Mock()
        resource_deleted.connect(receiver)

        try:
            # 手动发送信号（模拟 ResourceService 的行为）
            resource_deleted.send(
                sender=self.__class__, avid="TEST-002", delete_files=True
            )

            # 验证接收器被调用
            receiver.assert_called_once()
            call_kwargs = receiver.call_args[1]
            self.assertEqual(call_kwargs["avid"], "TEST-002")
            self.assertEqual(call_kwargs["delete_files"], True)

        finally:
            resource_deleted.disconnect(receiver)
