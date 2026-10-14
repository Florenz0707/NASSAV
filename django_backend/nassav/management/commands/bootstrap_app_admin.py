"""Explicit first-admin bootstrap; neither migrations nor Django flags grant roles."""

import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from nassav.composition import build_account_management
from nassav.account_management import AccountConflict


class Command(BaseCommand):
    help = "预览首个应用管理员引导；仅显式 --apply 授权配置中的操作者，已有可用管理员时拒绝"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--request-id")

    def handle(self, *args, **options):
        if options["username"] != settings.NASSAV_OPERATOR_USERNAME:
            raise CommandError("必须指定配置中的操作者")
        user = (
            get_user_model()
            .objects.filter(
                **{
                    getattr(get_user_model(), "USERNAME_FIELD", "username"): options[
                        "username"
                    ]
                },
                is_active=True,
            )
            .first()
        )
        if user is None:
            raise CommandError("启用的操作者账号不存在")
        if not options["apply"]:
            self.stdout.write(
                json.dumps({"username": options["username"], "applied": False})
            )
            return
        try:
            result = build_account_management().execute(
                user.pk,
                "bootstrap",
                user.pk,
                {"request_id": options["request_id"], "reason": "bootstrap"},
            )
        except (ValueError, PermissionError, AccountConflict) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result))
