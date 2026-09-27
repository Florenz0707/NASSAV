# 全栈 Compose 部署（P4）

从仓库根目录运行。当前镜像针对 **Linux amd64**：下载器固定为 upstream `v0.5.1-beta` 的 glibc x64 包，并在构建时校验归档 SHA-256。镜像还安装下载器运行所需的 ICU 与 ffmpeg。其他架构会在构建时明确失败，需先确定对应发布包与校验值。Byparr 使用已经验证的镜像 digest，容器内地址为 `http://byparr:8191`。独立开发用 Byparr Compose 仍可保留；全栈 Byparr 不暴露宿主机端口。

## 空目录准备

在仓库根目录执行：

```sh
cp .env.example .env
# 将 .env 中 SECRET_KEY 替换为 openssl rand -hex 32 的输出
mkdir -p deploy-data/{config,db,resource,resource_backup,backup,backup_sync,log,celery_beat,redis,ollama}
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

### 可选 Ollama profile

Ollama 使用[官方容器镜像](https://docs.ollama.com/docker)，仅在 `translator` profile 启用时运行，模型保存在 `deploy-data/ollama/`，不发布 11434 端口。镜像按已核对的 `0.13.5` digest 固定。默认栈仍使用配置中的外部 Ollama 地址。启用前在 `.env` 设置 `OLLAMA_URL=http://ollama:11434`，并在 `deploy-data/config/config.yaml` 的 `Translator.active` 对应配置中填好要使用的 `model`。首次启动会根据此配置拉取模型；模型可能占用数 GB，下载与首次加载需要时间。

```sh
# CPU 模式；默认不需要独立启动或手动拉模型
docker compose --profile translator up -d --build
# 查看一次性模型准备任务是否成功
docker compose --profile translator ps -a
docker compose --profile translator logs ollama ollama-model default-worker
```

`ollama-model` 在模型出现在 `/api/tags` 后成功退出；后端进程在指向内网 Ollama 时会再次检查模型，未就绪则退出并由 Compose 重启，避免进程长期缓存“翻译器不可用”的状态。更换模型需修改 `config.yaml`，然后运行 `docker compose --profile translator up -d --force-recreate ollama-model`，确认任务退出码为 0 后运行 `docker compose restart api scrape-worker download-worker default-worker`（启用了 Beat 时也重启 Beat）。若原先已有宿主机 Ollama，容器模型卷与宿主机模型目录相互独立；不要同时把两套服务写入同一模型目录。停用容器版时清空 `.env` 的 `OLLAMA_URL` 并重启 API/worker，恢复配置文件中的外部地址。

当前机器若已给 Docker 配好 NVIDIA GPU 运行时，可用 [Compose GPU 覆盖文件](../../compose.gpu.yaml)启动：

```sh
docker compose -f compose.yaml -f compose.gpu.yaml --profile translator up -d --build
```

GPU 资源预留按 [Docker Compose 官方说明](https://docs.docker.com/compose/how-tos/gpu-support/)配置；其他机器可只用 CPU profile。CPU 推理与模型同时驻留的内存开销应在目标机实测。模型拉取需要出网；如需代理，只为 Ollama 设置 HTTPS 代理，不要把内部 `ollama` 服务名流量送到代理。

配置目录、SQLite 与 WAL/SHM、资源/视频/封面、导入备份、计划备份及同步副本、日志、Beat 状态及 Redis AOF 分别位于 `deploy-data/` 的同名子目录。`deploy-data/` 和 `.env` 已被 Git 忽略。镜像构建上下文排除本机凭证、数据库、资源及开发目录。“复制视频路径”接口使用 `NASSAV_VIDEO_HOST_DIR` 返回宿主机路径；浏览器所在机器必须能访问该目录。若更改 `NASSAV_DATA_DIR`，也要同步更改此值。宿主机的 `django_backend/config/config.yaml` 与 `django_backend/db.sqlite3` 不会进入容器。

## 服务和代理

网关只发布前端端口，转发 `/nassav/api/` 与 `/nassav/ws/` 至 Django ASGI。WebSocket 设置 Upgrade、HTTP/1.1 和 3600 秒空闲超时。Redis、Byparr、API 和 worker 均仅位于 Compose 内部网络。`/healthz` 为内部 API 就绪检查，验证 SQLite 与 Redis；它不代表外部资源页面可抓取。容器有重启策略和内存上限。

`scrape-worker` 只监听 `scrape`，`download-worker` 只监听 `download`，`default-worker` 接收翻译与其他默认任务；三者并发与预取都为 1。Byparr 默认不设代理。Django 抓取使用 `config.yaml` 的 `Proxy.url`；Byparr 浏览器使用 `.env` 的 `BYPARR_PROXY_SERVER`；下载器读取 `config.yaml` 的 `Proxy.download_url`；留空则直连，不回退到 `Proxy.url`，也不继承 worker 的系统代理环境变量。本地开发和代理优先级见[代理路由说明](proxy-routing.md)。容器内 `localhost` 指向各自容器，宿主机代理必须填容器可访问的网关地址；内网服务名已列入 `NO_PROXY`。不要将代理凭证写进提交文件或日志。

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

切换前停止新任务并等待在途任务完成。停止 Compose 栈后，将整个 `deploy-data/`（包括 `db.sqlite3`、可能存在的 `-wal`/`-shm`、`resource/`、`config/`、`backup/`、`backup_sync/`、`celery_beat/`、`redis/`、`ollama/`）复制到外部备份位置；`.env` 单独妥善保管。恢复时保持所有写入者停止，用备份目录整体替换数据目录后启动同一镜像版本。现有 `backup_database` 命令按文件复制 SQLite/WAL/SHM；在写入过程中不能把单个数据库文件的拷贝视为一致性快照。

正式切换宿主机部署时，只让一套 API、Celery worker 与 Beat 写入这份数据。若 Compose 回退，停用新栈并从备份恢复完整数据目录，再启动原部署。不要直接把容器版与宿主机版同时指向同一个 SQLite 文件。
