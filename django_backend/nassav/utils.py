"""
工具类模块
"""
import time
from typing import Callable, Any, Optional


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
            self,
            func: Callable[..., Any],
            *args,
            force: bool = False,
            **kwargs
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
