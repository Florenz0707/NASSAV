#!/bin/bash
# 测试模拟下载任务的批处理脚本
# 用法:
#   ./test_mock_download.sh                    # 使用默认 AVID 列表
#   ./test_mock_download.sh AVID1 AVID2 ...    # 使用自定义 AVID 列表
#   ./test_mock_download.sh --status           # 仅查询队列状态
#   ./test_mock_download.sh --duration 60      # 指定模拟时长（秒）

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# API 基础地址
BASE_URL="${BASE_URL:-http://localhost:8000}"
API_ENDPOINT="$BASE_URL/nassav/api/downloads/mock"
STATUS_ENDPOINT="$BASE_URL/nassav/api/tasks/queue/status"

# 默认 AVID 列表
DEFAULT_AVIDS=(
    "SSIS-465"
    "ABF-139"
    "DASS-002"
    "IPX-416"
    "SONE-247"
)

# 模拟下载持续时间（秒）
DURATION=30

# 解析命令行参数
AVIDS=()
STATUS_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --status)
            STATUS_ONLY=true
            shift
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法: $0 [选项] [AVID...]"
            echo ""
            echo "选项:"
            echo "  --status           仅查询任务队列状态"
            echo "  --duration SECONDS 指定模拟下载持续时间（默认 30 秒）"
            echo "  --help, -h         显示帮助信息"
            echo ""
            echo "示例:"
            echo "  $0                              # 使用默认 AVID 列表"
            echo "  $0 SSIS-465 ABF-139            # 指定 AVID"
            echo "  $0 --duration 60 SSIS-465      # 60 秒模拟下载"
            echo "  $0 --status                     # 查询队列状态"
            exit 0
            ;;
        *)
            AVIDS+=("$1")
            shift
            ;;
    esac
done

# 如果没有指定 AVID，使用默认列表
if [ ${#AVIDS[@]} -eq 0 ] && [ "$STATUS_ONLY" = false ]; then
    AVIDS=("${DEFAULT_AVIDS[@]}")
fi

# 打印分隔线
print_separator() {
    echo -e "${BLUE}========================================${NC}"
}

# 打印标题
print_header() {
    print_separator
    echo -e "${BLUE}$1${NC}"
    print_separator
}

# 查询队列状态
check_status() {
    echo -e "${YELLOW}📊 查询任务队列状态...${NC}"
    response=$(curl -s "$STATUS_ENDPOINT")

    # 美化 JSON 输出
    if command -v jq &> /dev/null; then
        echo "$response" | jq .
    else
        echo "$response"
    fi
}

# 提交模拟下载任务
submit_mock_task() {
    local avid=$1
    echo -e "${YELLOW}🚀 提交模拟下载任务: ${NC}${avid}"

    # 构建请求体
    local request_body="{\"duration\": $DURATION}"

    # 发送请求
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$request_body" \
        "$API_ENDPOINT/$avid")

    # 分离响应体和状态码
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    # 根据状态码输出结果
    case $http_code in
        202)
            echo -e "${GREEN}✓ 成功${NC}"
            if command -v jq &> /dev/null; then
                task_id=$(echo "$body" | jq -r '.data.task_id')
                echo -e "  Task ID: ${task_id}"
                echo -e "  持续时间: ${DURATION}秒"
            fi
            ;;
        409)
            echo -e "${YELLOW}⚠ 任务已存在${NC}"
            ;;
        404)
            echo -e "${RED}✗ 资源不存在${NC}"
            ;;
        403)
            echo -e "${RED}✗ DEBUG 模式未启用${NC}"
            echo -e "  请在 .env 文件中设置 DEBUG=True"
            ;;
        *)
            echo -e "${RED}✗ 失败 (HTTP $http_code)${NC}"
            if command -v jq &> /dev/null; then
                echo "$body" | jq .
            else
                echo "$body"
            fi
            ;;
    esac

    echo ""
}

# 主程序
main() {
    print_header "模拟下载任务测试脚本"

    # 仅查询状态
    if [ "$STATUS_ONLY" = true ]; then
        check_status
        exit 0
    fi

    echo -e "${BLUE}API 地址:${NC} $BASE_URL"
    echo -e "${BLUE}模拟时长:${NC} ${DURATION}秒"
    echo -e "${BLUE}任务数量:${NC} ${#AVIDS[@]}"
    echo ""

    # 提交任务
    print_separator
    for avid in "${AVIDS[@]}"; do
        submit_mock_task "$avid"
        sleep 0.5  # 避免请求过快
    done

    # 等待一段时间后查询状态
    echo -e "${YELLOW}⏳ 等待 2 秒后查询任务状态...${NC}"
    sleep 2
    echo ""

    check_status

    echo ""
    print_separator
    echo -e "${GREEN}✓ 批处理测试完成${NC}"
    echo -e "${YELLOW}💡 提示:${NC}"
    echo "  - 使用 WebSocket 实时监控进度"
    echo "  - 运行 '$0 --status' 查询队列状态"
    echo "  - 查看 Celery Worker 日志了解详情"
    print_separator
}

# 执行主程序
main
