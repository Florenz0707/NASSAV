"""Read-only browser capabilities; server authorization remains authoritative."""

from django.conf import settings
from django.utils.crypto import salted_hmac
from nassav.access import is_operator
from nassav.account_policy import account


def browser_session(request):
    if not is_operator(request.user):
        return {
            "authenticated": False,
            "username": None,
            "user_id": None,
            "account_epoch": None,
            "cache_identity": None,
            "capabilities": {},
        }
    role = account(request.user)
    shared = bool(settings.SHARED_LIBRARY_ENABLED and role is not None)
    admin = bool(role and role.role == "admin")
    capabilities = {
        "shared_library": shared,
        "personal_source_credentials": bool(settings.SOURCE_CREDENTIALS_ENABLED),
        "app_admin": admin,
        "resource_gc": bool(shared and admin and settings.RESOURCE_GC_ENABLED),
        "legacy_asset_controls": not settings.SHARED_LIBRARY_ENABLED
        and (role is None or admin),
        "ordinary_login": False,
    }
    epoch = role.version if role else 0
    # Never expose the session key, credentials, or a reusable authorization token.
    context = [
        request.user.pk,
        request.session.session_key,
        epoch,
        sorted(capabilities.items()),
    ]
    identity = salted_hmac("nassav-browser-cache-v1", repr(context)).hexdigest()
    return {
        "authenticated": True,
        "username": request.user.get_username(),
        "user_id": request.user.pk,
        "account_epoch": epoch,
        "cache_identity": identity,
        "capabilities": capabilities,
    }
