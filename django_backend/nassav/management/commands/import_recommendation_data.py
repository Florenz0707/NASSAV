"""Assign legacy shared recommendations once, to the explicit original operator."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nassav.models import (
    RecommendationAvidBlocklist,
    RecommendationSeedProfile,
    RecommendationSnapshot,
)
from nassav.recommendation.jobs import ACTIVE, lock_history
from nassav.recommendation_models import RecommendationJob, RecommendationState


class Command(BaseCommand):
    help = "预览旧推荐历史/反馈/黑名单归属；仅 --apply 写入，拒绝覆盖既有个人推荐数据"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--preserve-personal-blocklist",
            action="store_true",
            help="仅补空历史/种子，保留既有个人AVID黑名单；旧AVID黑名单必须为空",
        )

    def handle(self, *args, **options):
        if options["username"] != settings.NASSAV_OPERATOR_USERNAME:
            raise CommandError("必须明确指定配置中的原操作者")
        user = (
            get_user_model()
            .objects.filter(username=options["username"], is_active=True)
            .first()
        )
        if user is None:
            raise CommandError("原操作者不存在或已停用")
        models = (
            RecommendationSnapshot,
            RecommendationSeedProfile,
            RecommendationAvidBlocklist,
        )
        if not options["apply"]:
            counts = [
                model.objects.filter(owner__isnull=True).count() for model in models
            ]
            self.stdout.write(
                f"预览：历史/种子/资源黑名单 {counts}；未写入，确认归属后加 --apply"
            )
            if options["preserve_personal_blocklist"]:
                retained = RecommendationAvidBlocklist.objects.filter(
                    owner=user
                ).count()
                self.stdout.write(
                    f"安全补导入：保留目标个人AVID黑名单 {retained} 条；"
                    "目标历史/种子与旧AVID黑名单必须为空，apply将重核活动任务"
                )
            return
        with transaction.atomic():
            legacy_generation = lock_history(None)
            target_generation = lock_history(user.pk)
            counts = [
                model.objects.filter(owner__isnull=True).count() for model in models
            ]
            if any(counts):
                preserve = options["preserve_personal_blocklist"]
                target_models = models[:2] if preserve else models
                if (
                    (preserve and counts[2] != 0)
                    or any(
                        model.objects.filter(owner=user).exists()
                        for model in target_models
                    )
                    or RecommendationJob.objects.filter(
                        owner=user, state__in=ACTIVE
                    ).exists()
                ):
                    raise CommandError(
                        "目标用户已有推荐数据或活动任务，拒绝自动合并；请先备份并明确归属"
                    )
                for model in models:
                    model.objects.filter(owner__isnull=True).update(owner=user)
                if preserve:
                    # Revoke both old synchronous writers without rewinding the
                    # target's fence or modifying its existing personal blacklist.
                    RecommendationState.objects.filter(owner__isnull=True).update(
                        generation=legacy_generation + 1
                    )
                    generation = target_generation + 1
                else:
                    # Compatibility import into an otherwise empty target.
                    generation = legacy_generation
                RecommendationState.objects.filter(owner=user).update(
                    generation=generation
                )
        self.stdout.write(
            f"导入完成：历史/种子/资源黑名单 {counts}；反馈关系保持，源资源与文件未修改"
        )
