"""FlareSolverr 客户端

封装 FlareSolverr REST API，用于绕过 Cloudflare 验证。

注意：cf_clearance cookie 与 FlareSolverr 浏览器的 TLS 指纹绑定，
获取 cookie 后的后续请求也必须通过 FlareSolverr 代理，不能直接用 curl_cffi。
"""

from typing import Optional

import requests
from loguru import logger


class FlareSolverrClient:
    """FlareSolverr API 客户端"""

    def __init__(self, base_url: str, timeout_ms: int = 60000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        # HTTP 请求超时（秒）= FlareSolverr 超时 + 10s 缓冲
        self._http_timeout = timeout_ms / 1000 + 10

    def is_available(self) -> bool:
        """检查 FlareSolverr 服务是否可达"""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get(self, url: str) -> Optional[dict]:
        """通过 FlareSolverr 发起 GET 请求

        Returns:
            solution 字典，包含 status、response（HTML）、cookies、userAgent，
            或 None（请求失败）
        """
        payload = {"cmd": "request.get", "url": url, "maxTimeout": self.timeout_ms}
        try:
            resp = requests.post(
                f"{self.base_url}/v1",
                json=payload,
                timeout=self._http_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                return data.get("solution")
            logger.warning(f"FlareSolverr 返回非 ok 状态: {data.get('message')}")
            return None
        except Exception as e:
            logger.error(f"FlareSolverr 请求失败 [{url}]: {e}")
            return None

    def get_html(self, url: str) -> Optional[str]:
        """获取页面 HTML，失败返回 None"""
        solution = self.get(url)
        if solution and solution.get("status") == 200:
            return solution.get("response")
        if solution:
            logger.error(f"FlareSolverr 页面请求失败，状态码: {solution.get('status')}")
        return None

    def get_cookies_str(self, url: str) -> Optional[str]:
        """获取目标站点的 cookie 字符串（含 cf_clearance），失败返回 None"""
        solution = self.get(url)
        if not solution:
            return None
        cookies = solution.get("cookies", [])
        if not cookies:
            logger.warning(f"FlareSolverr 未返回任何 cookie")
            return None
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
