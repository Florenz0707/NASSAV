"""Internal readiness endpoint for the Compose gateway."""

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def healthz(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        redis.from_url(settings.REDIS_URL, socket_timeout=2).ping()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
