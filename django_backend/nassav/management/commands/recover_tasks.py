"""Run the same fenced recovery scan used by task workers."""

import json
from uuid import UUID
from nassav.task_control_rules import TaskExecutionInvalid
from nassav.task_models import TaskAttempt

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Recover pending dispatch, proven stopped tasks, private cleanup and resource events"

    def add_arguments(self, parser):
        parser.add_argument("--stale-seconds", type=int, default=30)
        parser.add_argument("--retry-seconds", type=int, default=300)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--confirm-stopped-attempt", type=UUID)
        parser.add_argument("--all-writers-stopped", action="store_true")

    def handle(self, *args, **options):
        from nassav.composition import build_task_recovery

        try:
            recovery = build_task_recovery()
            if options["confirm_stopped_attempt"] or options["all_writers_stopped"]:
                if (
                    not options["confirm_stopped_attempt"]
                    or not options["all_writers_stopped"]
                ):
                    raise ValueError(
                        "确认操作必须同时提供 attempt UUID 和 --all-writers-stopped"
                    )
                snapshot = recovery.confirm_stopped(
                    str(options["confirm_stopped_attempt"]), all_writers_stopped=True
                )
                result = {
                    key: snapshot[key]
                    for key in ("job_id", "task_id", "state", "cleanup_state")
                }
            else:
                result = recovery.scan(
                    stale_seconds=options["stale_seconds"],
                    retry_seconds=options["retry_seconds"],
                    limit=options["limit"],
                )
        except (ValueError, TaskExecutionInvalid, TaskAttempt.DoesNotExist) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, ensure_ascii=False))
