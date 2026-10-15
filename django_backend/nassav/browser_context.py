"""Browser context precondition, in addition to login, CSRF and object policy."""

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import APIException
from nassav.access import is_admitted
from nassav.session_projection import browser_identity


class BrowserContextChanged(APIException):
    status_code = 409
    default_detail = "登录上下文已改变，请刷新后重试"
    default_code = "browser_context_changed"


# These opaque references already bind to the user and revalidate their ledger.
# Generic AVID cover/avatar URLs instead carry an explicit browser precondition.
OWNED_IMAGE_ROUTES = frozenset({"library-entry-image", "recommendations-cover"})
CONTEXT_QUERY_ROUTES = frozenset({"resource-cover", "actor-avatar"})


def require_browser_context(request):
    if not settings.MULTI_USER_ENABLED or not is_admitted(request.user):
        return
    route = getattr(getattr(request, "resolver_match", None), "url_name", None)
    if request.method in {"GET", "HEAD"} and route in OWNED_IMAGE_ROUTES:
        return
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    supplied = request.headers.get("X-NASSAV-Context", "")
    if (
        not supplied
        and request.method in {"GET", "HEAD"}
        and route in CONTEXT_QUERY_ROUTES
    ):
        supplied = request.GET.get("_context", "")
    if (
        not session_key
        or not supplied
        or not constant_time_compare(
            supplied, browser_identity(request.user, session_key) or ""
        )
    ):
        raise BrowserContextChanged()
