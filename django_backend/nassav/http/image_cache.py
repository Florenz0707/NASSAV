"""Conditional image responses after the caller has authorized and opened bytes."""

import hashlib
import json
import os

from django.http import FileResponse, HttpResponseNotModified
from django.utils.http import parse_etags


def file_validator(handle):
    info = os.fstat(handle.fileno())
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def authorized_image(request, handle, content_type, validator, size=None):
    """Never call before authorization; a matching ETag grants no access itself."""
    try:
        identity = [request.user.pk, request.session.session_key, validator]
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest()
        etag = f'W/"{digest}"'
        supplied = parse_etags(request.headers.get("If-None-Match", ""))
        if any(
            value == "*" or value.removeprefix("W/") == etag[2:] for value in supplied
        ):
            # Recheck stream fences even when no body will be returned.
            handle.read(0)
            handle.close()
            response = HttpResponseNotModified()
        else:
            response = FileResponse(handle, content_type=content_type)
            response.block_size = 65536
            if size is not None:
                response["Content-Length"] = str(size)
        response["ETag"] = etag
        response["Cache-Control"] = "private, no-cache"
        response["Vary"] = "Cookie"
        response["X-Content-Type-Options"] = "nosniff"
        setattr(response, "_nassav_revalidated_image", True)
        return response
    except BaseException:
        handle.close()
        raise
