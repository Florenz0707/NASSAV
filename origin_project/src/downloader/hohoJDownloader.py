import re

from .downloaderBase import *


class HohoJDownloader(Downloader):
    def __init__(self, path: str, proxy=None, timeout=15):
        super().__init__(path, proxy, timeout)

    def getDownloaderName(self) -> str:
        return "HohoJ"

    def getHTML(self, avid: str) -> Optional[str]:
        """需要先搜索，获取到详情页url"""
        searchUrl = f"https://hohoj.tv/search?text={avid}"
        logger.debug(searchUrl)
        content = self._fetch_html(searchUrl)
        if not content:
            return None

        first_id = None  # 初始化为默认值
        match = re.search(r"[?&]id=(\d+)", content)
        if match:
            first_id = match.group(1)
            logger.info(first_id)
        if not first_id:
            return None
        videoUrl = f"https://hohoj.tv/embed?id={first_id}"
        logger.debug(videoUrl)
        content = self._fetch_html(
            videoUrl, referer=f"https://hohoj.tv/video?id={first_id}"
        )
        if not content:
            return None
        return content

    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        """需要实现的方法：根据html，解析出元数据，返回AVMetadata"""
        downloadInfo = AVDownloadInfo()

        # 1. 提取m3u8
        match = re.search(r'var videoSrc\s*=\s*"([^"]+)"', html)
        if match:
            downloadInfo.m3u8 = match.group(1)
            logger.info(downloadInfo.m3u8)
        else:
            logger.error("未找到URL")
            return None
        return downloadInfo
