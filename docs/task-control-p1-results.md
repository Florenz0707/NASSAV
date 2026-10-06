# 任务控制 P1：持久记录与执行归属

2026-10-06；分支 `feat/task-control-records`；提交标题 `[Feat] Persist versioned task controls and execution attempts`。阶段基线 `29e1b47`。本阶段提供内部 Module 的 Interface，不开放 HTTP 控制入口，不改变旧任务提交行为，不运行正式数据库迁移。

## 实现

- TaskJob/Attempt/Artifact 模型和迁移 0022；另增加 TaskCommand，以持久 request_id 解决恢复请求在后续状态变化后再次到达的幂等问题。
- `DjangoTaskRecords.create/get/request` 管理业务任务和去重名额；`claim/check/checkpoint/acknowledge_stop/finish/heartbeat` 验证 generation 与随机 execution owner。暂停请求及实际停止分开记录，终态不复活。
- 事务和 version 条件更新处理 SQLite/PostgreSQL 并发；暂停保留去重名额、恢复更换 attempt UUID；旧消息、旧 checkpoint、旧失败收尾及重复领取被拒绝。
- `dispatch_pending(send)` 接受显式发送依赖，生产发送尚未装配。pending attempt 在发布前落地；失败保留重试；worker 比发布确认先领取时不倒退到 sent；控制期间送达的旧消息被入口拒绝。
- 操作者归属在控制前验证；跨任务控制被拒绝，受信任入口可显式授予 `allow_all`。当前内部 get 供执行模块读取，HTTP 装配时仍须鉴权，不能将它直接开放为匿名读取。
- 清理状态独立记录；Artifact 仅为数据模型，P1 不删任何文件。停止确认 Interface 要求调用者先确认 writer 退出；P3/P4 执行 Adapter 负责满足该前置条件。

## 验证

SQLite 专项 16 passed，覆盖控制竞争、重复派发、历史幂等、暂停超过旧 Redis TTL 后由新 Adapter 恢复读取及新旧执行交错。相同 16 项在真实隔离 PostgreSQL 16 容器通过：网络关闭、数据目录 tmpfs、Unix socket 位于 `/tmp/nassav-task-control-p1-pg`；未挂载应用资源或实际数据库。

```bash
cd django_backend
uv run pytest tests/test_task_records.py \
  --ds=django_project.refactoring_test_settings -v
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest tests/test_task_records.py \
  --ds=task_control_pg_settings -v
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
uv run python manage.py makemigrations --check --dry-run \
  --settings=django_project.refactoring_test_settings
# 根目录
pre-commit run -a
```

临时 task_control_pg_settings 继承 refactoring_test_settings，仅把 DATABASES 切换到上述私有 Unix socket、测试数据库 `nassav_task_control` 与 postgres 测试用户；pytest 创建并销毁 test 数据库。它不读取生产数据库配置，不对外监听宿主机 TCP。

全套门槛初次暴露旧 Cookie 迁移测试固定恢复到 0021、删除新任务表的问题。最小复现命令是 Cookie 迁移回归与任务并发领取组合，1 failed/1 passed；改为恢复原迁移图叶节点后 2 passed。该修复保护未来新增迁移，不改变正式迁移行为。修复后全套 579 passed、24 skipped，pre-commit 全部通过；迁移生成检查通过后提交。

P1 证明持久控制与数据库并发契约，不证明 CLI/HTTP 实际停止、文件补偿、非 eager worker 消息恢复或前端操作已实现；这些仍是 P2–P7 的门槛。
