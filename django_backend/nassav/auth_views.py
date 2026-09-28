"""Browser session entry points; business API permissions live in ``access``."""

import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .access import is_operator


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
    active = is_operator(request.user)
    return _response(
        200,
        "success",
        {
            "authenticated": active,
            "username": request.user.get_username() if active else None,
        },
    )


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
    if user is None or not is_operator(user):
        return _response(401, "用户名或密码错误")
    login(request, user)
    return _response(
        200, "success", {"authenticated": True, "username": user.get_username()}
    )


@require_POST
@csrf_protect
def logout_view(request):
    if not is_operator(request.user):
        return _response(401, "请先登录")
    logout(request)
    return _response(200, "success", {"authenticated": False})
