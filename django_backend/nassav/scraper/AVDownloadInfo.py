import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from loguru import logger


@dataclass
class AVDownloadInfo:
    """下载信息数据类"""
    m3u8: str = ""
    title: str = ""
    avid: str = ""
    source: str = ""
    # 扩展元数据字段
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
            with path.open('w', encoding='utf-8') as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=indent)
            return True
        except (IOError, TypeError) as e:
            logger.error(f"JSON序列化失败: {str(e)}")
            return False

    def update_from_scrapper(self, scrapped_data: dict) -> None:
        """从刮削器数据更新元数据"""
        if scrapped_data.get('release_date'):
            self.release_date = scrapped_data['release_date']
        if scrapped_data.get('duration'):
            self.duration = scrapped_data['duration']
        if scrapped_data.get('director'):
            self.director = scrapped_data['director']
        if scrapped_data.get('studio'):
            self.studio = scrapped_data['studio']
        if scrapped_data.get('label'):
            self.label = scrapped_data['label']
        if scrapped_data.get('series'):
            self.series = scrapped_data['series']
        if scrapped_data.get('genres'):
            self.genres = scrapped_data['genres']
        if scrapped_data.get('actors'):
            self.actors = scrapped_data['actors']
        # 如果刮削器有更好的标题，可以选择更新
        if scrapped_data.get('title') and not self.title:
            self.title = scrapped_data['title']
