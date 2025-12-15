"""
N_m3u8DL-RE 下载器实现
https://github.com/nilaoda/N_m3u8DL-RE
"""
import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from django.conf import settings
from loguru import logger

from .M3u8DownloaderBase import M3u8DownloaderBase


class N_m3u8DL_RE(M3u8DownloaderBase):
    """N_m3u8DL-RE 下载器"""

    def __init__(self, proxy: Optional[str] = None):
        super().__init__(proxy)

        # 工具路径
        tools_dir = settings.BASE_DIR / "tools"
        if platform.system() == 'Windows':
            self.tool_path = str(tools_dir / "N_m3u8DL-RE.exe")
        else:
            self.tool_path = str(tools_dir / "N_m3u8DL-RE")

    def get_downloader_name(self) -> str:
        return "N_m3u8DL-RE"

    def download(
            self,
            url: str,
            output_dir: Path,
            output_name: str,
            referer: str,
            user_agent: str,
            thread_count: int = 32,
            retry_count: int = 5,
    ) -> bool:
        """使用 N_m3u8DL-RE 下载 M3U8 视频"""
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = output_dir / "temp"

        try:
            # 构建命令
            cmd = [
                self.tool_path,
                url,
                "--tmp-dir", str(tmp_path),
                "--save-dir", str(output_dir),
                "--save-name", output_name,
                "--thread-count", str(thread_count),
                "--download-retry-count", str(retry_count),
                "--del-after-done",  # 下载完成后删除临时文件
                "--auto-select",  # 自动选择最佳质量
                "--no-log",  # 禁用日志文件
                "-H", f"Referer: {referer}",
                "-H", f"User-Agent: {user_agent}",
            ]

            logger.debug(f"执行命令: {' '.join(cmd)}")

            # 设置环境变量（代理）
            env = os.environ.copy()
            if self.proxy:
                env['http_proxy'] = self.proxy
                env['https_proxy'] = self.proxy
                env['HTTP_PROXY'] = self.proxy
                env['HTTPS_PROXY'] = self.proxy
                logger.debug(f"使用代理: {self.proxy}")

            # 直接运行，让工具输出到终端显示进度
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=False,
            )

            if result.returncode != 0:
                logger.error(f"N_m3u8DL-RE 下载失败，退出码: {result.returncode}")
                return False

            # 检查输出文件
            output_file = self.get_output_file(output_dir, output_name)
            if output_file:
                file_size = output_file.stat().st_size
                size_mb = file_size / (1024 * 1024)
                logger.info(f"[{output_name}] 下载完成: {size_mb:.1f} MB")
                return True
            else:
                logger.error(f"[{output_name}] 未找到输出文件")
                return False

        except FileNotFoundError:
            logger.error(f"N_m3u8DL-RE 工具不存在: {self.tool_path}")
            return False
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
