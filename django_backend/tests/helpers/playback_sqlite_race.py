"""Isolated file/WAL database reproduces an active media heartbeat during control."""

import os
import sqlite3
from threading import Thread
from uuid import uuid4

os.environ["DJANGO_SETTINGS_MODULE"] = "django_project.refactoring_test_settings"
import django

django.setup()
from django.core.management import call_command
from django.db import connection
from django.contrib.auth import get_user_model
from nassav.models import AVResource
from nassav.playback import records
from nassav.playback.contracts import PlaybackDescriptor

call_command("migrate", verbosity=0)
user = get_user_model().objects.create(username="control-race")
resource = AVResource.objects.create(avid="RACE-1", source="Jable")
row = records.submit(user.pk, "login", resource.avid, uuid4())
records.ready(
    records.claim(row.pk),
    PlaybackDescriptor(
        "https://media.example/v",
        "https://source.example/detail",
        "ua",
        "jable",
        None,
        None,
    ),
)
records.observe_identity(row.pk, 1, "root", "manifest", "hash")
row.refresh_from_db()
original_expiry = row.absolute_expires_at

for index, action in enumerate(("refresh", "close")):
    row.refresh_from_db()
    threads = []
    writer_errors = []
    first = None

    def concurrent_writer():
        try:
            with sqlite3.connect(connection.settings_dict["NAME"], timeout=5) as db:
                assert (
                    db.execute(
                        "UPDATE nassav_playback_session SET last_seen_at=datetime('now',?) WHERE id=?",
                        (f"+{index + 1} seconds", row.pk.hex),
                    ).rowcount
                    == 1
                )
        except Exception as error:
            writer_errors.append(type(error).__name__)

    def interleave(execute, sql, params, many, context):
        global first
        result = execute(sql, params, many, context)
        verb = sql.lstrip().split()[0].upper()
        if first is None and verb in {"SELECT", "UPDATE"}:
            first = verb
            thread = Thread(target=concurrent_writer)
            threads.append(thread)
            thread.start()
            # A read transaction permits the external WAL writer; a write transaction
            # holds it until commit. Waiting only for a reader reproduces SQLITE_BUSY_SNAPSHOT.
            if verb == "SELECT":
                thread.join(3)
        return result

    try:
        with connection.execute_wrapper(interleave):
            result = getattr(records, action)(
                row.pk, user.pk, "login", row.version, uuid4()
            )
        assert result.state == ("queued" if action == "refresh" else "closed")
        assert result.absolute_expires_at == original_expiry
    finally:
        for thread in threads:
            thread.join(8)
    assert not writer_errors and all(not thread.is_alive() for thread in threads)
print("WAL control race passed")
