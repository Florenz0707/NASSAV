#!/bin/bash
# API 综合测试脚本
# 用法: ./test_api.sh [--verbose]

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 配置
BASE_URL="${BASE_URL:-http://localhost:8000}"
VERBOSE=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --verbose, -v  显示详细输出"
            echo "  --help, -h     显示帮助信息"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# 测试计数器
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 打印标题
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# 测试函数
test_api() {
    local name=$1
    local method=$2
    local endpoint=$3
    local expected_code=$4
    local data=${5:-}

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    echo -ne "${CYAN}测试 #${TOTAL_TESTS}: ${name}${NC} ... "

    # 构建 curl 命令
    if [ -n "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint" 2>&1)
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            "$BASE_URL$endpoint" 2>&1)
    fi

    # 检查是否成功执行
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ 连接失败${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi

    # 分离响应体和状态码
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    # 验证状态码
    if [ "$http_code" = "$expected_code" ]; then
        echo -e "${GREEN}✓ 通过${NC} (HTTP $http_code)"
        PASSED_TESTS=$((PASSED_TESTS + 1))

        # 详细模式输出响应体
        if [ "$VERBOSE" = true ] && [ -n "$body" ]; then
            if command -v jq &> /dev/null; then
                echo "$body" | jq . | sed 's/^/  /'
            else
                echo "$body" | sed 's/^/  /'
            fi
        fi
    else
        echo -e "${RED}✗ 失败${NC} (期望 $expected_code, 实际 $http_code)"
        FAILED_TESTS=$((FAILED_TESTS + 1))

        # 失败时总是输出响应
        if [ -n "$body" ]; then
            if command -v jq &> /dev/null; then
                echo "$body" | jq . | sed 's/^/  /'
            else
                echo "$body" | sed 's/^/  /'
            fi
        fi
    fi
}

# 主测试流程
main() {
    print_header "NASSAV API 综合测试"

    echo -e "${YELLOW}测试服务器: ${NC}$BASE_URL"
    echo -e "${YELLOW}详细模式: ${NC}$VERBOSE"
    echo ""

    # ========== 源管理 API ==========
    print_header "源管理 API"

    test_api "获取可用源列表" \
        "GET" "/nassav/api/source/list" "200"

    # ========== 资源列表 API ==========
    print_header "资源列表 API"

    test_api "获取资源列表（默认分页）" \
        "GET" "/nassav/api/resources/" "200"

    test_api "获取资源列表（指定分页）" \
        "GET" "/nassav/api/resources/?page=1&page_size=10" "200"

    test_api "搜索资源" \
        "GET" "/nassav/api/resources/?search=SSIS" "200"

    test_api "按状态过滤（已下载）" \
        "GET" "/nassav/api/resources/?status=downloaded" "200"

    test_api "按状态过滤（待下载）" \
        "GET" "/nassav/api/resources/?status=pending" "200"

    # ========== 演员和类别 API ==========
    print_header "演员和类别 API"

    test_api "获取演员列表" \
        "GET" "/nassav/api/actors/" "200"

    test_api "获取类别列表" \
        "GET" "/nassav/api/genres/" "200"

    # ========== 任务队列 API ==========
    print_header "任务队列 API"

    test_api "获取任务队列状态" \
        "GET" "/nassav/api/tasks/queue/status" "200"

    # ========== 下载列表 API ==========
    print_header "下载列表 API"

    test_api "获取已下载列表" \
        "GET" "/nassav/api/downloads/list" "200"

    # ========== 测试不存在的资源 ==========
    print_header "错误处理测试"

    test_api "获取不存在资源的预览" \
        "GET" "/nassav/api/resource/NOTEXIST-999/preview" "404"

    test_api "获取不存在资源的封面" \
        "GET" "/nassav/api/resource/cover?avid=NOTEXIST-999" "404"

    # ========== DEBUG 模式测试 ==========
    print_header "DEBUG 模式测试"

    # 检查是否有有效的 AVID 用于测试
    test_avid=$(curl -s "$BASE_URL/nassav/api/resources/?page_size=1" | \
        grep -o '"avid":"[^"]*"' | head -1 | cut -d'"' -f4)

    if [ -n "$test_avid" ]; then
        echo -e "${YELLOW}使用测试 AVID: ${test_avid}${NC}"

        test_api "模拟下载（应根据 DEBUG 状态返回 202 或 403）" \
            "POST" "/nassav/api/downloads/mock/$test_avid" "202|403" \
            '{"duration": 10}'
    else
        echo -e "${YELLOW}⚠ 数据库中没有资源，跳过模拟下载测试${NC}"
    fi

    # ========== 测试总结 ==========
    print_header "测试总结"

    echo -e "${BLUE}总测试数: ${NC}$TOTAL_TESTS"
    echo -e "${GREEN}通过: ${NC}$PASSED_TESTS"
    echo -e "${RED}失败: ${NC}$FAILED_TESTS"

    success_rate=0
    if [ $TOTAL_TESTS -gt 0 ]; then
        success_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi
    echo -e "${CYAN}成功率: ${NC}${success_rate}%"

    echo ""
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}🎉 所有测试通过！${NC}"
        exit 0
    else
        echo -e "${RED}❌ 部分测试失败${NC}"
        exit 1
    fi
}

# 执行主程序
main
