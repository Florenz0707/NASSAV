#!/usr/bin/env python3
import os
from pathlib import Path

def rename_jpg_files_with_prefix(root_dir):
    """为所有jpg文件添加所在文件夹名前缀"""
    root_path = Path(root_dir).resolve()

    # 遍历目录
    for folder in root_path.iterdir():
        if folder == "thumb":
            continue
        if folder.is_dir():
            prefix = folder.name  # 获取文件夹名作为前缀
            # 遍历文件夹内的文件
            for file in folder.iterdir():
                if file.suffix.lower() == '.jpg':
                    # 构造新文件名，符合jellyfin命名规则
                    new_name = f"{prefix}-{file.name}"
                    new_path = file.with_name(new_name)

                    # 重命名文件
                    try:
                        file.rename(new_path)
                        print(f"重命名: {file} -> {new_path}")
                    except Exception as e:
                        print(f"错误: 无法重命名 {file}: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(f"用法: {sys.argv[0]} <目录路径>")
        sys.exit(1)

    target_dir = sys.argv[1]
    rename_jpg_files_with_prefix(target_dir)
