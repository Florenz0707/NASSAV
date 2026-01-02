from typing import Optional

from .comm import *
from .downloader.downloaderBase import Downloader
from .downloader.hohoJDownloader import HohoJDownloader
from .downloader.jableDownloder import JableDownloader
from .downloader.KanAVDownloader import KanAVDownloader
from .downloader.memoDownloader import MemoDownloader
from .downloader.missAVDownloader import MissAVDownloader


class DownloaderMgr:
    downloaders: dict = {}

    def __init__(self):
        # 手动注册handler
        downloader = MissAVDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = JableDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = HohoJDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = MemoDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

        downloader = KanAVDownloader(save_path, myproxy)
        self.downloaders[downloader.getDownloaderName()] = downloader

    def GetDownloader(self, downloaderName: str) -> Optional[Downloader]:
        return self.downloaders[downloaderName]
