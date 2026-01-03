"""
工具类模块
"""
import time
from typing import Any, Callable, Optional


class Throttler:
    """
    节流器类 - 用于限制函数调用频率

    支持:
    - 基于时间间隔的节流
    - 对特定条件（如 100% 进度）强制执行

    使用示例:
        throttler = Throttler(min_interval=1.0)

        def on_progress(percent, speed):
            # 只有通过节流检查才会执行
            send_notification(percent, speed)

        # 在循环中使用
        for percent in progress_updates:
            if throttler.should_execute(force=(percent >= 100)):
                on_progress(percent, speed)
    """

    def __init__(self, min_interval: float = 1.0):
        """
        初始化节流器

        Args:
            min_interval: 最小时间间隔（秒），默认 1.0 秒
        """
        self.min_interval = min_interval
        self._last_execute_time: Optional[float] = None

    def should_execute(self, force: bool = False) -> bool:
        """
        检查是否应该执行（基于时间间隔）

        Args:
            force: 是否强制执行（忽略时间间隔限制）

        Returns:
            bool: 如果应该执行返回 True，否则返回 False
        """
        current_time = time.time()

        # 强制执行
        if force:
            self._last_execute_time = current_time
            return True

        # 首次执行
        if self._last_execute_time is None:
            self._last_execute_time = current_time
            return True

        # 检查时间间隔
        elapsed = current_time - self._last_execute_time
        if elapsed >= self.min_interval:
            self._last_execute_time = current_time
            return True

        return False

    def reset(self):
        """重置节流器状态"""
        self._last_execute_time = None

    def execute_if_allowed(
        self, func: Callable[..., Any], *args, force: bool = False, **kwargs
    ) -> Optional[Any]:
        """
        如果通过节流检查，则执行函数

        Args:
            func: 要执行的函数
            *args: 函数参数
            force: 是否强制执行
            **kwargs: 函数关键字参数

        Returns:
            函数返回值，如果未执行则返回 None
        """
        if self.should_execute(force=force):
            return func(*args, **kwargs)
        return None


def generate_thumbnail(source_path, dest_path, width: int):
    """Generate a JPEG thumbnail with given width while preserving aspect ratio.

    Args:
        source_path (str or Path): path to source image
        dest_path (str or Path): path to save thumbnail (parent dirs will be created)
        width (int): target width in pixels

    Returns:
        bool: True on success, False otherwise
    """
    try:
        from PIL import Image
    except Exception:
        return False

    from pathlib import Path

    sp = Path(source_path)
    dp = Path(dest_path)
    dp.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(sp) as im:
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")

            w, h = im.size
            if w <= width:
                im.save(dp, format="JPEG", quality=85)
                return True

            ratio = width / float(w)
            new_h = int(h * ratio)
            im = im.resize((width, new_h), Image.LANCZOS)
            im.save(dp, format="JPEG", quality=85)
            return True
    except Exception:
        return False


def generate_etag_from_text(text: str) -> str:
    """Return a quoted ETag string computed from input text."""
    try:
        import hashlib

        h = hashlib.md5()
        h.update(text.encode("utf-8"))
        return '"' + h.hexdigest() + '"'
    except Exception:
        return '"0"'


def generate_etag_for_file(path) -> str:
    """Generate an ETag from file mtime and size (quoted string)."""
    from pathlib import Path

    p = Path(path)
    try:
        st = p.stat()
        # use mtime_ns for higher precision
        return '"%s-%s"' % (st.st_mtime_ns, st.st_size)
    except Exception:
        return '"0"'


def parse_http_if_modified_since(header_value):
    """Parse If-Modified-Since header value to epoch seconds (int) or None."""
    if not header_value:
        return None
    try:
        from django.utils.http import parse_http_date_safe

        val = parse_http_date_safe(header_value)
        return val
    except Exception:
        return None


def download_avatar(url: str, dest_path, max_retries: int = 3) -> bool:
    """下载演员头像图片

    Args:
        url: 头像图片URL
        dest_path: 目标文件路径（Path或str）
        max_retries: 最大重试次数

    Returns:
        bool: 下载成功返回True，否则返回False
    """
    from pathlib import Path

    from loguru import logger

    try:
        from curl_cffi import requests
    except ImportError:
        logger.error("curl_cffi未安装，无法下载头像")
        return False

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 设置请求头（模拟浏览器，添加Referer）
    headers = {
        "Referer": "https://www.javbus.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(
                url, headers=headers, timeout=10, impersonate="chrome110"
            )
            if response.status_code == 200:
                dest.write_bytes(response.content)
                logger.info(f"头像下载成功: {dest.name}")
                return True
            else:
                logger.warning(f"头像下载失败 (HTTP {response.status_code}): {url}")
        except Exception as e:
            logger.warning(f"头像下载失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time

                time.sleep(1)  # 重试前等待1秒

    return False
