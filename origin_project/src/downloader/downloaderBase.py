# doc: 定义下载类的基础操作
from abc import ABC, abstractmethod
import json
from loguru import logger
import os
from dataclasses import dataclass, asdict, field
from typing import Optional, Tuple
from pathlib import Path
from ..comm import *
from curl_cffi import requests

# 下载信息，只保留最基础的信息。只需要填写avid，其他字段用于调试，选填
@dataclass
class AVDownloadInfo:
    m3u8: str = ""
    title: str = ""
    avid: str = ""

    def __str__(self):
        return (
            f"=== 元数据详情 ===\n"
            f"番号: {self.avid or '未知'}\n"
            f"标题: {self.title or '未知'}\n"
            f"M3U8: {self.m3u8 or '无'}"
        )

    def to_json(self, file_path: str, indent: int = 2) -> bool:
        try:
            path = Path(file_path) if isinstance(file_path, str) else file_path
            path.parent.mkdir(parents=True, exist_ok=True)

            with path.open('w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=indent)
            return True
        except (IOError, TypeError) as e:
            logger.error(f"JSON序列化失败: {str(e)}")
            return False

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}

class Downloader(ABC):
    """
    使用方式：
    1. downloadInfo生成元数据，并序列化到download_info.json
    2. downloadM3u8下载视频并转成mp4格式
    3. downloadIMG下载封面和演员头像
    4. genNFO生成nfo文件
    """
    def __init__(self, path: str, proxy = None, timeout = 15):
        """
        :path: 配置的路径，如/vol2/user/missav
        :avid: 车牌号
        """
        self.path = path
        self.proxy = proxy
        self.proxies = {
            'http': proxy,
            'https': proxy
        } if proxy else None
        self.timeout = timeout

    def setDomain(self, domain: str) -> bool:
        if domain:
            self.domain = domain
            return True
        return False

    @abstractmethod
    def getDownloaderName(self) -> str:
        pass

    @abstractmethod
    def getHTML(self, avid: str) -> Optional[str]:
        '''需要实现的方法：根据avid，构造url并请求，获取html, 返回字符串'''
        pass

    @abstractmethod
    def parseHTML(self, html: str, avid: str) -> Optional[AVDownloadInfo]:
        '''
        需要实现的方法：根据html，解析出元数据，返回AVDownloadInfo
        注意：实现新的downloader，只需要获取到m3u8就行了(也可以多匹配点方便调试)，元数据统一使用MissAV
        '''
        pass

    def downloadInfo(self, avid: str) -> Optional[AVDownloadInfo]:
        '''将元数据download_info.json序列化到到对应位置，同时返回AVDownloadInfo'''
        # 获取html
        avid = avid.upper()
        print(os.path.join(self.path, avid))
        os.makedirs(os.path.join(self.path, avid), exist_ok=True)
        html = self.getHTML(avid)
        if not html:
            logger.error("获取html失败")
            return None
        with open(os.path.join(self.path, avid, avid+".html"), "w+", encoding='utf-8') as f:
            f.write(html)

        # 从html中解析元数据，返回MissAVInfo结构体
        info = self.parseHTML(html)
        if info is None:
            logger.error("解析元数据失败")
            return None

        info.avid = info.avid.upper() # 强制大写
        info.to_json(os.path.join(self.path, avid, "download_info.json"))
        logger.info("已保存到 download_info.json")

        return info


    def downloadM3u8(self, url: str, avid: str) -> bool:
        """m3u8视频下载"""
        os.makedirs(os.path.dirname(os.path.join(self.path, avid)), exist_ok=True)
        try:
            if isNeedVideoProxy and self.proxy:
                logger.info("使用代理")
                command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -p {self.proxy} -H Referer:http://{self.domain}"
            else:
                logger.info("不使用代理")
                command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -H Referer:http://{self.domain}"
            logger.debug(command)
            if os.system(command) != 0:
                # 难顶。。。使用代理下载失败，尝试不用代理；不用代理下载失败，尝试使用代理
                if not isNeedVideoProxy and self.proxy:
                    logger.info("尝试使用代理")
                    command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -p {self.proxy} -H Referer:http://{self.domain}"
                else:
                    logger.info("尝试不使用代理")
                    command = f"{download_tool} -u {url} -o {os.path.join(self.path, avid, avid+'.ts')} -H Referer:http://{self.domain}"
                logger.debug(f"retry {command}")
                if os.system(command) != 0:
                    return False

            # 转mp4
            convert = f"{ffmpeg_tool} -i {os.path.join(self.path, avid, avid+'.ts')} -c copy -f mp4 {os.path.join(self.path, avid, avid+'.mp4')}"
            logger.debug(convert)
            if os.system(convert) != 0:
                return False
            if os.system(f"rm {os.path.join(self.path, avid, avid+'.ts')}") != 0:
                return False
            return True
        except:
            return False

    def _fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        logger.debug(f"fetch url: {url}")
        try:
            newHeader = headers
            if referer:
                newHeader["Referer"] = referer
            response = requests.get(
                url,
                proxies=self.proxies,
                headers=newHeader,
                timeout=self.timeout,
                impersonate="chrome110",  # 可选：chrome, chrome110, edge99, safari15_5
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {str(e)}")
            return None
