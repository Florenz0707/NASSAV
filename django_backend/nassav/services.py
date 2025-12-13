"""
服务层：封装下载器和刮削器逻辑
"""
import json
import os
import platform
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from curl_cffi import requests
from django.conf import settings
from loguru import logger

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
                  "Safari/537.36",
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

    def get_cover_url(self, html: str) -> str:
        raise NotImplementedError

    def fetch_html(self, url: str, referer: str = "") -> Optional[str]:
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

    def download_file(self, url: str, save_path: str, referer: str = "") -> bool:
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
            f'https://{self.domain}/dm76/cn/{avid_lower}',
            f'https://{self.domain}/dm52/cn/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
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
            match = re.search(r"m3u8\|([a-f0-9|]+)\|com\|surrit\|https\|video", html)
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
        return self.fetch_html(url)

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


class HohojDownloader(DownloaderBase):
    """Hohoj下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('hohoj', {})
        self.domain = source_config.get('domain', 'hohoj.tv')

    def get_downloader_name(self) -> str:
        return "Hohoj"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_lower}-chinese-subtitle',
            f'https://{self.domain}/video/{avid_lower}-uncensored-leak',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8 - 尝试多种模式
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src["\']?\s*[:=]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_patterns = [
                r'<title>([^<]+)</title>',
                r'<h1[^>]*>([^<]+)</h1>',
                r'<meta property="og:title" content="([^"]+)"',
            ]
            for pattern in title_patterns:
                match = re.search(pattern, html)
                if match:
                    info.title = match.group(1).strip()
                    break

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Hohoj解析失败: {e}")
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


class MemoDownloader(DownloaderBase):
    """MemoJav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('memo', {})
        self.domain = source_config.get('domain', 'memojav.com')

    def get_downloader_name(self) -> str:
        return "Memo"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/cn/{avid_lower}',
            f'https://{self.domain}/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Memo解析失败: {e}")
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


class KanavDownloader(DownloaderBase):
    """Kanav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('kanav', {})
        self.domain = source_config.get('domain', 'kanav.info')

    def get_downloader_name(self) -> str:
        return "Kanav"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/watch/{avid_lower}',
            f'https://{self.domain}/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Kanav解析失败: {e}")
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


class AvtodayDownloader(DownloaderBase):
    """Avtoday下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('avtoday', {})
        self.domain = source_config.get('domain', 'avtoday.io')

    def get_downloader_name(self) -> str:
        return "Avtoday"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/watch/{avid_lower}',
            f'https://{self.domain}/{avid_lower}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Avtoday解析失败: {e}")
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


