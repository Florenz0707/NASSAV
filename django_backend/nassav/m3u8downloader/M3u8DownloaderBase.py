"""
M3U8 下载器基类
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class M3u8DownloaderBase(ABC):
    """M3U8 下载器基类"""

    def __init__(self, proxy: Optional[str] = None):
        """
        初始化下载器

        Args:
            proxy: 代理地址，如 http://127.0.0.1:7077
        """
        self.proxy = proxy

    @abstractmethod
    def get_downloader_name(self) -> str:
        """获取下载器名称"""
        pass

    @abstractmethod
    def download(
        self,
        url: str,
        output_dir: Path,
        output_name: str,
        referer: str,
        user_agent: str,
        thread_count: int = 32,
        retry_count: int = 5,
        progress_callback: Optional[callable] = None,
    ) -> bool:
        """
        下载 M3U8 视频

        Args:
            url: M3U8 地址
            output_dir: 输出目录
            output_name: 输出文件名（不含扩展名）
            referer: Referer 头
            user_agent: User-Agent 头
            thread_count: 下载线程数
            retry_count: 重试次数
            progress_callback: 进度回调函数，参数为 (percent: float, speed: str, eta: str)

        Returns:
            是否下载成功
        """
        pass

    def get_output_file(self, output_dir: Path, output_name: str) -> Optional[Path]:
        """
        获取输出文件路径，检查多种可能的扩展名

        Args:
            output_dir: 输出目录
            output_name: 输出文件名（不含扩展名）

        Returns:
            输出文件路径，如果不存在返回 None
        """
        possible_extensions = [".mp4", ".ts", ".mkv"]
        for ext in possible_extensions:
            file_path = output_dir / f"{output_name}{ext}"
            if file_path.exists():
                return file_path
        return None

    def ensure_mp4(self, output_dir: Path, output_name: str) -> Optional[Path]:
        """
        确保输出文件为 MP4 格式，如果是其他格式则重命名

        Args:
            output_dir: 输出目录
            output_name: 输出文件名（不含扩展名）

        Returns:
            MP4 文件路径，如果不存在返回 None
        """
        output_file = self.get_output_file(output_dir, output_name)
        if not output_file:
            return None

        mp4_path = output_dir / f"{output_name}.mp4"
        if output_file.suffix != ".mp4":
            output_file.rename(mp4_path)
            return mp4_path
        return output_file
