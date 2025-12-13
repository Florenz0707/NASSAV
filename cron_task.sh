#!/bin/bash

FILE="db/download_queue.txt"

# 1. 检查文件是否存在且非空
if [ ! -s "$FILE" ]; then
    echo "Error: File is empty or does not exist: $FILE"
    exit 1
fi

# 2. 获取最后一行（跳过空行）
LAST_LINE=$(tail -n 1 "$FILE" | sed '/^$/d')

# 如果最后一行是空，则获取倒数第二行
if [ -z "$LAST_LINE" ]; then
    LAST_LINE=$(tail -n 2 "$FILE" | head -n 1 | sed '/^$/d')
fi

# 3. 去除首尾空格和换行符
TRIMMED_LINE=$(echo "$LAST_LINE" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
echo $TRIMMED_LINE

# 4. 检查是否有效内容
if [ -n "$TRIMMED_LINE" ]; then
    # 5. 删除该行（原地修改文件）
    sed -i "/^[[:space:]]*${TRIMMED_LINE}[[:space:]]*$/d" "$FILE"

    # 6. 调用 Python 脚本并传递参数
    python3 main.py "$TRIMMED_LINE"
else
    echo "Error: No valid line found in $FILE"
    exit 1
fi
