"""Bounded audit retention; durable command receipts are never pruned here."""

from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from nassav.account_models import AuditEvent


class Command(BaseCommand):
    help = "预览/有界清理管理审计（默认保留180天）；不删除幂等命令账本"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=180)
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["days"] <= 3650 or not 1 <= options["limit"] <= 1000:
            raise CommandError("days必须在1–3650之间，limit必须在1–1000之间")
        ids = list(
            AuditEvent.objects.filter(
                created_at__lt=timezone.now() - timedelta(days=options["days"])
            )
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[: options["limit"]]
        )
        if options["apply"]:
            AuditEvent.objects.filter(pk__in=ids).delete()
        self.stdout.write(
            f"{'清理' if options['apply'] else '预览'} {len(ids)} 条审计；幂等账本保留"
        )
