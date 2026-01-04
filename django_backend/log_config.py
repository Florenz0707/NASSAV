"""
日志配置 - 用于 uvicorn 日志持久化
"""
import logging
import os
from pathlib import Path

# 获取日志目录
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class RotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    支持按日期轮转并自动清理旧日志的文件处理器
    """

    def __init__(self, filename, when="midnight", interval=1, backupCount=7, **kwargs):
        """
        Args:
            filename: 日志文件路径
            when: 轮转时间单位（midnight表示每天午夜）
            interval: 轮转间隔
            backupCount: 保留的旧日志文件数量
        """
        super().__init__(filename, when, interval, backupCount, **kwargs)


def get_uvicorn_log_config():
    """
    获取 uvicorn 的日志配置字典

    配置说明：
    - access 日志：记录所有 HTTP 请求
    - error 日志：记录错误和警告信息
    - 日志文件：按日期轮转，保留最近 30 天
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(asctime)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(asctime)s - %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "default_file": {
                "formatter": "default",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(LOG_DIR / "uvicorn.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 30,  # 保留 30 天
                "encoding": "utf-8",
            },
            "access_file": {
                "formatter": "access",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(LOG_DIR / "uvicorn_access.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 30,  # 保留 30 天
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["default", "default_file"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default", "default_file"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access", "access_file"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
