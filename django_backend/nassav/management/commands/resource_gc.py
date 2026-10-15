"""Explicit preview/audited request; never an unguarded recursive filesystem tool."""

import json
from uuid import UUID
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from nassav.account_management import REASONS
from nassav.resource_gc import GcDeferred, GcNotFound
from nassav.resource_gc_admin import GcAdminConflict


class Command(BaseCommand):
    help = "预览共享资源回收，或提交带版本/理由/幂等ID的管理员命令。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--action",
            choices=["preview", "enqueue", "retry", "retention"],
            default="preview",
        )
        parser.add_argument(
            "--target", type=UUID, required=True, help="pool UUID；retry时为GC job UUID"
        )
        parser.add_argument("--version-id", type=UUID)
        parser.add_argument("--actor", help="已配置应用管理员用户名")
        parser.add_argument("--reason", choices=sorted(REASONS))
        parser.add_argument("--request-id", type=UUID)
        parser.add_argument("--expected-version", type=int)
        parser.add_argument("--retained", choices=["true", "false"])

    def handle(self, *args, **options):
        from nassav.resource_gc_records import DjangoGcRecords
        from nassav.composition import build_resource_gc_administration

        try:
            if options["action"] == "preview":
                result = DjangoGcRecords().preview(
                    options["target"], options.get("version_id")
                )
            else:
                if not settings.SHARED_LIBRARY_ENABLED:
                    raise CommandError("共享模式尚未开启")
                if (
                    options["action"] in {"enqueue", "retry"}
                    and not settings.RESOURCE_GC_ENABLED
                ):
                    raise CommandError("回收执行开关尚未开启；先完成目标验收")
                if (
                    not options.get("actor")
                    or not options.get("reason")
                    or not options.get("request_id")
                    or not options.get("expected_version")
                ):
                    raise CommandError(
                        "写操作必须指定actor/reason/request-id/expected-version"
                    )
                user = get_user_model().objects.get(username=options["actor"])
                payload = {
                    "request_id": str(options["request_id"]),
                    "reason": options["reason"],
                    "expected_version": options["expected_version"],
                }
                if options["action"] == "enqueue" and options.get("version_id"):
                    payload["version_id"] = str(options["version_id"])
                if options["action"] == "retention":
                    payload["retained"] = (
                        options.get("retained") == "true"
                        if options.get("retained") is not None
                        else None
                    )
                result = build_resource_gc_administration().execute(
                    user.pk, options["action"], options["target"], payload
                )
        except (
            ValueError,
            PermissionError,
            GcDeferred,
            GcNotFound,
            GcAdminConflict,
            get_user_model().DoesNotExist,
        ) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(json.dumps(result, ensure_ascii=False))
