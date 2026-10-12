"""Bounded retries for short, restartable SQLite transactions only."""

import time
from functools import wraps
from django.db import OperationalError, connection


def retry_sqlite_contention(method):
    @wraps(method)
    def retry(*args, **kwargs):
        for attempt in range(8):
            try:
                return method(*args, **kwargs)
            except OperationalError as error:
                if (
                    connection.vendor != "sqlite"
                    or "locked" not in str(error).lower()
                    or attempt == 7
                ):
                    raise
                time.sleep(0.01 * (attempt + 1))

    return retry
