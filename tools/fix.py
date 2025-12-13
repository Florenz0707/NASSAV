#!/usr/bin/env python3
import os
import re
from pathlib import Path

def replace_thumb_path(root_dir):
    for nfo_file in Path(root_dir).rglob('*.nfo'):
        content = nfo_file.read_text(encoding='utf-8')
        new_content = re.sub(
            r'(<thumb>.*)/Relax/(.*</thumb>)',
            r'\1/MissAV/\2',
            content
        )
        if new_content != content:
            nfo_file.write_text(new_content, encoding='utf-8')
            print(f"已修改: {nfo_file}")

if __name__ == "__main__":
    replace_thumb_path('/vol2/1000/MissAV')
