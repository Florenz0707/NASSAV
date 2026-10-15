"""Single-operator session access for the NASSAV API and task stream."""

from django.conf import settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission


def is_operator(user) -> bool:
    """Only the configured active account may access business data."""
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.get_username() == settings.NASSAV_OPERATOR_USERNAME
    )


def is_admitted(user) -> bool:
    """Explicit managed admission; never upgrade Django staff to an app role."""
    if not settings.MULTI_USER_ENABLED:
        return is_operator(user)
    if not (settings.SHARED_LIBRARY_ENABLED and settings.SOURCE_CREDENTIALS_ENABLED):
        return False
    from nassav.account_policy import account

    return account(user) is not None


class OperatorSessionAuthentication(SessionAuthentication):
    """Return 401 for missing sessions while preserving Django's CSRF checks."""

    def authenticate_header(self, request):
        return 'Session realm="NASSAV"'


class IsOperator(BasePermission):
    def has_permission(self, request, view):
        if not is_admitted(request.user):
            return False
        from nassav.account_policy import permit_business_view

        return permit_business_view(request, view)
