"""Browser session entry points; business API permissions live in ``access``."""

import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .access import is_admitted


def _response(status: int, message: str, data=None) -> JsonResponse:
    response = JsonResponse(
        {"code": status, "message": message, "data": data}, status=status
    )
    response["Cache-Control"] = "no-store"
    return response


@require_GET
@ensure_csrf_cookie
def session_view(request):
    """Issue a CSRF cookie and report whether this browser has an operator session."""
    from nassav.session_projection import browser_session

    return _response(200, "success", browser_session(request))


@require_POST
@csrf_protect
def login_view(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, "请求格式错误")
    if not isinstance(payload, dict):
        return _response(400, "请求格式错误")
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return _response(400, "请输入用户名和密码")
    user = authenticate(request, username=username, password=password)
    if user is None or not is_admitted(user):
        return _response(401, "用户名或密码错误")
    from django.db import transaction
    from nassav.personal_state import lock_user
    from nassav.account_models import UserLoginSession

    try:
        with transaction.atomic():
            lock_user(user.pk)
            from django.contrib.auth import get_user_model

            current = get_user_model().objects.get(pk=user.pk)
            if current.password != user.password or not is_admitted(current):
                raise PermissionError("Account changed during authentication")
            user = current
            login(request, user)
            request.session.save()
            UserLoginSession.objects.get_or_create(
                user=user, session_id=request.session.session_key
            )
    except PermissionError:
        return _response(401, "账号不可用")
    from nassav.session_projection import browser_session

    return _response(200, "success", browser_session(request))


@require_POST
@csrf_protect
def logout_view(request):
    if not is_admitted(request.user):
        return _response(401, "请先登录")
    from nassav.browser_context import require_browser_context, BrowserContextChanged

    try:
        require_browser_context(request)
    except BrowserContextChanged as error:
        return _response(
            409, str(error.detail), {"error_code": "browser_context_changed"}
        )
    from django.conf import settings

    if getattr(settings, "PLAYBACK_ENABLED", False):
        from nassav.playback.records import close_login

        close_login(request.session.session_key)
    logout(request)
    return _response(200, "success", {"authenticated": False})
