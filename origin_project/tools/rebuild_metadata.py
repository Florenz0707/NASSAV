import os
import xml.etree.ElementTree as ET
from pathlib import Path

# 要替换的路径
path = "/vol2/1000/MissAV"
old_path = "/vol2/1000/thumb"
new_path = "/vol2/1000/MissAV/thumb"

# 遍历目录下的所有文件
folders = []
for item in os.listdir(path):
    item_path = os.path.join(path, item)
    if os.path.isdir(item_path):
        folders.append(item_path)

for fold in folders:
    print(fold)
    files = os.listdir(fold)
    for file in files:
        if file.endswith(".nfo"):
            file_path = os.path.join(fold, file)
            try:
                # 解析 XML 文件
                tree = ET.parse(file_path)
                root_elem = tree.getroot()

                modified = False

                # 查找所有 actor 元素
                for actor in root_elem.findall(".//actor"):
                    thumb_elem = actor.find("thumb")
                    if thumb_elem is not None and old_path in thumb_elem.text:
                        # 替换路径
                        thumb_elem.text = thumb_elem.text.replace(old_path, new_path)
                        modified = True

                # 如果有修改，保存文件
                if modified:
                    # 保留原始 XML 声明和格式
                    with open(file_path, "r", encoding="utf-8") as f:
                        original_content = f.read()

                    # 使用 ElementTree 生成修改后的内容
                    tree.write(file_path, encoding="utf-8", xml_declaration=True)

                    # 恢复原始格式（ElementTree 会改变格式）
                    with open(file_path, "r+", encoding="utf-8") as f:
                        modified_content = f.read()
                        final_content = original_content.replace(old_path, new_path)
                        f.seek(0)
                        f.write(final_content)
                        f.truncate()

                    print(f"已修改: {file_path}")

            except ET.ParseError as e:
                print(f"解析错误 {file_path}: {e}")
            except Exception as e:
                print(f"处理 {file_path} 时出错: {e}")
