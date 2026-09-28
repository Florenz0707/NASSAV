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


class OperatorSessionAuthentication(SessionAuthentication):
    """Return 401 for missing sessions while preserving Django's CSRF checks."""

    def authenticate_header(self, request):
        return 'Session realm="NASSAV"'


class IsOperator(BasePermission):
    def has_permission(self, request, view):
        return is_operator(request.user)
