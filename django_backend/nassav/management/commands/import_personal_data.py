"""One-time, explicitly owned import of shared legacy flags and read-only INI."""

import configparser
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from nassav.models import AVResource, UserPreferences, UserResourceState
from nassav.preference_definitions import PREFERENCE_DEFINITIONS, validate_preferences
from nassav.personal_state import lock_user


class Command(BaseCommand):
    help = "预览旧收藏/观看/INI导入；指定 --apply 才写入，仅导入到原操作者，既有个人数据不覆盖"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--settings-file", type=Path)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        username = options["username"]
        if username != settings.NASSAV_OPERATOR_USERNAME:
            raise CommandError("username 必须是当前配置的原操作者；不自动推断数据归属")
        User = get_user_model()
        user = User.objects.filter(
            **{getattr(User, "USERNAME_FIELD", "username"): username}, is_active=True
        ).first()
        if user is None:
            raise CommandError("原操作者账号不存在或已停用，请先创建/确认账号")
        values = {}
        path = options["settings_file"]
        if path is not None:
            parser = configparser.ConfigParser(interpolation=None)
            try:
                with path.open(encoding="utf-8") as source:
                    parser.read_file(source)
                if not parser.has_section("display"):
                    raise ValueError("缺少 display 节")
                values = {
                    key: parser.get("display", key)
                    for key in PREFERENCE_DEFINITIONS
                    if parser.has_option("display", key)
                }
                validate_preferences(values)
                if values.get("default_external_search_source", "jable") not in {
                    "jable",
                    "missav",
                }:
                    raise ValueError("未知旧搜索来源")
            except (OSError, ValueError, configparser.Error) as error:
                raise CommandError(f"旧设置无法读取，未写入数据库: {error}") from error
        if not options["apply"]:
            count = AVResource.objects.filter(
                Q(watched=True) | Q(is_favorite=True)
            ).count()
            self.stdout.write(
                f"预览：{count} 条旧资源状态，{len(values)} 项旧设置；未写入。确认后加 --apply"
            )
            return
        with transaction.atomic():
            lock_user(user.pk)
            created = False
            if values:
                _, created = UserPreferences.objects.get_or_create(
                    user=user, defaults={"preferences": values}
                )
            rows = AVResource.objects.filter(
                Q(watched=True) | Q(is_favorite=True)
            ).iterator(chunk_size=500)
            imported = 0
            for resource in rows:
                _, new = UserResourceState.objects.get_or_create(
                    user=user,
                    resource=resource,
                    defaults={
                        "watched": resource.watched,
                        "is_favorite": resource.is_favorite,
                    },
                )
                imported += int(new)
        settings_result = (
            ("已导入" if created else "保留既有值")
            if values
            else "无设置输入，未创建设置行"
        )
        self.stdout.write(
            f"导入完成：新增 {imported} 条个人状态；设置{settings_result}；源文件未修改"
        )
