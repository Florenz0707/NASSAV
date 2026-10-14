"""Private image HTTP delivery; authorization and leases belong to the service."""

from django.http import FileResponse
from nassav import composition
from nassav.library_assets import LibraryImages


def image_response(request, entry, asset_id=None):
    version = LibraryImages.require_version(entry)
    handle, content_type, size = composition.build_library_images().open(
        request.user.pk, request.session.session_key, version, asset_id
    )
    try:
        response = FileResponse(handle, content_type=content_type)
        response.block_size = 65536
        response["Content-Length"] = str(size)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    except BaseException:
        handle.close()
        raise
