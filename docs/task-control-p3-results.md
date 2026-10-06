# 任务控制 P3：下载暂停、终止和恢复

2026-10-06；分支 `feat/download-pause-cancel`；基线 `275c891`；提交标题 `[Feat] Control download execution and verify resumed media`。

## 实现和行为变化

新下载提交先保存 TaskJob/Attempt，再按稳定 attempt UUID 发布。响应新增 job_id，保留 task_id、status 等字段和 Celery 任务名。暂停持有 DB 去重名额；恢复换 attempt/generation；重复派发只允许一个执行领取。旧已发布消息未携带 job_id 时仍走旧下载流程，部署必须先排空旧 worker。

ControlledDownload 在来源获取前后、等槽位、分片复用校验、CLI、合并、视频校验和提交前检查控制。下载信息解析使用只读能力，不再通过 add_resource 的副作用修复链接。输出全部在私有工作区；暂停先确认 CLI/ffmpeg 进程组无 writer、释放 owner 租约，再保存检查点。终止只删私有目录，已有视频和已提交数据保留；新提交与正式删除使用同一资源锁协调。

CLI 的 100ms watchdog 在无 stdout 时检查控制；记录 host、boot_id、PID/PGID、启动 ticks、worker 身份及 lease owner。无法证明 writer 退出时拒绝确认停止及清理，仍归属本执行的 Redis key 变为不自动过期的恢复保留；不碰后继 owner。此异常须由 P7 的身份验证恢复或人工核查解除，不能无条件 DEL 全局锁。

受控 CLI 显式保留分片到正式提交后的私有清理，防止完成与暂停竞争时提前删缓存；旧调用仍自动清理。重启前校验播放列表身份及每个已有分片的远端内容，签名 query 变化不改变内容身份。AES-128 按 key/IV/sequence 解密后核对缓存，密钥内容也属于身份。损坏本地缓存仅在远端匹配原记录时删除重下；内容变化返回 paused/RESTART_REQUIRED，仅允许终止后重建，不静默拼接。

实测续传范围为闭合单轨 MPEG-TS VOD（明文/AES-128）。独立音轨、fMP4/byterange、不连续轨道或未知加密不承诺复用；首次可由 CLI 下载，暂停后的未知缓存须明确终止后重建。不能把受限证据推广到所有来源。

视频经 ffprobe 容器/轨道/时长检查、必要的真实 MP4 remux 和 ffmpeg 全量解码后才提升。大文件 SHA 在 DB 写入 fence 外校验，临界区重查 inode/大小/修改信息；DB 回调做短 ORM 操作和有界 Redis owner 检查，不做 HTTP/翻译/任务派发。video_committed 与业务提交一起落地，提交后到达的暂停恢复不会重复下载。

校验传输使用非 stream libcurl，总期限 20 秒（连接 5 秒、余下请求预算 15 秒），内容回调在分块间检查控制，最大 64 MiB；显式 CurlOpt.PROXY/NOPROXY 避免环境代理绕过下载专用配置。CLI/验证进程组 TERM 等待 2 秒后 KILL，再检查 writer 最多 2 秒，不将此配置视为真实来源停止 SLA。

Redis 只投影 active/progress，DB 是控制状态和历史的所有者。Channels 发送 task_job_update(job_id/job_type/version) 唤醒提示，不广播播放 URL、AES key 或私有路径；前端合并在 P6 接入。推送失败不回滚结果。待派发/未知 writer 的自动扫描仍待 P7。

## 验证

```bash
cd django_backend
uv run pytest tests/ --ds=django_project.refactoring_test_settings -v
PYTHONPATH=/tmp/nassav-task-control-p1-pg:. uv run pytest \
  tests/test_controlled_download.py tests/test_task_records.py \
  tests/test_task_assets.py tests/test_task_control_http.py \
  --ds=task_control_pg_settings -v
NASSAV_LOCAL_DOWNLOAD_BINARY=/tmp/nassav-task-control-p0/tools/N_m3u8DL-RE \
  uv run pytest tests/test_local_cli_task_control.py \
  --ds=django_project.refactoring_test_settings -v
# 同一真实 CLI 专项也使用上述 PYTHONPATH 与 task_control_pg_settings
# 根目录
pre-commit run -a
```

固定 P0 二进制、本地生成 24 秒 HLS 和隔离 SQLite 的真实 CLI 专项 2 passed：明文/AES 都保留至少 4 个分片，停止后无 CLI writer，恢复视频解码 hash 等于原样例，提交后私有目录清理。来源解析/校验 HTTP 使用本地文件替身，CLI 实际访问 loopback 服务；不属于非 eager Celery 联调或真实站点验收。

隔离 PostgreSQL 16 的任务/资产/HTTP 专项 67 passed，含真实 Redis 槽位转让。初次暴露取消回调在执行线程关闭 DB 连接、SQLite 未暴露的问题；限定仅 watchdog 清理自身连接后通过。原 URL/OpenAPI 快照保留，三个新增控制路由显式检查；没有重生成旧契约快照。

固定 CLI 的同一 2 项专项也在 PostgreSQL 16 通过。完整后端 630 passed、26 skipped；其中 2 项跳过为显式 opt-in 的本地 CLI 专项，已用上述固定二进制另行执行。迁移生成检查与 pre-commit 通过后提交。所有临时服务用后停止，媒体目录由 pytest 清理。

生产库没有运行迁移，正式文件没有写入/清理。真实 worker 重启、完整错误恢复及目标环境由 P7 验收；P4/P5 整条刮削和翻译控制尚未开放。
