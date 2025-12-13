"""
服务层：封装下载器和刮削器逻辑
"""
import json
import os
import re
import platform
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, asdict
from loguru import logger
from curl_cffi import requests
from PIL import Image
from django.conf import settings


# 初始化日志
LOG_DIR = settings.LOG_DIR
logger.add(
    str(LOG_DIR / "{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="7 days",
    enqueue=False,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


@dataclass
class AVDownloadInfo:
    """下载信息数据类"""
    m3u8: str = ""
    title: str = ""
    avid: str = ""
    source: str = ""

    def to_json(self, file_path: str, indent: int = 2) -> bool:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=indent)
            return True
        except (IOError, TypeError) as e:
            logger.error(f"JSON序列化失败: {str(e)}")
            return False


# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}


class DownloaderBase:
    """下载器基类"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        self.proxy = proxy
        self.proxies = {'http': proxy, 'https': proxy} if proxy else None
        self.timeout = timeout
        self.domain = ""

    def set_domain(self, domain: str):
        self.domain = domain

    def get_downloader_name(self) -> str:
        raise NotImplementedError

    def get_html(self, avid: str) -> Optional[str]:
        raise NotImplementedError

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        raise NotImplementedError

    def _fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        logger.debug(f"fetch url: {url}")
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=headers,
                timeout=self.timeout,
                impersonate="chrome110",
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"请求失败: {str(e)}")
            return None

    def _download_file(self, url: str, save_path: str, referer: str = "") -> bool:
        """下载文件到指定路径"""
        logger.debug(f"download {url} to {save_path}")
        try:
            headers = HEADERS.copy()
            if referer:
                headers["Referer"] = referer
            response = requests.get(
                url,
                stream=True,
                impersonate="chrome110",
                proxies=self.proxies,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False


class MissAVDownloader(DownloaderBase):
    """MissAV下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('missav', {})
        self.domain = source_config.get('domain', 'missav.ai')

    def get_downloader_name(self) -> str:
        return "MissAV"

    def get_html(self, avid: str) -> Optional[str]:
        """根据avid获取HTML"""
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/cn/{avid_lower}-chinese-subtitle',
            f'https://{self.domain}/cn/{avid_lower}-uncensored-leak',
            f'https://{self.domain}/cn/{avid_lower}',
            f'https://{self.domain}/dm13/cn/{avid_lower}',
        ]
        for url in urls:
            content = self._fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        """解析HTML获取下载信息"""
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        # 提取m3u8
        uuid = self._extract_uuid(html)
        if uuid:
            playlist_url = f"https://surrit.com/{uuid}/playlist.m3u8"
            result = self._get_highest_quality_m3u8(playlist_url)
            if result:
                m3u8_url, resolution = result
                logger.debug(f"最高清晰度: {resolution}\nM3U8链接: {m3u8_url}")
                info.m3u8 = m3u8_url
            else:
                logger.error("未找到有效视频流")
                return None
        else:
            logger.error("未找到有效uuid")
            return None

        # 提取基本信息
        if not self._extract_metadata(html, info):
            return None

        return info

    @staticmethod
    def _extract_uuid(html: str) -> Optional[str]:
        try:
            match = re.search(r"m3u8\|([a-f0-9\|]+)\|com\|surrit\|https\|video", html)
            if match:
                return "-".join(match.group(1).split("|")[::-1])
            return None
        except Exception as e:
            logger.error(f"UUID提取异常: {str(e)}")
            return None

    @staticmethod
    def _extract_metadata(html: str, metadata: AVDownloadInfo) -> bool:
        try:
            og_title = re.search(r'<meta property="og:title" content="(.*?)"', html)
            if og_title:
                title_content = og_title.group(1)
                code_match = re.search(r'^([A-Z]+(?:-[A-Z]+)*-\d+)', title_content)
                if code_match:
                    metadata.avid = code_match.group(1)
                    metadata.title = title_content.replace(metadata.avid, '').strip()
                else:
                    metadata.title = title_content.strip()
            return True
        except Exception as e:
            logger.error(f"元数据解析异常: {str(e)}")
            return False

    @staticmethod
    def _get_highest_quality_m3u8(playlist_url: str) -> Optional[Tuple[str, str]]:
        try:
            response = requests.get(playlist_url, timeout=10, impersonate="chrome110")
            response.raise_for_status()
            playlist_content = response.text

            streams = []
            pattern = re.compile(
                r'#EXT-X-STREAM-INF:BANDWIDTH=(\d+),.*?RESOLUTION=(\d+x\d+).*?\n(.*)'
            )

            for match in pattern.finditer(playlist_content):
                bandwidth = int(match.group(1))
                resolution = match.group(2)
                url = match.group(3).strip()
                streams.append((bandwidth, resolution, url))

            streams.sort(reverse=True, key=lambda x: x[0])
            logger.debug(streams)

            if streams:
                best_stream = streams[0]
                base_url = playlist_url.rsplit('/', 1)[0]
                full_url = f"{base_url}/{best_stream[2]}" if not best_stream[2].startswith('http') else best_stream[2]
                return full_url, best_stream[1]
            return None

        except Exception as e:
            logger.error(f"获取最高质量流失败: {str(e)}")
            return None

    def get_cover_url(self, html: str) -> Optional[str]:
        """从HTML中提取封面URL"""
        try:
            # MissAV的封面通常在og:image标签中
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None


