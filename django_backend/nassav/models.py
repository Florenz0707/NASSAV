"""
数据库模型
"""
from django.db import models


class SourceCookie(models.Model):
    """
    存储下载源的 Cookie 配置
    通过 API 动态设置，持久化存储
    """
    source_name = models.CharField(
        max_length=50,
        unique=True,
        primary_key=True,
        verbose_name='源名称'
    )
    cookie = models.TextField(
        verbose_name='Cookie'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        db_table = 'source_cookie'
        verbose_name = '源Cookie配置'
        verbose_name_plural = '源Cookie配置'

    def __str__(self):
        return f"{self.source_name}"
