#!/bin/bash
# 测试完整任务队列显示功能（B2 任务）
# 用途：验证多个任务提交后，队列状态 API 能够显示所有任务

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:8000/nassav"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   测试完整任务队列显示功能（B2任务）${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 测试 AVID 列表
TEST_AVIDS=("ABF-139" "DASS-002" "IPX-416")

echo -e "${YELLOW}步骤 1: 快速提交模拟下载任务${NC}"
for avid in "${TEST_AVIDS[@]}"; do
    echo -e "${BLUE}提交任务: ${avid}${NC}"
    curl -s -X POST "${BASE_URL}/api/downloads/mock/${avid}?duration=15" \
        -H "Content-Type: application/json" | jq -r '.message'
    sleep 0.5
done

echo -e "\n${YELLOW}步骤 2: 等待 2 秒后查询队列状态${NC}"
sleep 2

echo -e "\n${YELLOW}步骤 3: 获取完整任务队列状态${NC}"
RESPONSE=$(curl -s -X GET "${BASE_URL}/api/tasks/queue/status")

echo -e "${GREEN}队列状态响应:${NC}"
echo "$RESPONSE" | jq '.'

# 解析并显示关键信息
PENDING_COUNT=$(echo "$RESPONSE" | jq '.data.pending_tasks | length')
ACTIVE_COUNT=$(echo "$RESPONSE" | jq '.data.active_tasks | length')
TOTAL_COUNT=$((PENDING_COUNT + ACTIVE_COUNT))

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}   队列统计${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${BLUE}待处理任务数: ${NC}${PENDING_COUNT}"
echo -e "${BLUE}执行中任务数: ${NC}${ACTIVE_COUNT}"
echo -e "${BLUE}队列总任务数: ${NC}${TOTAL_COUNT}"

# 验证结果
echo -e "\n${YELLOW}步骤 4: 验证结果${NC}"
if [ "$TOTAL_COUNT" -ge 4 ]; then
    echo -e "${GREEN}✓ 成功: 队列显示了 ${TOTAL_COUNT} 个任务（预期 >= 4）${NC}"
    echo -e "${GREEN}✓ B2 任务测试通过：完整任务队列显示正常${NC}"
else
    echo -e "${RED}✗ 失败: 队列只显示了 ${TOTAL_COUNT} 个任务（预期 >= 4）${NC}"
    echo -e "${RED}✗ 这表明 B2 任务可能未完全生效${NC}"
fi

# 显示详细任务列表
echo -e "\n${YELLOW}步骤 5: 详细任务列表${NC}"
echo -e "${BLUE}待处理任务:${NC}"
echo "$RESPONSE" | jq -r '.data.pending_tasks[] | "  - \(.avid) (任务ID: \(.task_id))"'

echo -e "\n${BLUE}执行中任务:${NC}"
echo "$RESPONSE" | jq -r '.data.active_tasks[] | "  - \(.avid) (任务ID: \(.task_id), 进度: \(.progress.percent)%)"'

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}测试完成！${NC}"
echo -e "${BLUE}========================================${NC}"