class NetflavDownloader(DownloaderBase):
    """Netflav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('netflav', {})
        self.domain = source_config.get('domain', 'netflav.com')

    def get_downloader_name(self) -> str:
        return "Netflav"

    def get_html(self, avid: str) -> Optional[str]:
        # Netflav 使用搜索页面找到视频
        avid_lower = avid.lower()
        avid_upper = avid.upper()

        # 尝试直接访问视频页面
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_upper}',
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content

        # 尝试搜索
        search_url = f'https://{self.domain}/search?keyword={avid_upper}'
        search_html = self.fetch_html(search_url)
        if search_html:
            # 从搜索结果中提取视频链接
            video_match = re.search(rf'href="([^"]+{avid_lower}[^"]*)"', search_html, re.IGNORECASE)
            if video_match:
                video_url = video_match.group(1)
                if not video_url.startswith('http'):
                    video_url = f'https://{self.domain}{video_url}'
                return self.fetch_html(video_url)

        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # Netflav 通常使用 iframe 或 ajax 加载视频
            # 尝试提取 m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'm3u8["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                # 尝试提取 iframe src 并获取其中的 m3u8
                iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"', html)
                if iframe_match:
                    iframe_url = iframe_match.group(1)
                    if not iframe_url.startswith('http'):
                        iframe_url = f'https:{iframe_url}' if iframe_url.startswith('//') else f'https://{self.domain}{iframe_url}'
                    iframe_html = self.fetch_html(iframe_url)
                    if iframe_html:
                        for pattern in m3u8_patterns:
                            match = re.search(pattern, iframe_html)
                            if match:
                                info.m3u8 = match.group(1)
                                break

            if not info.m3u8:
                return None

            # 提取标题
            title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            if title_match:
                info.title = title_match.group(1).strip()

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Netflav解析失败: {e}")
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


class KissavDownloader(DownloaderBase):
    """Kissav下载器"""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 15):
        super().__init__(proxy, timeout)
        source_config = settings.SOURCE_CONFIG.get('kissav', {})
        self.domain = source_config.get('domain', 'f15.bzraizy.cc')

    def get_downloader_name(self) -> str:
        return "Kissav"

    def get_html(self, avid: str) -> Optional[str]:
        avid_lower = avid.lower()
        avid_upper = avid.upper()
        urls = [
            f'https://{self.domain}/video/{avid_lower}',
            f'https://{self.domain}/video/{avid_upper}',
            f'https://{self.domain}/{avid_lower}',
            f'https://{self.domain}/play/{avid_lower}',
            f"https://{self.domain}/videos/index/id/{avid_lower}",
        ]
        for url in urls:
            content = self.fetch_html(url)
            if content:
                return content
        return None

    def parse_html(self, html: str) -> Optional[AVDownloadInfo]:
        info = AVDownloadInfo()
        info.source = self.get_downloader_name()

        try:
            # 提取m3u8
            m3u8_patterns = [
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            for pattern in m3u8_patterns:
                match = re.search(pattern, html)
                if match:
                    info.m3u8 = match.group(1)
                    break

            if not info.m3u8:
                return None

            # 提取标题
            title_patterns = [
                r'<meta property="og:title" content="([^"]+)"',
                r'<title>([^<]+)</title>',
                r'<h1[^>]*>([^<]+)</h1>',
            ]
            for pattern in title_patterns:
                match = re.search(pattern, html)
                if match:
                    info.title = match.group(1).strip()
                    break

            # 提取avid
            avid_match = re.search(r'([A-Z]+-\d+)', info.title, re.IGNORECASE)
            if avid_match:
                info.avid = avid_match.group(1).upper()

            return info
        except Exception as e:
            logger.error(f"Kissav解析失败: {e}")
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

    # 下载器类映射
    DOWNLOADER_CLASSES = {
        'missav': MissAVDownloader,
        'jable': JableDownloader,
        'hohoj': HohojDownloader,
        'memo': MemoDownloader,
        'kanav': KanavDownloader,
        'avtoday': AvtodayDownloader,
        'netflav': NetflavDownloader,
        'kissav': KissavDownloader,
    }

    def __init__(self):
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        self.downloaders: Dict[str, DownloaderBase] = {}

        # 注册下载器，根据配置中的权重
        source_config = settings.SOURCE_CONFIG

        for source_name, downloader_class in self.DOWNLOADER_CLASSES.items():
            config = source_config.get(source_name, {})
            weight = config.get('weight')
            # 只有配置了有效权重的源才会被注册
            if weight:
                downloader = downloader_class(proxy)
                self.downloaders[downloader.get_downloader_name()] = downloader
                logger.debug(f"注册下载器: {downloader.get_downloader_name()}, 权重: {weight}")

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
        if downloader.download_file(cover_url, str(cover_path)):
            return str(cover_path)
        return None


class VideoDownloadService:
    """视频下载服务"""

    def __init__(self, downloader: DownloaderManager):
        self.manager = downloader

        # 下载工具路径 - 改为使用 settings 中的 RESOURCE_DIR
        tools_dir = settings.BASE_DIR / "tools"
        if platform.system() == 'Windows':
            self.download_tool = str(tools_dir / "m3u8-Downloader-Go.exe")
            self.ffmpeg_tool = str(tools_dir / "ffmpeg.exe")
        else:
            self.download_tool = str(tools_dir / "m3u8-Downloader-Go")
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
video_download_service = VideoDownloadService(downloader_manager)
