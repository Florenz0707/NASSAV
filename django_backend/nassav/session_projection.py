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
            "source_cache_identity": None,
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
    source_identity = identity
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
    return {
        "authenticated": True,
        "username": request.user.get_username(),
        "user_id": request.user.pk,
        "account_epoch": epoch,
        "cache_identity": identity,
        "source_cache_identity": source_identity,
        "capabilities": capabilities,
    }
