import re

from .downloaderBase import *


class JableDownloader(Downloader):
    def getDownloaderName(self) -> str:
        return "Jable"

    def getHTML(self, avid: str) -> Optional[str]:
        """需要实现的方法：根据avid，构造url并请求，获取html, 返回字符串"""
        url = f"https://{self.domain}/videos/{avid}/".lower()
        logger.debug(url)
        content = self._fetch_html(url)
        if content:
            return content
        return None

    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        """需要实现的方法：根据html，解析出元数据，返回AVMetadata"""
        missavMetadata = AVDownloadInfo()

        # 1. 提取m3u8
        pattern = r"var hlsUrl = '(https?://[^']+)'"
        match = re.search(pattern, html)
        if match:
            missavMetadata.m3u8 = match.group(1)
            logger.info(missavMetadata.m3u8)
        else:
            logger.error("未找到 m3u8")
            return None

        # 2. 提取基本信息
        if not self._extract_metadata(html, missavMetadata):
            return None

        return missavMetadata

    @staticmethod
    def _extract_metadata(html: str, metadata: AVDownloadInfo) -> bool:
        try:
            # 提取OG标签
            og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)

            if og_title:  # 处理标题和番号
                title_content = og_title.group(1)
                if code_match := re.search(r"([A-Z]+(?:-[A-Z]+)*-\d+)", title_content):
                    metadata.avid = code_match.group(1)
                    metadata.title = title_content.replace(metadata.avid, "").strip()
                else:
                    metadata.title = title_content.strip()

        except Exception as e:
            logger.error(f"元数据解析异常: {str(e)}")
            return False

        return True
