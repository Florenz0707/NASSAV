# 后端运行目录与取消任务收尾修复（2026-10-06）

## 变更

分支 `fix/backend-volume-ownership`，基线 `6d5fe89`，提交标题 `[Fix] Align backend runtime ownership and recover cancelled task cleanup`。

Docker 后端没有显式 user，root 创建的 `.tasks`、配置、日志及备份运行目录使宿主机 UID 1000 无法维护。Compose 现在将 API、migrate、三个 worker、Beat、ollama-model 的 user 统一为 `.env` 中 `NASSAV_UID:NASSAV_GID`（默认 1000:1000），渲染护栏拒绝 root、非数字或不一致身份。Beat PID 文件移入可写运行卷。

新增 `scripts/prepare_backend_permissions.py`：默认只读预览，显式 `--repair --writers-stopped` 才准备/修复限定路径，先拒绝链接、路径穿越及特殊文件，不遍历正式媒体文件，不删除任何锁或缓存，不修改 Redis、Ollama 卷及密码文件。锁文件继续保留，结束操作或进程退出释放 flock；不增加在线删除锁文件机制。范围和命令见[部署说明](../django_backend/doc/compose-deployment.md#后端运行身份与任务目录权限)。

## 隔离验证

- 权限与 Compose 专项 15 项通过：预览不写入、停止断言、锁 inode/缓存内容保持、正式媒体文件模式保持、符号链接/硬链接/路径穿越拒绝及 user 护栏。
- Compose 只读渲染：七个后端服务均为 1000:1000，Beat PID 在其运行卷。
- 真实 Docker 探针：临时目录先由 root 创建缓存，再通过脚本修复。以 UID 1000、network none 启动当前后端镜像，验证全部运行目录写入、SQLite 写入、flock、缓存删除及 loopback HLS 原生下载/清理。探针目录与容器已清理。
- 后端目录 `uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：736 通过、28 跳过（80.79s）；根目录 `pre-commit run -a` 全通过，结果维护于[验证状态](../django_backend/doc/validation-status.md)。钩子配置未修改。

## 当前实例处理

只读核对实际 Compose 所有服务停止，宿主机无 Celery、uvicorn、下载器或 ffmpeg 进程。实际 PostgreSQL 只读事务确认 HMN-606 job `ebf1deb6-191c-44f2-af96-fb621a0958d9` 为 cancelling / RECOVERY_UNCONFIRMED；旧 attempt `11aeeabf-6eca-46e9-b4df-4cbf650a6c50` 仍记为 running，记录的旧容器不再运行。这是停止身份待确认导致的保留，不是目录扫描生成任务。

明确核对并修复 `/home/florenz/NASSAV/deploy-data` 的后端运行目录，以及 `/home/florenz/NASSAV/django_backend/resource` 的目录/私有缓存/锁，205 个条目改为 1000:1000。绑定 resource 本身是链接，修复工具传入已核对的真实目录。六个原锁 inode 保持，复核零权限差异。

临时启动原 Redis 以原 owner 释放锁，使用当前镜像和 UID 1000 执行现有 fenced `recover_tasks --confirm-stopped-attempt ... --all-writers-stopped`，仅收尾该已请求取消的任务。返回 cancelled / cleanup_state=completed，目标 `.tasks/<job_id>` 目录已删除；没有用 rm 清除任务、没有清空 Redis、没有迁移数据库或删除正式视频。随后 Redis 恢复停止，其余正式服务全程保持停止。

## 部署边界

默认 dev 工作树不变，代码仅合并辅助工作树 idle。当前目录权限和指定取消任务收尾已在目标实例验收；Compose 新运行身份须在用户合并代码后重新创建后端容器，restart 不应用 user。当前 `.env` 未覆盖新 UID/GID 时默认 1000:1000 符合本机账号；其他主机需显式核对。正式 API/worker 持续运行、其他任务及真实外站下载不属于本轮验收。
