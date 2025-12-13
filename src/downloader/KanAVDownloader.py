from .downloaderBase import *
import re
import base64
from urllib.parse import unquote


class KanAVDownloader(Downloader):
    def __init__(self, path: str, proxy = None, timeout = 15):
        super().__init__(path, proxy, timeout)

    def getDownloaderName(self) -> str:
        return "KanAV"

    def getHTML(self, avid: str) -> Optional[str]:
        '''需要先搜索，获取到详情页url'''
        searchUrl = f"https://kanav.info/index.php/vod/search.html?wd={avid}&by=time_add"
        logger.debug(searchUrl)
        content = self._fetch_html(searchUrl)
        if not content: return None

        pageUrl = None  # 初始化为默认值
        match = re.search(r'href="(/index\.php/vod/play[^"]*\.html)"', content)
        if match:
            pageUrl = f"https://{self.domain}{match.group(1)}"
            logger.info(pageUrl)
        if not pageUrl:
            return None

        content = self._fetch_html(pageUrl)
        if content: return content
        return None


    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        '''需要实现的方法：根据html，解析出元数据，返回AVMetadata'''
        downloadInfo = AVDownloadInfo()

        match = re.search(r'"url":"([A-Za-z0-9]*)"', html)
        if match:
            encoded_url = match.group(1)
            logger.debug("URL before decode:", encoded_url)
            final_url = unquote(base64.b64decode(encoded_url).decode('utf-8'))
            logger.debug("URL after decode:", final_url)
            downloadInfo.m3u8 = final_url
            logger.info(downloadInfo.m3u8)
        else:
            logger.error("未找到URL")
            return None
        return downloadInfo
