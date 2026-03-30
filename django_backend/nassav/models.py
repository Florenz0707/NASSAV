"""
数据库模型
"""

import re

from django.db import models
from django.utils import timezone


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
    avatar_url = models.URLField(blank=True, null=True, help_text="Javbus 头像 URL")
    avatar_filename = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="头像文件名（存储在 resource/avatar/）",
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="最后更新时间")

    class Meta:
        db_table = "nassav_actor"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ActorSourceMapping(models.Model):
    actor = models.ForeignKey(
        Actor,
        on_delete=models.CASCADE,
        related_name="source_mappings",
    )
    source_name = models.CharField(max_length=32, db_index=True)
    source_actor_name = models.CharField(max_length=255, blank=True)
    source_actor_slug = models.CharField(max_length=255, null=True, blank=True)
    source_actor_url = models.URLField(max_length=1024, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    match_method = models.CharField(max_length=32, default="manual")
    confidence = models.FloatField(default=1.0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_actor_source_mapping"
        ordering = ["source_name", "actor_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "source_name"],
                name="nas_actsrc_actor_src_uniq",
            ),
            models.UniqueConstraint(
                fields=["source_name", "source_actor_slug"],
                name="nassav_actsrc_source_slug_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["source_name", "source_actor_name"],
                name="nassav_actsrc_source_name_idx",
            ),
            models.Index(
                fields=["source_name", "is_active"],
                name="nas_actsrc_src_active_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.source_name = str(self.source_name or "").strip().lower()
        self.source_actor_name = str(self.source_actor_name or "").strip()
        self.source_actor_url = str(self.source_actor_url or "").strip()

        slug = str(self.source_actor_slug or "").strip().strip("/")
        if not slug and self.source_name == "jable" and self.source_actor_url:
            match = re.search(r"/models/([^/?#]+)/?", self.source_actor_url)
            if match:
                slug = match.group(1).strip()
        self.source_actor_slug = slug.lower() if slug else None

        if (
            self.source_name == "jable"
            and self.source_actor_slug
            and not self.source_actor_url
        ):
            self.source_actor_url = f"https://jable.tv/models/{self.source_actor_slug}/"

        if self.aliases is None:
            self.aliases = []
        super().save(*args, **kwargs)

    def __str__(self):
        actor_pk = getattr(self, "actor_id", None)
        return (
            f"{actor_pk}:{self.source_name}:"
            f"{self.source_actor_slug or self.source_actor_name}"
        )


class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)

    class Meta:
        db_table = "nassav_genre"
        ordering = ["name"]

    def __str__(self):
        return self.name


class GenreSourceMapping(models.Model):
    genre = models.ForeignKey(
        Genre,
        on_delete=models.CASCADE,
        related_name="source_mappings",
    )
    source_name = models.CharField(max_length=32, db_index=True)
    source_genre_name = models.CharField(max_length=255, blank=True)
    source_genre_slug = models.CharField(max_length=255, null=True, blank=True)
    source_genre_url = models.URLField(max_length=1024, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    match_method = models.CharField(max_length=32, default="manual")
    confidence = models.FloatField(default=1.0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_genre_source_mapping"
        ordering = ["source_name", "genre_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["genre", "source_name"],
                name="nas_gensrc_genre_src_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["source_name", "source_genre_name"],
                name="nassav_gensrc_source_name_idx",
            ),
            models.Index(
                fields=["source_name", "is_active"],
                name="nas_gensrc_src_active_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.source_name = str(self.source_name or "").strip().lower()
        self.source_genre_name = str(self.source_genre_name or "").strip()
        self.source_genre_url = str(self.source_genre_url or "").strip()

        slug = str(self.source_genre_slug or "").strip().strip("/")
        if not slug and self.source_name == "jable" and self.source_genre_url:
            match = re.search(
                r"/(?:tags|categories)/([^/?#]+)/?", self.source_genre_url
            )
            if match:
                slug = match.group(1).strip()
        self.source_genre_slug = slug.lower() if slug else None

        if self.aliases is None:
            self.aliases = []
        super().save(*args, **kwargs)

    def __str__(self):
        genre_pk = getattr(self, "genre_id", None)
        return (
            f"{genre_pk}:{self.source_name}:"
            f"{self.source_genre_slug or self.source_genre_name}"
        )


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
    original_title = models.CharField(
        max_length=512,
        blank=True,
        db_index=True,
        help_text="Scraper 获取的原始标题（通常为日语，来自 Javbus）",
    )
    source_title = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Source 获取的标题（备用，来自 MissAV/Jable 等）",
    )
    translated_title = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="翻译后的标题（中文，由 Ollama 翻译）",
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
        max_length=255,
        blank=True,
        null=True,
        help_text="相对于 resource/{avid}/ 的封面文件名",
    )
    file_exists = models.BooleanField(
        default=False, db_index=True, help_text="是否存在 MP4 文件"
    )
    file_size = models.BigIntegerField(null=True, blank=True)

    watched = models.BooleanField(default=False, db_index=True, help_text="是否已观看")
    is_favorite = models.BooleanField(
        default=False, db_index=True, help_text="是否收藏"
    )

    metadata_created_at = models.DateTimeField(
        null=True, blank=True, help_text="元数据首次创建时间"
    )
    metadata_updated_at = models.DateTimeField(
        auto_now=True, help_text="元数据最后更新时间"
    )
    video_saved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "nassav_avresource"
        ordering = ["-metadata_updated_at"]

    def __str__(self):
        return f"{self.avid} - {self.original_title}"


class RecommendationSnapshot(models.Model):
    recommender_id = models.CharField(max_length=64, db_index=True)
    strategy_id = models.CharField(max_length=64, db_index=True)
    request_fingerprint = models.CharField(max_length=64, db_index=True)
    request_payload = models.JSONField(default=dict)
    seed_summary = models.JSONField(default=list)
    item_count = models.PositiveIntegerField(default=0)
    random_seed = models.BigIntegerField(default=0)
    generated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "nassav_recommendation_snapshot"
        ordering = ["-generated_at"]
        indexes = [
            models.Index(
                fields=["recommender_id", "strategy_id", "request_fingerprint"],
                name="nassav_recsnap_lkp_idx",
            ),
        ]

    def __str__(self):
        return f"{self.recommender_id}:{self.strategy_id}#{self.pk}"


class RecommendationItem(models.Model):
    snapshot = models.ForeignKey(
        RecommendationSnapshot,
        on_delete=models.CASCADE,
        related_name="items",
    )
    rank = models.PositiveIntegerField()
    avid = models.CharField(max_length=50, db_index=True)
    title = models.CharField(max_length=512, blank=True)
    detail_url = models.URLField(max_length=1024, blank=True)
    cover_url = models.URLField(max_length=1024, blank=True)
    source = models.CharField(max_length=128, blank=True, db_index=True)
    score = models.FloatField(default=0.0)
    search_rank = models.IntegerField(null=True, blank=True)
    reasons = models.JSONField(default=list)
    matched_seeds = models.JSONField(default=list)
    score_breakdown = models.JSONField(default=list)
    raw_metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "nassav_recommendation_item"
        ordering = ["snapshot_id", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "rank"],
                name="nassav_recitem_sr_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["snapshot", "avid"],
                name="nassav_recitem_sa_idx",
            ),
        ]

    def __str__(self):
        snapshot = getattr(self, "snapshot", None)
        snapshot_pk = snapshot.pk if snapshot is not None else None
        return f"{snapshot_pk}:{self.rank}:{self.avid}"


class RecommendationFeedback(models.Model):
    FEEDBACK_CHOICES = [
        ("like", "喜欢"),
        ("dislike", "不喜欢"),
    ]
    FEEDBACK_VALUE_MAP = {
        "like": 1,
        "dislike": -1,
    }

    item = models.OneToOneField(
        RecommendationItem,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    avid = models.CharField(max_length=50, db_index=True)
    feedback = models.CharField(max_length=16, choices=FEEDBACK_CHOICES, db_index=True)
    feedback_value = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nassav_recommendation_feedback"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(
                fields=["avid", "feedback"],
                name="nassav_recfb_af_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        self.feedback_value = self.FEEDBACK_VALUE_MAP.get(self.feedback, 0)
        item_id = getattr(self, "item_id", None)
        if item_id and not self.avid:
            self.avid = self.item.avid
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.avid}:{self.feedback}"
