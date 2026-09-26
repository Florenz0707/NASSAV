# 全栈 Compose 部署（P4）

从仓库根目录运行。当前镜像针对 **Linux amd64**：下载器固定为 upstream `v0.5.1-beta` 的 glibc x64 包，并在构建时校验归档 SHA-256。镜像还安装下载器运行所需的 ICU 与 ffmpeg。其他架构会在构建时明确失败，需先确定对应发布包与校验值。Byparr 使用已经验证的镜像 digest，容器内地址为 `http://byparr:8191`。独立开发用 Byparr Compose 仍可保留；全栈 Byparr 不暴露宿主机端口。

## 空目录准备

在仓库根目录执行：

```sh
cp .env.example .env
# 将 .env 中 SECRET_KEY 替换为 openssl rand -hex 32 的输出
mkdir -p deploy-data/{config,db,resource,resource_backup,backup,backup_sync,log,celery_beat,redis}
cp django_backend/config/compose-config.example.yaml deploy-data/config/config.yaml
# 将 realpath deploy-data/resource/video 的结果填入 .env 的 NASSAV_VIDEO_HOST_DIR
# 在 deploy-data/config/config.yaml 中设置实际的站点、翻译及代理配置
# 先用 docker compose config 检查环境变量

docker compose config --quiet
docker compose build
docker compose up -d
```

首次 `up` 按 Redis 健康检查 → `migrate` 成功 → API/worker → 前端健康检查启动。检查 `docker compose ps -a` 和 `docker compose logs migrate api scrape-worker download-worker default-worker`。浏览器访问 `.env` 中的 `FRONTEND_BIND_ADDRESS:FRONTEND_PORT`（默认 `127.0.0.1:9780`）。`docker compose --profile scheduler up -d` 才启动唯一 Beat 实例；先确认旧宿主机 Beat 已停。修改配置后运行 `docker compose restart api scrape-worker download-worker default-worker beat`（未启用 Beat 时省略它）。

示例翻译器指向 `host.docker.internal:11434`。如果 Ollama 在另一台机器或未对容器开放监听，请在 `config.yaml` 中改为容器可达地址；未运行 Ollama 时翻译任务会失败，资源添加任务仍可完成。

配置目录、SQLite 与 WAL/SHM、资源/视频/封面、导入备份、计划备份及同步副本、日志、Beat 状态及 Redis AOF 分别位于 `deploy-data/` 的同名子目录。`deploy-data/` 和 `.env` 已被 Git 忽略。镜像构建上下文排除本机凭证、数据库、资源及开发目录。“复制视频路径”接口使用 `NASSAV_VIDEO_HOST_DIR` 返回宿主机路径；浏览器所在机器必须能访问该目录。若更改 `NASSAV_DATA_DIR`，也要同步更改此值。宿主机的 `django_backend/config/config.yaml` 与 `django_backend/db.sqlite3` 不会进入容器。

## 服务和代理

网关只发布前端端口，转发 `/nassav/api/` 与 `/nassav/ws/` 至 Django ASGI。WebSocket 设置 Upgrade、HTTP/1.1 和 3600 秒空闲超时。Redis、Byparr、API 和 worker 均仅位于 Compose 内部网络。`/healthz` 为内部 API 就绪检查，验证 SQLite 与 Redis；它不代表外部资源页面可抓取。容器有重启策略和内存上限。

`scrape-worker` 只监听 `scrape`，`download-worker` 只监听 `download`，`default-worker` 接收翻译与其他默认任务；三者并发与预取都为 1。Byparr 默认不设代理。Django 抓取使用 `config.yaml` 的 `Proxy.url`；Byparr 浏览器使用 `.env` 的 `BYPARR_PROXY_SERVER`；下载器使用 `DOWNLOAD_PROXY_URL`，空值表示不使用代理。容器内 `localhost` 指向各自容器，宿主机代理必须填容器可访问的网关地址；内网服务名已列入 `NO_PROXY`。不要将代理凭证写进提交文件或日志。

默认仅绑定 `127.0.0.1`。现有 API 允许匿名访问，WebSocket 广播任务事件，因此不要直接将 `FRONTEND_BIND_ADDRESS` 改为公网地址。若经可信反向代理提供 HTTPS，应设置真实域名 `ALLOWED_HOSTS` 和 `CSRF_TRUSTED_ORIGINS`，并在外层限制访问。

## 验证

```sh
docker compose ps -a
docker compose exec api python manage.py check
docker compose exec download-worker /app/tools/N_m3u8DL-RE --version
docker compose exec api python -c "import socket; socket.create_connection(('byparr', 8191), 5).close()"
curl -i http://127.0.0.1:9780/nassav/api/source/list
```

浏览器中再检查一次资源添加/刷新任务直至终态、一个实际下载的进度和文件、WebSocket 断线重连。真实外部页面和代理出口需要在目标环境按 [计划](async-scraping-compose-plan.md) 与 [P3 记录](async-scraping-p3-channel-evaluation.md) 测量；内部 TCP 和 `/healthz` 无法替代样本页验证。改端口时同步调整 `curl`。

隔离验证可设置独立项目名与数据目录，例如 `SECRET_KEY=... NASSAV_DATA_DIR=/tmp/nassav-p4-check FRONTEND_PORT=9781 docker compose -p nassav-p4-check up -d`。不要让两个栈同时写同一 SQLite、Redis 或资源目录。

## 备份、恢复和回滚

切换前停止新任务并等待在途任务完成。停止 Compose 栈后，将整个 `deploy-data/`（包括 `db.sqlite3`、可能存在的 `-wal`/`-shm`、`resource/`、`config/`、`backup/`、`backup_sync/`、`celery_beat/`、`redis/`）复制到外部备份位置；`.env` 单独妥善保管。恢复时保持所有写入者停止，用备份目录整体替换数据目录后启动同一镜像版本。现有 `backup_database` 命令按文件复制 SQLite/WAL/SHM；在写入过程中不能把单个数据库文件的拷贝视为一致性快照。

正式切换宿主机部署时，只让一套 API、Celery worker 与 Beat 写入这份数据。若 Compose 回退，停用新栈并从备份恢复完整数据目录，再启动原部署。不要直接把容器版与宿主机版同时指向同一个 SQLite 文件。
