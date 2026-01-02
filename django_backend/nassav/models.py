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
        max_length=50, unique=True, primary_key=True, verbose_name="源名称"
    )
    cookie = models.TextField(verbose_name="Cookie")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "source_cookie"
        verbose_name = "源Cookie配置"
        verbose_name_plural = "源Cookie配置"

    def __str__(self):
        return f"{self.source_name}"


class Actor(models.Model):
    name = models.CharField(max_length=200, unique=True, db_index=True)

    class Meta:
        db_table = "nassav_actor"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    class Meta:
        db_table = "nassav_genre"
        ordering = ["name"]

    def __str__(self):
        return self.name


from django.utils import timezone


class AVResource(models.Model):
    # 翻译状态选项
    TRANSLATION_STATUS_CHOICES = [
        ("pending", "待翻译"),
        ("translating", "翻译中"),
        ("completed", "已完成"),
        ("failed", "翻译失败"),
        ("skipped", "跳过"),
    ]

    avid = models.CharField(max_length=50, unique=True, db_index=True)
    title = models.CharField(
        max_length=512,
        blank=True,
        db_index=True,
        help_text="Scraper 获取的标题（通常为日语，来自 Javbus）",
    )
    source_title = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Source 获取的标题（备用，来自 MissAV/Jable 等）",
    )
    translated_title = models.CharField(
        max_length=512, blank=True, null=True, help_text="翻译后的标题（中文，由 Ollama 翻译）"
    )
    translation_status = models.CharField(
        max_length=20,
        choices=TRANSLATION_STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="翻译状态",
    )
    source = models.CharField(max_length=128, blank=True, db_index=True)
    release_date = models.CharField(max_length=64, blank=True, db_index=True)
    duration = models.IntegerField(null=True, blank=True, help_text="时长（秒）")

    metadata = models.JSONField(null=True, blank=True)
    m3u8 = models.TextField(null=True, blank=True)

    actors = models.ManyToManyField(Actor, blank=True, related_name="resources")
    genres = models.ManyToManyField(Genre, blank=True, related_name="resources")

    cover_filename = models.CharField(
        max_length=255, blank=True, null=True, help_text="相对于 resource/{avid}/ 的封面文件名"
    )
    file_exists = models.BooleanField(
        default=False, db_index=True, help_text="是否存在 MP4 文件"
    )
    file_size = models.BigIntegerField(null=True, blank=True)

    metadata_saved_at = models.DateTimeField(auto_now=True)
    video_saved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "nassav_avresource"
        ordering = ["-metadata_saved_at"]
        indexes = [
            models.Index(fields=["avid"]),
            models.Index(fields=["title"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        return f"{self.avid} - {self.title}"