class JableDownloader(DownloaderBase):
    """Jable下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('jable', {})
        self.domain = source_config.get('domain', 'jable.tv')

    def get_downloader_name(self) -> str:
        return "Jable"

    def get_html(self, avid: str) -> Optional[str]:
        url = f'https://{self.domain}/videos/{avid.lower()}/'
        return self._fetch_html(url)

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            match = re.search(r'var hlsUrl = ["\']([^"\']+)["\']', html)
            if match:
                info.m3u8 = match.group(1)
            else:
                return None

            # 提取标题
            title_match = re.search(r'<h4 class="title">([^<]+)</h4>', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'<span class="inactive-color">([A-Z]+-\d+)</span>', html)
            if avid_match:
                info.avid = avid_match.group(1)

            return info
        except Exception as e:
            logger.error(f"Jable解析失败: {e}")
            return None

    def get_cover_url(self, html: str) -> Optional[str]:
        try:
            match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            logger.error(f"封面URL提取失败: {e}")
            return None


class DownloaderManager:
    """下载器管理器"""

    def __init__(self):
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        self.downloaders: Dict[str, DownloaderBase] = {}

        # 注册下载器，按权重排序
        source_config = settings.SOURCE_CONFIG

        # MissAV
        missav_config = source_config.get('missav', {})
        if missav_config.get('weight', 0):
            downloader = MissAVDownloader(proxy)
            self.downloaders[downloader.get_downloader_name()] = downloader

        # Jable
        jable_config = source_config.get('jable', {})
        if jable_config.get('weight', 0):
            downloader = JableDownloader(proxy)
            self.downloaders[downloader.get_downloader_name()] = downloader

    def get_sorted_downloaders(self) -> List[Tuple[str, DownloaderBase]]:
        """获取按权重排序的下载器列表"""
        source_config = settings.SOURCE_CONFIG
        sorted_items = []
        for name, downloader in self.downloaders.items():
            weight = source_config.get(name.lower(), {}).get('weight', 0)
            sorted_items.append((name, downloader, weight))
        sorted_items.sort(key=lambda x: x[2], reverse=True)
        return [(name, dl) for name, dl, _ in sorted_items]

    def get_info_from_any_source(self, avid: str) -> Optional[Tuple[AVDownloadInfo, DownloaderBase]]:
        """遍历所有源获取信息"""
        for name, downloader in self.get_sorted_downloaders():
            logger.info(f"尝试从 {name} 获取 {avid}")
            html = downloader.get_html(avid)
            if html:
                info = downloader.parse_html(html)
                if info:
                    info.avid = avid.upper()
                    return info, downloader
        return None

    def download_cover(self, avid: str, downloader: DownloaderBase) -> Optional[str]:
        """下载封面图片"""
        html = downloader.get_html(avid)
        if not html:
            return None

        cover_url = downloader.get_cover_url(html)
        if not cover_url:
            return None

        cover_path = settings.COVER_DIR / f"{avid.upper()}.jpg"
        if downloader._download_file(cover_url, str(cover_path)):
            return str(cover_path)
        return None


class VideoDownloadService:
    """视频下载服务"""

    def __init__(self):
        self.manager = DownloaderManager()
        self.base_dir = Path(__file__).resolve().parent.parent.parent

        # 下载工具路径
        if platform.system() == 'Windows':
            self.download_tool = str(self.base_dir / "tools" / "m3u8-Downloader-Go.exe")
            self.ffmpeg_tool = str(self.base_dir / "tools" / "ffmpeg.exe")
        else:
            self.download_tool = str(self.base_dir / "tools" / "m3u8-Downloader-Go")
            self.ffmpeg_tool = "ffmpeg"

    def download_video(self, avid: str) -> bool:
        """下载视频"""
        avid = avid.upper()
        video_dir = settings.VIDEO_DIR / avid
        video_dir.mkdir(parents=True, exist_ok=True)

        # 获取下载信息
        result = self.manager.get_info_from_any_source(avid)
        if not result:
            logger.error(f"无法获取 {avid} 的下载信息")
            return False

        info, downloader = result

        # 保存元数据
        metadata_path = video_dir / f"{avid}.json"
        info.to_json(str(metadata_path))

        # 下载m3u8视频
        if not self._download_m3u8(info.m3u8, avid, downloader.domain):
            return False

        return True

    def _download_m3u8(self, url: str, avid: str, domain: str) -> bool:
        """下载m3u8视频"""
        video_dir = settings.VIDEO_DIR / avid
        ts_path = video_dir / f"{avid}.ts"
        mp4_path = video_dir / f"{avid}.mp4"

        try:
            proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None

            # 下载命令
            if proxy:
                command = f'"{self.download_tool}" -u {url} -o "{ts_path}" -p {proxy} -H Referer:http://{domain}'
            else:
                command = f'"{self.download_tool}" -u {url} -o "{ts_path}" -H Referer:http://{domain}'

            logger.debug(f"执行命令: {command}")
            if os.system(command) != 0:
                logger.error("m3u8下载失败")
                return False

            # 转换为mp4
            convert_cmd = f'"{self.ffmpeg_tool}" -i "{ts_path}" -c copy -f mp4 "{mp4_path}"'
            logger.debug(f"执行转换: {convert_cmd}")
            if os.system(convert_cmd) != 0:
                logger.error("mp4转换失败")
                return False

            # 删除ts文件
            if ts_path.exists():
                ts_path.unlink()

            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False


# 全局服务实例
downloader_manager = DownloaderManager()
video_download_service = VideoDownloadService()
