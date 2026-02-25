"""
FlareSolverr 集成测试脚本

目的：验证通过 FlareSolverr 绕过 Cloudflare 验证，自动获取 MissAV 的 cookie 并访问资源

用法：
  uv run pytest tests/test_flaresolverr.py -v -s
  uv run python tests/test_flaresolverr.py  # 直接运行（交互模式）

参数：
  FLARESOLVERR_URL  环境变量，FlareSolverr 服务地址，默认 http://localhost:8191
  TEST_AVID         环境变量，测试用的番号，默认 SSIS-001
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

import pytest
import requests
from django.conf import settings
from loguru import logger

FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "http://localhost:8191")
TEST_AVID = os.environ.get("TEST_AVID", "SSIS-001")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _call_flaresolverr(target_url: str, timeout_ms: int = 60000) -> dict | None:
    """向 FlareSolverr 发送 request.get 请求，返回 solution 字典或 None"""
    payload = {"cmd": "request.get", "url": target_url, "maxTimeout": timeout_ms}
    try:
        resp = requests.post(
            f"{FLARESOLVERR_URL}/v1",
            json=payload,
            timeout=timeout_ms / 1000 + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok":
            return data.get("solution")
        logger.error(f"FlareSolverr 返回非 ok 状态: {data.get('message')}")
        return None
    except Exception as e:
        logger.error(f"FlareSolverr 请求失败: {e}")
        return None


def _cookies_list_to_str(cookies: list[dict]) -> str:
    """将 FlareSolverr 返回的 cookies 列表转为 Cookie 请求头字符串"""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


def test_flaresolverr_health():
    """测试 1：FlareSolverr 服务是否可达"""
    print(f"\n{'='*60}")
    print(f"测试 1: FlareSolverr 健康检查 ({FLARESOLVERR_URL})")
    print("=" * 60)

    try:
        resp = requests.get(f"{FLARESOLVERR_URL}/health", timeout=5)
        assert resp.status_code == 200, f"健康检查失败，状态码: {resp.status_code}"
        data = resp.json()
        print(f"✅ FlareSolverr 正常运行，版本: {data.get('version', 'unknown')}")
    except requests.ConnectionError:
        print(f"❌ 无法连接到 FlareSolverr ({FLARESOLVERR_URL})")
        print("   请确认 FlareSolverr 已启动，参考脚本顶部的环境配置说明")
        raise


def test_flaresolverr_get_missav_cookie():
    """测试 2：通过 FlareSolverr 获取 MissAV 的 Cloudflare cookie（不写库，仅验证）"""
    print(f"\n{'='*60}")
    print("测试 2: 获取 MissAV Cloudflare Cookie")
    print("=" * 60)

    source_config = settings.SOURCE_CONFIG.get("missav", {})
    domain = source_config.get("domain", "missav.ai")
    home_url = f"https://{domain}/"

    print(f"目标 URL: {home_url}")
    print("正在通过 FlareSolverr 解决 Cloudflare 验证（最长等待 60 秒）...")

    solution = _call_flaresolverr(home_url)
    assert solution is not None, "FlareSolverr 未能返回有效 solution"

    cookies = solution.get("cookies", [])
    user_agent = solution.get("userAgent", "")
    status = solution.get("status", 0)

    print(f"\n响应状态码: {status}")
    print(f"User-Agent: {user_agent}")
    print(f"获取到的 Cookie 数量: {len(cookies)}")

    cookie_names = [c["name"] for c in cookies]
    print(f"Cookie 名称: {cookie_names}")

    # cf_clearance 是 Cloudflare 验证通过的关键 cookie
    cf_cookie = next((c for c in cookies if c["name"] == "cf_clearance"), None)
    assert cf_cookie is not None, (
        "未获取到 cf_clearance cookie，Cloudflare 验证可能未通过\n"
        f"  获取到的 cookies: {cookie_names}"
    )

    print(f"\n✅ 成功获取 cf_clearance: {cf_cookie['value'][:30]}...")


def test_flaresolverr_fetch_page_with_cookie():
    """测试 3：通过 FlareSolverr 直接访问 MissAV 番号页面

    cf_clearance 与 FlareSolverr 使用的浏览器 TLS 指纹绑定，
    不能直接用 curl_cffi 携带该 cookie 请求（指纹不匹配会 403）。
    正确做法是让 FlareSolverr 代理整个页面请求。
    """
    print(f"\n{'='*60}")
    print(f"测试 3: 通过 FlareSolverr 访问 MissAV 页面 (AVID: {TEST_AVID})")
    print("=" * 60)

    source_config = settings.SOURCE_CONFIG.get(
        "missav",
    )
    domain = source_config.get("domain", "missav.ai")
    avid_lower = TEST_AVID.lower()

    # 直接让 FlareSolverr 请求番号页面
    target_url = f"https://{domain}/cn/{avid_lower}"
    print(f"目标页面: {target_url}")
    print("正在通过 FlareSolverr 请求页面（最长等待 60 秒）...")

    solution = _call_flaresolverr(target_url)
    assert solution is not None, "FlareSolverr 未能返回有效 solution"

    status = solution.get("status", 0)
    html = solution.get("response", "")

    print(f"响应状态码: {status}")
    print(f"HTML 长度: {len(html)} 字符")

    assert status == 200, f"页面请求失败，状态码: {status}"
    assert "Just a moment" not in html, "仍被 Cloudflare 拦截"
    assert "cf-browser-verification" not in html, "仍被 Cloudflare 拦截"

    print(f"✅ 成功访问页面，未被 Cloudflare 拦截")

    # 尝试解析 UUID（验证页面内容有效）
    import re

    uuid_match = re.search(r"m3u8\|([a-f0-9|]+)\|com\|surrit\|https\|video", html)
    if uuid_match:
        uuid = "-".join(uuid_match.group(1).split("|")[::-1])
        print(f"✅ 成功提取 UUID: {uuid}")
    else:
        print(f"⚠️  未找到 UUID（该番号可能在 MissAV 上不存在，但页面访问正常）")


@pytest.mark.django_db
def test_flaresolverr_save_cookie_to_db():
    """测试 4：将 FlareSolverr 获取的 cookie 保存到数据库"""
    print(f"\n{'='*60}")
    print("测试 4: 保存 Cookie 到数据库")
    print("=" * 60)

    from nassav.models import SourceCookie

    source_config = settings.SOURCE_CONFIG.get("missav", {})
    domain = source_config.get("domain", "missav.ai")
    home_url = f"https://{domain}/"

    solution = _call_flaresolverr(home_url)
    assert solution is not None, "无法获取 FlareSolverr solution"

    cookies = solution.get("cookies", [])
    user_agent = solution.get("userAgent", "")
    cookie_str = _cookies_list_to_str(cookies)

    assert cookie_str, "cookie 字符串为空"

    SourceCookie.objects.update_or_create(
        source_name="MissAV",
        defaults={"cookie": cookie_str},
    )

    # 验证已保存
    saved = SourceCookie.objects.get(source_name="MissAV")
    assert saved.cookie == cookie_str

    print(f"✅ Cookie 已保存到数据库")
    print(f"   Cookie 长度: {len(cookie_str)} 字符")
    print(f"   User-Agent: {user_agent}")
    print(f"\n提示：后续请求需要使用相同的 User-Agent，否则 cf_clearance 无效")
    print(f"   建议将 User-Agent 也保存到配置或数据库中")


# ---------------------------------------------------------------------------
# 直接运行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("█" + " " * 18 + "FlareSolverr 集成测试" + " " * 19 + "█")
    print("█" * 60)
    print(f"\nFlareSolverr 地址: {FLARESOLVERR_URL}")
    print(f"测试番号: {TEST_AVID}\n")

    tests = [
        ("健康检查", test_flaresolverr_health),
        ("获取 Cookie", test_flaresolverr_get_missav_cookie),
        ("访问页面", test_flaresolverr_fetch_page_with_cookie),
        ("保存到数据库", test_flaresolverr_save_cookie_to_db),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"\n❌ [{name}] 失败: {e}")
            import traceback

            traceback.print_exc()
        input("\n按 Enter 继续下一项测试...")

    print(f"\n{'='*60}")
    print(f"测试完成: {passed}/{len(tests)} 通过")
    print("=" * 60)
