import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from loguru import logger


@dataclass
class AVDownloadInfo:
    """下载信息数据类

    职责划分：
    - Source 提供：m3u8、source_title（备用标题）
    - Scraper 提供：title（规范标题）、其他元数据
    """

    # Source 提供的核心信息
    m3u8: str = ""
    source_title: str = ""  # Source 获取的标题（备用）
    avid: str = ""
    source: str = ""  # 来源名称（如 Jable、MissAV）

    # Scraper 补充的扩展元数据
    title: str = ""  # Scraper 获取的规范标题（通常为日语）
    release_date: str = ""  # 发行日期
    duration: str = ""  # 时长
    director: str = ""  # 导演
    studio: str = ""  # 制作商
    label: str = ""  # 发行商
    series: str = ""  # 系列
    genres: List[str] = None  # 类别
    actors: List[str] = None  # 演员

    def __post_init__(self):
        if self.genres is None:
            self.genres = []
        if self.actors is None:
            self.actors = []

    def to_json(self, file_path: str, indent: int = 2) -> bool:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=indent)
            return True
        except (IOError, TypeError) as e:
            logger.error(f"JSON序列化失败: {str(e)}")
            return False

    def update_from_scraper(self, scraped_data: dict) -> None:
        """从刮削器数据更新元数据

        Args:
            scraped_data: 从 Scraper（如 JavBus）获取的元数据字典
        """
        # 更新 Scraper 提供的规范标题
        if scraped_data.get("title"):
            self.title = scraped_data["title"]

        # 更新所有扩展元数据字段
        if scraped_data.get("release_date"):
            self.release_date = scraped_data["release_date"]
        if scraped_data.get("duration"):
            self.duration = scraped_data["duration"]
        if scraped_data.get("director"):
            self.director = scraped_data["director"]
        if scraped_data.get("studio"):
            self.studio = scraped_data["studio"]
        if scraped_data.get("label"):
            self.label = scraped_data["label"]
        if scraped_data.get("series"):
            self.series = scraped_data["series"]
        if scraped_data.get("genres"):
            self.genres = scraped_data["genres"]
        if scraped_data.get("actors"):
            self.actors = scraped_data["actors"]
