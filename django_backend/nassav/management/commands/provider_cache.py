"""Inspect disposable provider caches; deletion requires explicit --apply."""

import json
from django.core.management.base import BaseCommand, CommandError
from nassav.resource_cache_maintenance import DjangoProviderCacheMaintenance


class Command(BaseCommand):
    help = "统计来源/刮削/播放缓存，默认预览有界清理，--apply 实际清理"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        service = DjangoProviderCacheMaintenance()
        try:
            cleanup = service.purge(apply=options["apply"], limit=options["limit"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            json.dumps(
                {
                    "applied": options["apply"],
                    "cleanup": cleanup,
                    "statistics": service.statistics(),
                }
            )
        )
