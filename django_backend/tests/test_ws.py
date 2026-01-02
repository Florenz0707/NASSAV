#!/usr/bin/env python
"""
WebSocket 连接测试

功能：
1. 测试 WebSocket 连接建立
2. 测试任务队列状态查询（通过 WebSocket）
3. 验证 WebSocket 消息格式
4. 测试异步通信机制

运行方式：
    # 运行所有测试
    python manage.py test tests.test_ws

    # 运行单个测试
    python manage.py test tests.test_ws.WebSocketTest.test_ws_queue_status

    # 使用 pytest
    pytest tests/test_ws.py -v

注意：
    - 需要 Redis 服务运行
    - 需要 Channels 和 channels-redis 已安装
    - 测试使用 TransactionTestCase 以支持异步操作
"""

import asyncio
import json
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from django_project.asgi import application


class WebSocketTest(TransactionTestCase):
    """Basic WebSocket skeleton test for task consumer."""

    async def _run(self):
        comm = WebsocketCommunicator(application, '/nassav/ws/tasks/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        # request queue status
        await comm.send_json_to({'action': 'get_queue_status'})
        msg = await comm.receive_json_from()
        # expecting a dict with type/ data
        self.assertIn('type', msg)
        await comm.disconnect()

    def test_ws_queue_status(self):
        asyncio.get_event_loop().run_until_complete(self._run())
