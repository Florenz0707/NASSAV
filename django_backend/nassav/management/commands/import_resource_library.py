"""Preview/import existing resources into an explicitly confirmed operator's library."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from nassav.library_import import import_legacy_library


class Command(BaseCommand):
    help = "预览共享池与旧资源持有导入；仅 --apply 写入，不移动媒体或修改个人状态"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if options["username"] != settings.NASSAV_OPERATOR_USERNAME:
            raise CommandError("必须显式指定配置的原操作者，不推断所有者")
        try:
            result = import_legacy_library(options["username"], apply=options["apply"])
        except (get_user_model().DoesNotExist, ValueError) as error:
            raise CommandError(f"导入拒绝，未写入: {error}") from error
        self.stdout.write(json.dumps(result, ensure_ascii=False))
