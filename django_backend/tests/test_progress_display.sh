#!/bin/bash
# 测试任务进度显示功能

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="http://localhost:8000/nassav"
TEST_AVID="ABF-139"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   测试任务进度显示功能${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}步骤 1: 提交模拟下载任务${NC}"
RESPONSE=$(curl -s -X POST "${BASE_URL}/api/downloads/mock/${TEST_AVID}?duration=25")
echo "$RESPONSE" | python3 -m json.tool

echo -e "\n${YELLOW}步骤 2: 等待 3 秒后检查任务状态和进度${NC}"
sleep 3

echo -e "\n${YELLOW}步骤 3: 获取任务队列状态${NC}"
QUEUE_STATUS=$(curl -s "${BASE_URL}/api/tasks/queue/status")

# 提取并显示 ABF-139 的任务信息
echo -e "${GREEN}任务详情:${NC}"
echo "$QUEUE_STATUS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tasks = data['data']['active_tasks'] + data['data']['pending_tasks']
abf = [t for t in tasks if t['avid']=='${TEST_AVID}']
if abf:
    task = abf[0]
    print(json.dumps(task, indent=2, ensure_ascii=False))
else:
    print('任务未找到')
"

echo -e "\n${YELLOW}步骤 4: 检查进度字段${NC}"
echo "$QUEUE_STATUS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
tasks = data['data']['active_tasks'] + data['data']['pending_tasks']
abf = [t for t in tasks if t['avid']=='${TEST_AVID}']

if abf:
    task = abf[0]
    progress = task.get('progress', {})

    print('✓ 任务状态:', task.get('state'))
    print('✓ 进度字段:')
    print('  - percent:', progress.get('percent', 'N/A'))
    print('  - speed:', progress.get('speed', 'N/A'))
    print('  - eta:', progress.get('eta', 'N/A'))
    print('  - downloaded:', progress.get('downloaded', 'N/A'))

    # 验证关键字段
    has_percent = 'percent' in progress
    has_speed = 'speed' in progress
    has_eta = 'eta' in progress

    if has_percent and has_speed:
        print('\n✓ 基本进度信息完整')
    else:
        print('\n✗ 缺少基本进度信息')

    if has_eta:
        print('✓ 包含 ETA 信息')
    else:
        print('⚠ 缺少 ETA 信息（可能需要重启 Celery worker）')
else:
    print('✗ 任务未找到')
"

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}测试完成！${NC}"
echo -e "${BLUE}========================================${NC}"
