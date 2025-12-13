from .downloaderBase import *
import re
from urllib.parse import unquote

def decode_url(encoded_url):
    try:
        return unquote(encoded_url)
    except Exception as e:
        print(f"解码失败: {e}")
        return None

class MemoDownloader(Downloader):
    def getDownloaderName(self) -> str:
        return "Memo"

    def getHTML(self, avid: str) -> Optional[str]:
        '''需要先搜索，获取到详情页url'''
        url = f"https://{self.domain}/hls/get_video_info.php?id={avid}&sig=NTg1NTczNg&sts=7264825"
        logger.debug(url)
        content = self._fetch_html(url, referer=f"https://{self.domain}")
        if not content: return None
        return content

    def parseHTML(self, html: str) -> Optional[AVDownloadInfo]:
        '''需要实现的方法：根据html，解析出元数据，返回AVMetadata'''
        logger.debug(html)
        missavMetadata = AVDownloadInfo()
        pattern = r'"url":"(https?%3A%2F%2F[^"]+)"'
        match = re.search(pattern, html)
        if match:
            encoded_url = match.group(1)
            url = decode_url(encoded_url)
            logger.info(url)
            if url is None:
                return None
            missavMetadata.m3u8 = url
            return missavMetadata
        return None
