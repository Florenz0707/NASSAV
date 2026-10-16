"""Private image HTTP delivery; authorization and leases belong to the service."""

from nassav import composition
from nassav.library_assets import LibraryImages


def image_response(request, entry, asset_id=None):
    version = LibraryImages.require_version(entry)
    from nassav.http.image_cache import authorized_image
    from nassav.version_image_files import image_asset

    asset = image_asset(version, asset_id)
    handle, content_type, size = composition.build_library_images().open(
        request.user.pk, request.session.session_key, version, asset_id
    )
    return authorized_image(
        request, handle, content_type, [str(version.pk), asset["sha256"]], size
    )


def catalog_avatar_response(request, term_id):
    from django.http import HttpResponseRedirect
    from nassav.catalog_projection import own_term, name_key
    from nassav.catalog_presentation import avatar_urls
    from nassav.library_catalog import held_entries
    from nassav.library_membership import LibraryNotFound
    from nassav.models import Actor

    term = own_term(request.user.pk, "actor", term_id)
    url = avatar_urls(request.user.pk, [term]).get(term.pk)
    if url and "/library/entries/" in url:
        response = HttpResponseRedirect(url)
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        return response
    legacy_ids = (
        held_entries(request.user.pk)
        .filter(current_version__isnull=True, catalog_links__term=term)
        .values_list("pool__resource_id", flat=True)
    )
    actor = next(
        (
            row
            for row in Actor.objects.filter(resources__pk__in=legacy_ids).distinct()
            if name_key(row.name) == term.name_key and row.avatar_filename
        ),
        None,
    )
    if actor is None:
        raise LibraryNotFound("Avatar not available")
    handle = composition.build_legacy_avatar_reader()(actor.avatar_filename)
    from nassav.http.image_cache import authorized_image, file_validator

    try:
        validator = file_validator(handle)
    except BaseException:
        handle.close()
        raise
    return authorized_image(request, handle, "image/jpeg", validator)
