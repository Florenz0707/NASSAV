# 批量生成 metadata.json和nfo
import os
import time

from src import data
from src.comm import *
from src.scraper import Sracper


def list_folders(path):
    """返回指定路径下的所有文件夹名称"""
    folders = []
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            folders.append(item)
    return folders


def has_nfo_file(folder_path):
    """检查包括隐藏文件在内的所有.nfo文件"""
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".nfo"):
                return True
    return False


def gen_nfo():
    folders = list_folders(save_path)
    data.batch_insert_bvids(folders, downloaded_path, "MissAV")  # 多点脏数据也无所谓
    for folder in folders:
        if folder == "thumb":
            continue

        # 检查文件夹中是否有.nfo文件
        if has_nfo_file(os.path.join(save_path, folder)):
            print(f"已有nfo: {folder}")
            continue
        # if os.path.exists(f"{folder}.html"):
        #     print(f"已刮削: {folder}")
        #     continue

        print(folder)
        scraper = Sracper(save_path, myproxy)
        scraper.scrape(folder)

        time.sleep(5)


if __name__ == "__main__":
    data.initialize_db(downloaded_path, "MissAV")
    gen_nfo()
