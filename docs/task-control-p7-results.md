# P7：后台恢复与真实 worker 隔离验收

日期：2026-10-06。分支 `chore/task-control-acceptance`，基线 `44ed2b9`（P6 已合并）。阶段提交以 Git 标题 `[Feat] Recover controlled tasks and validate real worker lifecycle` 追溯。完整设计见[任务控制计划](task-pause-cancel-design.md)。

## 已实现

每个 Celery worker ready 启动独立后台扫描，无需 Beat 或浏览器。恢复用例分别处理 pending 派发、sent 未领取消息补发、执行身份核查、暂停/终止确认、promoting 文件日志、清理失败和资源事件出箱；独立失败不当作任务成功。重复消息仍由 DB 原子领取拒绝。

心跳过期仅触发核查。确认同 host/boot/PID namespace 的原 worker 已退出后，查找继承 job/attempt/owner 的 CLI/ffmpeg 后代；包含未登记 PID 的子进程。核查启动时间、组内每个 writer 归属，TERM/KILL 有界等待且再次确认退出。活着或未知的 worker 保留状态及私有目录；只有停止已确认才释放仍属于旧 owner 的 Redis key、更新 stopped 和执行清理，不操作共享 worker。

未知旧容器/主机实例保持 RECOVERY_UNCONFIRMED。管理命令提供显式“原实例所有 writer 均已退出”的人工确认入口，拒绝本地仍活着或有近期心跳的任务；这是运维断言，不能由 HTTP 控制绕过。后台恢复翻译时只收尾该 child 的版本/owner，保留已完成译文和后来翻译。

补充行为修复：已终止但仍存在 promoting 日志的资源，正式删除也返回 409，避免删除后旧文件补偿将其恢复；暂停的未完成日志会持续重试，恢复按钮按日志状态禁用。联调补齐前端 source_complete/metadata_complete/cover_complete/saved 等中文阶段标签。

## 真实隔离联调

使用固定 P0 二进制、真实 **prefork Celery（并发 1，非 eager）**、临时 loopback Redis、生成的 MPEG-TS VOD、本地图片和翻译 HTTP fixture；SQLite 与无网络 PostgreSQL 16 临时容器各运行九项用例：

| 用例                                            | SQLite | PostgreSQL |
| ----------------------------------------------- | ------ | ---------- |
| 下载暂停确认并释放容量，另一任务可获取槽位      | 通过   | 通过       |
| 终止删除私有产物，保留已有正式视频              | 通过   | 通过       |
| 同 job/new attempt 恢复，完整视频解码 hash 一致 | 通过   | 通过       |
| worker 实际崩溃，后台自动停止残留 CLI 后收尾    | 通过   | 通过       |
| 实际目录权限错误导致清理失败，恢复权限后重试    | 通过   | 通过       |
| 刮削检查点复用及所属翻译暂停/恢复，整体完成     | 通过   | 通过       |
| 终止刮削清理私有图片，保留共享头像              | 通过   | 通过       |
| 翻译 worker 实际崩溃后终止，保留已提交资源      | 通过   | 通过       |
| 实际 Redis Broker 停止/重启，pending 后台重派   | 通过   | 通过       |

报告：[SQLite](task-control-probes/p7-sqlite.json)、[PostgreSQL](task-control-probes/p7-postgres.json)。本地下载暂停到确认本次分别测得 239ms/136ms，**仅为生成媒体与该环境的实测，不是实际来源 SLA**。事件投递注入失败保持 pending，恢复后使用同一稳定事件投递；fixture 结束检查无 running attempt/非终态任务、全局下载锁释放，停止自身 worker/Redis/HTTP 服务并删除临时资源。

## 回归与质量门槛

从后端执行：

```bash
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
# PG 使用 /tmp 的隔离设置和无网络临时容器。
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest \
  tests/test_batch_translation_state.py tests/test_controlled_download.py \
  tests/test_controlled_scrape.py tests/test_controlled_translation.py \
  tests/test_http_contracts.py tests/test_persistent_scrape_http.py \
  tests/test_task_assets.py tests/test_task_control_http.py \
  tests/test_task_records.py tests/test_task_recovery.py --ds=task_control_pg_settings -v
```

验证结果：完整 SQLite 隔离回归 697 通过、26 跳过；PG 任务专项 140 通过；PG 明文/AES-128 原生恢复及资产/恢复补查 40 通过，SQLite 原生恢复补查 2 通过。前端 `pnpm run check` 为 54 单元测试通过、lint 与构建通过，P6 完整浏览器套件及 P7 任务控制复查通过。根目录 `pre-commit run -a` 全部通过；钩子配置保持。各阶段已有证据保留在 P0–P6 执行记录，本阶段实际命令与结果以本分支提交和验收报告为准。

## 目标环境边界

请求通过已授权 DRF APIClient 调用真实 HTTP 层，网络准备与下载/翻译响应来自本地 fixture；这是实际 worker/CLI/DB/恢复联调，未做真实站点、真实翻译模型、Docker 新旧 worker 切换、HTTPS/WSS 网关验收。正式数据库未迁移，正式服务未部署。上线及回滚必须按[部署说明](../django_backend/doc/compose-deployment.md#持久任务控制版本切换与回滚)执行，不依据本地通过自动上线。
