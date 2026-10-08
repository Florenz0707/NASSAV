"""Recommendation history fence and owned, bounded worker requests."""

from uuid import uuid4
from django.conf import settings
from django.db import models


class RecommendationState(models.Model):
    generation = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "nassav_recommendation_state"


class RecommendationJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    state = models.CharField(max_length=16, default="queued")
    version = models.PositiveBigIntegerField(default=1)
    history_generation = models.PositiveBigIntegerField()
    execution_owner = models.UUIDField(null=True)
    parameters = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateTimeField()
    dispatch_after = models.DateTimeField(null=True)

    class Meta:
        db_table = "nassav_recommendation_job"
        indexes = [
            models.Index(
                fields=["state", "deadline"], name="nassav_reco_state_64edbc_idx"
            )
        ]
