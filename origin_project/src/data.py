import sqlite3
from typing import List

from .comm import *


def initialize_db(db_path: str, table_name: str):
    logger.debug(f"db_path: {db_path}, table_name: {table_name}")

    """初始化数据库，创建表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建表（如果不存在）
    cursor.execute(
        f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        bvid TEXT PRIMARY KEY
    )
    """
    )

    conn.commit()
    conn.close()


def batch_insert_bvids(bvid_list: list[str], db_path: str, table_name: str):
    """批量插入BVID，自动忽略已存在的"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 使用 INSERT OR IGNORE 避免重复插入
        cursor.executemany(
            f"INSERT OR IGNORE INTO {table_name} (bvid) VALUES (?)",
            [(bvid,) for bvid in bvid_list],
        )
        conn.commit()
        logger.info(f"成功插入 {cursor.rowcount}")
    except sqlite3.Error as e:
        logger.error(f"插入BVID时出错: {e}")
        conn.rollback()
    finally:
        conn.close()


def find_in_db(bvid: str, db_path: str, table_name: str) -> bool:
    try:
        # 连接到 SQLite 数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 执行查询
        query = f"SELECT 1 FROM {table_name} WHERE bvid = ? LIMIT 1"
        cursor.execute(query, (bvid,))
        result = cursor.fetchone()
        # 关闭连接
        cursor.close()
        conn.close()

        return result is not None

    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        return False
    except Exception as e:
        print(f"发生错误: {e}")
        return False
