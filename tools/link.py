#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def create_symlinks(source_dir, target_dir):
    """为 source_dir 下的所有 mp4/ts/nfo 文件创建软链接到 target_dir"""
    source_dir = Path(source_dir).resolve()
    target_dir = Path(target_dir).resolve()

    # 确保目标目录存在
    target_dir.mkdir(parents=True, exist_ok=True)

    # 支持的扩展名
    extensions = ('.mp4', '.ts', '.nfo', '.jpg')

    # 遍历源目录
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith(extensions):
                src_path = Path(root) / file
                dst_path = target_dir / file

                # 如果链接已存在则跳过
                if dst_path.exists():
                    print(f"跳过已存在的链接: {dst_path}")
                    continue

                try:
                    # 创建相对路径的软链接
                    rel_src = os.path.relpath(src_path, dst_path.parent)
                    dst_path.symlink_to(rel_src)
                    print(f"创建链接: {dst_path} -> {src_path}")
                except OSError as e:
                    print(f"错误: 无法创建链接 {dst_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"用法: {sys.argv[0]} <源目录> <目标目录>")
        sys.exit(1)

    source_dir = sys.argv[1]
    target_dir = sys.argv[2]

    create_symlinks(source_dir, target_dir)
