"""
Django信号定义
用于实现事件驱动架构，解耦业务逻辑
"""

from django.dispatch import Signal

# 资源相关信号
resource_added = Signal()  # 资源添加完成
resource_updated = Signal()  # 资源更新完成
resource_deleted = Signal()  # 资源删除完成
metadata_refreshed = Signal()  # 元数据刷新完成

# 视频相关信号
video_downloaded = Signal()  # 视频下载完成
video_deleted = Signal()  # 视频删除完成

# 翻译相关信号
translation_completed = Signal()  # 翻译完成
