#!/bin/bash
# WebSocket 测试脚本
# 需要安装: npm install -g wscat 或 pip install websocket-client
# 用法: ./test_websocket.sh

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
WS_URL="${WS_URL:-ws://localhost:8000/ws/tasks/}"
TIMEOUT=30

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# 检查 WebSocket 工具
check_tools() {
    if command -v wscat &> /dev/null; then
        return 0
    elif command -v python3 &> /dev/null; then
        return 0
    else
        echo -e "${RED}错误: 未找到 WebSocket 测试工具${NC}"
        echo "请安装以下工具之一:"
        echo "  - wscat: npm install -g wscat"
        echo "  - Python websocket-client: pip install websocket-client"
        exit 1
    fi
}

# 使用 wscat 测试
test_with_wscat() {
    print_header "使用 wscat 测试 WebSocket"
    echo -e "${YELLOW}连接到: ${NC}$WS_URL"
    echo -e "${YELLOW}超时时间: ${NC}${TIMEOUT}秒"
    echo ""
    echo -e "${CYAN}提示: 按 Ctrl+C 退出${NC}"
    echo ""

    wscat -c "$WS_URL"
}

# 使用 Python 测试
test_with_python() {
    print_header "使用 Python 测试 WebSocket"
    echo -e "${YELLOW}连接到: ${NC}$WS_URL"
    echo -e "${YELLOW}监听时间: ${NC}${TIMEOUT}秒"
    echo ""

    python3 - <<EOF
import json
import sys
import time

try:
    import websocket
except ImportError:
    print("\033[0;31m错误: 未安装 websocket-client\033[0m")
    print("请运行: pip install websocket-client")
    sys.exit(1)

def on_message(ws, message):
    try:
        data = json.loads(message)
        msg_type = data.get('type', 'unknown')

        # 格式化输出
        if msg_type == 'queue_status':
            print("\033[0;36m[队列状态]\033[0m")
            queue_data = data.get('data', {})
            print(f"  活跃任务: {queue_data.get('active_count', 0)}")
            print(f"  等待任务: {queue_data.get('pending_count', 0)}")

            # 显示活跃任务详情
            for task in queue_data.get('active_tasks', []):
                avid = task.get('avid')
                task_type = task.get('task_type', 'download')
                progress = task.get('progress', {})
                percent = progress.get('percent', 0)
                speed = progress.get('speed', 'N/A')
                print(f"    - {avid} [{task_type}]: {percent:.1f}% @ {speed}")

        elif msg_type == 'task_started':
            task_data = data.get('data', {})
            avid = task_data.get('avid')
            print(f"\033[0;32m[任务开始]\033[0m {avid}")

        elif msg_type == 'progress_update':
            task_data = data.get('data', {})
            avid = task_data.get('avid')
            progress = task_data.get('progress', {})
            percent = progress.get('percent', 0)
            speed = progress.get('speed', 'N/A')
            print(f"\033[1;33m[进度更新]\033[0m {avid}: {percent:.1f}% @ {speed}")

        elif msg_type == 'task_completed':
            task_data = data.get('data', {})
            avid = task_data.get('avid')
            print(f"\033[0;32m[任务完成]\033[0m {avid}")

        elif msg_type == 'task_failed':
            task_data = data.get('data', {})
            avid = task_data.get('avid')
            message = task_data.get('message', '')
            print(f"\033[0;31m[任务失败]\033[0m {avid}: {message}")

        else:
            print(f"[{msg_type}] {json.dumps(data, ensure_ascii=False)}")

        print()  # 空行

    except json.JSONDecodeError:
        print(f"接收到非 JSON 消息: {message}")

def on_error(ws, error):
    print(f"\033[0;31m错误: {error}\033[0m")

def on_close(ws, close_status_code, close_msg):
    print("\033[1;33m连接已关闭\033[0m")

def on_open(ws):
    print("\033[0;32m✓ WebSocket 连接已建立\033[0m\n")

# 创建 WebSocket 连接
ws_url = "$WS_URL"
print(f"正在连接到 {ws_url}...")

ws = websocket.WebSocketApp(
    ws_url,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

# 运行指定时间后关闭
import threading
def close_after_timeout():
    time.sleep($TIMEOUT)
    print("\n\033[1;33m超时，关闭连接\033[0m")
    ws.close()

timer = threading.Thread(target=close_after_timeout)
timer.daemon = True
timer.start()

try:
    ws.run_forever()
except KeyboardInterrupt:
    print("\n\033[1;33m用户中断\033[0m")
    ws.close()
EOF
}

# 主程序
main() {
    print_header "WebSocket 测试脚本"

    check_tools

    # 优先使用 Python（输出更友好）
    if command -v python3 &> /dev/null && python3 -c "import websocket" 2>/dev/null; then
        test_with_python
    elif command -v wscat &> /dev/null; then
        test_with_wscat
    fi
}

main
