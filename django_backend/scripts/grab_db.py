import sqlite3

if __name__ == "__main__":
    # 连接到 SQLite 数据库
    conn = sqlite3.connect('../db.sqlite3')
    cursor = conn.cursor()

    # 执行查询
    cursor.execute("SELECT title, source_title, translated_title FROM nassav_avresource")
    rows = cursor.fetchall()

    # 输出结果
    for row in rows:
        print(f"Title: {row[0]}, Source Title: {row[1]}, Translated Title: {row[2]}")

    # 关闭连接
    cursor.close()
    conn.close()
