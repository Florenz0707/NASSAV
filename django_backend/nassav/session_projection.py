"""Read-only browser capabilities; server authorization remains authoritative."""

from django.conf import settings
from django.utils.crypto import salted_hmac
from nassav.access import is_admitted
from nassav.account_policy import account


def _principal(user, session_key):
    if not is_admitted(user):
        return {
            "authenticated": False,
            "username": None,
            "user_id": None,
            "account_epoch": None,
            "cache_identity": None,
            "source_cache_identity": None,
            "capabilities": {},
        }
    role = account(user)
    shared = bool(settings.SHARED_LIBRARY_ENABLED and role is not None)
    admin = bool(role and role.role == "admin")
    capabilities = {
        "shared_library": shared,
        "personal_source_credentials": bool(settings.SOURCE_CREDENTIALS_ENABLED),
        "app_admin": admin,
        "resource_gc": bool(shared and admin and settings.RESOURCE_GC_ENABLED),
        "legacy_asset_controls": not settings.SHARED_LIBRARY_ENABLED
        and (role is None or admin),
        "ordinary_login": bool(settings.MULTI_USER_ENABLED),
    }
    epoch = role.version if role else 0
    # Never expose the session key, credentials, or a reusable authorization token.
    context = [
        user.pk,
        session_key,
        epoch,
        sorted(capabilities.items()),
    ]
    identity = salted_hmac("nassav-browser-cache-v1", repr(context)).hexdigest()
    return {
        "authenticated": True,
        "username": user.get_username(),
        "user_id": user.pk,
        "account_epoch": epoch,
        "cache_identity": identity,
        "source_cache_identity": identity,
        "capabilities": capabilities,
    }


def browser_identity(user, session_key):
    return _principal(user, session_key)["cache_identity"]


def browser_session(request):
    result = _principal(request.user, request.session.session_key)
    if not result["authenticated"]:
        return result
    identity = result["cache_identity"]
    if settings.SOURCE_CREDENTIALS_ENABLED:
        from django.db.models import Q
        from nassav.credential_models import SourceCredential, SourceCredentialKeyPolicy

        # Only this user's private references and system metadata affect their
        # source namespace. Ciphertexts and secrets never enter this projection.
        refs = list(
            SourceCredential.objects.filter(
                Q(scope="system", owner__isnull=True)
                | Q(scope="personal", owner_id=request.user.pk)
            )
            .order_by("pk")
            .values_list("pk", "version", "state")
        )
        policy = (
            SourceCredentialKeyPolicy.objects.filter(pk=1)
            .values_list("version", flat=True)
            .first()
        )
        source_identity = salted_hmac(
            "nassav-browser-source-cache-v1", repr([identity, refs, policy])
        ).hexdigest()
        result["source_cache_identity"] = source_identity
    return result
