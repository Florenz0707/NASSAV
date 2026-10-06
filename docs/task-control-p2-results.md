# 任务控制 P2：私有文件、提交日志和清理

2026-10-06；分支 `feat/task-artifact-workspaces`；基线 `11c8aeb`；提交标题 `[Feat] Journal task assets and protect private cleanup`。

## 已实现

TaskAssets 在 cover/avatar/video 各根下管理 `.tasks/<job_id>/`；预计写入路径先登记，producer 仅收到私有路径。校验、提交与停止分别检查执行 owner/generation；迟到 producer 不能记录当前 generation 的完成资产。相对路径拒绝穿越、符号链接及控制字符，根目录禁止相同/嵌套，checksum 打开文件使用 O_NOFOLLOW，Linux fd 清理不遍历链接。

提交先保存 promoting 日志，再持有资源/共享目标短锁及 DB 写入 fence，备份旧文件、提升资产、执行 ORM 回调并标记 committed。回调异常时回滚 DB 并恢复正式文件。文件内容相同时通过私有源是否仍存在区分“尚未提升”和“已经提升”；正式发布 marker 区分后来任务的同内容发布。数据库迁移 0023 增加 TaskAssetTarget；没有运行正式迁移。

恢复拒绝仍有 running attempt 的任务，且短恢复事务阻止同时 resume/claim。缺备份、校验不符或归属变化保留现场，cleanup_state=failed；不得盲目恢复旧文件。恢复未完成的 promoting 日志前不能 resume。终态清理只删除本 job 私有目录，保留正式文件、共享头像、既有视频和已保存 DB 数据；cleanup_retry 幂等登记新的 pending 清理，不复活任务。

正式删除复用原锁文件路径，已有活动/暂停任务时返回 409；备份跳过 `.tasks`。本阶段资产协议是内部能力；既有生产任务尚未使用私有工作区，新增任务创建与删除的完整竞争协调、CLI/图像内容验证及执行器退出由 P3/P4 接入完成。不将仅非空文件的通用 stage 视为图像或视频内容有效。

## 验证与范围

```bash
cd django_backend
uv run pytest tests/test_task_assets.py tests/test_task_records.py \
  --ds=django_project.refactoring_test_settings -v
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest \
  tests/test_task_assets.py tests/test_task_records.py \
  --ds=task_control_pg_settings -v
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
uv run python manage.py makemigrations --check --dry-run \
  --settings=django_project.refactoring_test_settings
# 根目录
pre-commit run -a
```

专项 41 项在 SQLite 和隔离 PostgreSQL 16 通过；容器无网络、数据 tmpfs，仅挂载 /tmp 私有 Unix socket，测试 DB 用后销毁。覆盖提交部分失败、相同内容回滚、真实 ORM 回滚、多文件补偿、停止前拒绝清理、旧 marker 拒绝恢复、备份缺失保留正式文件、清理 PermissionError 后重试、链接及穿越拒绝、活动任务删除冲突和备份排除。全套后端 604 passed、24 skipped；迁移一致性与 pre-commit 通过后提交。

本阶段只提供文件/DB 隔离验证，没有连接正式资源站点、数据库或目录；真实 CLI、非 eager worker 停止、断电持久性和目标环境验收仍待 P3–P7。
