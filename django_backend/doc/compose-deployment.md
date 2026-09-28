# 全栈 Compose 部署（P4）

从仓库根目录运行。基础 `compose.yaml` 选择 SQLite；PostgreSQL 需显式添加 `compose.postgres.yaml`。不要通过 `.env` 中的 `DB_ENGINE` 切换 Compose 模式；数据目录中的 `db/.nassav-db-mode` 是持久期望模式；若缺失或与当前 Compose 文件不一致，所有后端进程在连接数据库前退出。当前镜像针对 **Linux amd64**：下载器固定为 upstream `v0.5.1-beta` 的 glibc x64 包，并在构建时校验归档 SHA-256。镜像还安装下载器运行所需的 ICU 与 ffmpeg。其他架构会在构建时明确失败，需先确定对应发布包与校验值。Byparr 使用已经验证的镜像 digest，容器内地址为 `http://byparr:8191`。独立开发用 Byparr Compose 仍可保留；全栈 Byparr 不暴露宿主机端口。

配置来源、启动校验与开发 `.env` 语法见[启动配置契约](configuration-contract.md)。

## 空目录准备

在仓库根目录执行：

```sh
cp .env.example .env
# 将 .env 中 SECRET_KEY 替换为 openssl rand -hex 32 的输出
mkdir -p deploy-data/{config,db,resource,resource_backup,backup,backup_sync,log,celery_beat,redis,ollama}
cp django_backend/config/compose-config.example.yaml deploy-data/config/config.yaml
# 将 realpath deploy-data/resource/video 的结果填入 .env 的 NASSAV_VIDEO_HOST_DIR
# 在 deploy-data/config/config.yaml 中设置实际的站点、翻译及代理配置
# 基础文件固定 SQLite；只读渲染，不启动容器
python3 scripts/compose_stack.py --mode sqlite init
python3 scripts/compose_stack.py --mode sqlite config --quiet
python3 scripts/compose_stack.py --mode sqlite build
python3 scripts/compose_stack.py --mode sqlite up -d
```

部署入口默认项目名为 `nassav`，可用 `--project` 指定隔离项目。首次 `up` 按 Redis 健康检查 → `migrate` 成功 → API/worker → 前端健康检查启动。首次使用还须在目标数据库创建 operator 账号：`docker compose exec api python manage.py createsuperuser --username nassav`（若修改 `NASSAV_OPERATOR_USERNAME`，命令中使用同一用户名）。密码由交互提示输入，不写入 `.env`。检查 `docker compose ps -a` 和 `docker compose logs migrate api scrape-worker download-worker default-worker`。浏览器访问 `.env` 中的 `FRONTEND_BIND_ADDRESS:FRONTEND_PORT`（默认 `127.0.0.1:9780`）。SQLite 模式用 `docker compose --profile scheduler up -d` 启动唯一 Beat；PostgreSQL 模式须在每条 Compose 命令中同时传入 `-f compose.yaml -f compose.postgres.yaml`。先确认旧宿主机 Beat 已停。修改配置后运行 `docker compose restart api scrape-worker download-worker default-worker beat`（未启用 Beat 时省略它）。

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

API、`migrate`、三个 worker 和 Beat 共享同一组数据目录挂载；配置目录、SQLite 与 WAL/SHM、资源/视频/封面、导入备份、计划备份及同步副本、日志、Beat 状态及 Redis AOF 分别位于 `deploy-data/` 的同名子目录。`deploy-data/` 和 `.env` 已被 Git 忽略。镜像构建上下文排除本机凭证、数据库、资源及开发目录。“复制视频路径”接口使用 `NASSAV_VIDEO_HOST_DIR` 返回宿主机路径；浏览器所在机器必须能访问该目录。若更改 `NASSAV_DATA_DIR`，也要同步更改此值。宿主机的 `django_backend/config/config.yaml` 与 `django_backend/db.sqlite3` 不会进入容器。

## 数据库模式声明与部署入口

`NASSAV_DATA_DIR/db/.nassav-db-mode` 保存 `sqlite` 或 `postgres`，随整个数据目录备份和恢复。首次空目录运行 `python3 scripts/compose_stack.py --mode sqlite init`；外部 PostgreSQL 模式使用 `--mode postgres init`，并先准备存在的 `POSTGRES_PASSWORD_FILE`。已有数据目录须先核对当前运行容器的 Compose 文件标签、数据库备份和活动数据库模式，然后执行 `python3 scripts/compose_stack.py --mode postgres --adopt-existing init`（SQLite 则改为 `--mode sqlite`）。脚本不会覆盖相反模式的声明；正式数据库迁移与回退需按独立迁移计划处理数据，不能只改声明文件。

日常 `up`、`ps`、`logs`、`exec`、`down`、`build`、`restart` 都用同一个 `--mode`、`--project` 与 `--gpu`/`--profile` 组合，例如 `python3 scripts/compose_stack.py --mode postgres --gpu --profile scheduler ps -a`。脚本在执行 Compose 命令前校验数据目录声明、密码文件（PG 模式）、各后端服务渲染模式及当前运行后端容器的文件标签；模式冲突会在替换容器前拒绝。输出只展示项目、模式、数据库名/schema 和文件名，不展示环境变量或密码。需要查看配置时可使用 `config --quiet`，不要把未经脱敏的 `config` 输出写入日志。

直接执行原生 `docker compose up` 会绕过部署预检，可能先替换或停止正在运行的容器；但 `migrate`、API、三个 worker、启用时的 Beat 及模型准备任务都读取持久声明，在连库前拒绝缺失或冲突的模式，也不会创建意外 SQLite 业务库。若误用后服务中断，停止错误文件集合，确认声明和活动 PostgreSQL 未改动，再用原来的完整文件集合、项目名与镜像版本重新 `up -d`；检查 `migrate`、API、三个队列与 Beat 状态。不要在活动数据库上试验此过程。

隔离项目首次验证可使用独立 `NASSAV_DATA_DIR=/tmp/nassav-f2-check` 与 `--project nassav-f2-check`；PostgreSQL 还应使用独立测试库和虚构凭证。目标库不可达会使迁移失败，不能回落到 SQLite。备份恢复时声明文件必须与恢复的数据及目标数据库模式一致。

## 服务和代理

网关只发布前端端口，转发 `/nassav/api/` 与 `/nassav/ws/` 至 Django ASGI。WebSocket 设置 Upgrade、HTTP/1.1 和 3600 秒空闲超时。Redis、Byparr、API 和 worker 均仅位于 Compose 内部网络。`/healthz` 为内部 API 就绪检查，验证当前配置的数据库与 Redis；它不代表外部资源页面可抓取。容器有重启策略和内存上限。

`scrape-worker` 只监听 `scrape`，`download-worker` 只监听 `download`，`default-worker` 接收翻译与其他默认任务；三者并发与预取都为 1。Byparr 默认不设代理。Django 直接抓取与 Byparr 浏览器均读取 `config.yaml` 的 `Proxy.Enable/url`；Django 将浏览器代理按请求发送给 Byparr。`.env` 的 `BYPARR_PROXY_SERVER` 仅作为没有请求头时的 Byparr 默认值。下载器读取 `config.yaml` 的 `Proxy.download_url`；留空则直连，不回退到 `Proxy.url`，也不继承 worker 的系统代理环境变量。本地开发和代理优先级见[代理路由说明](proxy-routing.md)。容器内 `localhost` 指向各自容器，宿主机代理必须填容器可访问的网关地址；内网服务名已列入 `NO_PROXY`。不要将代理凭证写进提交文件或日志。

默认仅绑定 `127.0.0.1`，对外访问由同机 HTTPS 反向代理转发到该地址。所有业务 API 和任务 WebSocket 要求 `NASSAV_OPERATOR_USERNAME` 指定账号的登录会话；默认账号名为 `nassav`，仅创建账号后才可登录。`/healthz` 保持内部使用。

远程部署时在 `.env` 中设置 `ALLOWED_HOSTS=你的域名,localhost,127.0.0.1,api`、`CSRF_TRUSTED_ORIGINS=https://你的域名`、`NASSAV_SECURE_COOKIES=true`。HTTPS 代理必须转发 `/nassav/api/` 与 `/nassav/ws/`，保留原始 `Host`（含端口），覆盖传入的 `X-Forwarded-Proto` 为实际外部协议，支持 WebSocket Upgrade。不要让客户端自行伪造该头；Django 信任它判断 HTTPS 与 CSRF。前端页面、API 和 WebSocket 必须同源；浏览器用 session cookie 与 CSRF header，WebSocket 用同源 Origin。公网入口应限制登录请求速率。`ALLOWED_HOSTS` 是 Host 校验，不是登录机制。

## 验证

```sh
docker compose ps -a
docker compose exec api python manage.py check
docker compose exec download-worker /app/tools/N_m3u8DL-RE --version
docker compose exec api python -c "import socket; socket.create_connection(('byparr', 8191), 5).close()"
curl -i http://127.0.0.1:9780/nassav/api/auth/session
# 匿名业务请求应返回 401
curl -i http://127.0.0.1:9780/nassav/api/source/list
```

浏览器中再检查一次资源添加/刷新任务直至终态、一个实际下载的进度和文件、WebSocket 断线重连。真实外部页面和代理出口需要在目标环境按 [计划](async-scraping-compose-plan.md) 与 [P3 记录](async-scraping-p3-channel-evaluation.md) 测量；内部 TCP 和 `/healthz` 无法替代样本页验证。改端口时同步调整 `curl`。

隔离验证可设置独立项目名与数据目录，例如 `SECRET_KEY=... NASSAV_DATA_DIR=/tmp/nassav-p4-check FRONTEND_PORT=9781 docker compose -p nassav-p4-check up -d`。不要让两个栈同时写同一 SQLite、Redis 或资源目录。

## 外部 PostgreSQL（可选）

Compose 不创建或管理 PostgreSQL 服务；它只连接你单独部署和维护的 PostgreSQL 17 服务。SQLite 仍是默认配置。本机开发可直接在忽略的 `django_backend/config/config.yaml` 中设置 `Database.Engine: postgres` 及连接参数，包括 `Database.Schema`。Compose 使用覆盖文件，并在 `.env` 设置容器可访问的 `DB_HOST`、`DB_PORT`、可选的 `DB_SCHEMA`、`DB_NAME`、`DB_USER`，再创建密码文件。未设置 `DB_SCHEMA` 时使用应用配置中的 schema，默认为 `public`：

```sh
mkdir -p secrets
umask 077
printf '%s' '由管理员提供的数据库密码' > secrets/postgres_password
# 在 .env 中设置 POSTGRES_PASSWORD_FILE=./secrets/postgres_password

docker compose -f compose.yaml -f compose.postgres.yaml config --quiet
```

密码文件由 Compose secret 挂载到后端容器。不要把实际密码放进仓库或命令历史。容器访问宿主机上的 PostgreSQL 时可将 `DB_HOST` 设为 `host.docker.internal`；PostgreSQL 还须监听对应网卡并在 `pg_hba.conf` 允许来自 Docker 网络的应用账号连接。远端服务则填写其内网地址。数据库、目标 schema 和应用账号须由管理员预先创建；应用账号需在该 schema 上有使用和建表权限。启用前确认服务端备份策略和磁盘空间。

只有在已准备外部服务器、密码文件和空目标库后，才使用覆盖文件启动。覆盖文件对 `migrate`、API、三个 worker 和 Beat 统一设定 PostgreSQL 引擎、主机、库名、schema 与密码文件；密码或连接失败时不会使用 SQLite：

```sh
python3 scripts/compose_stack.py --mode postgres init
python3 scripts/compose_stack.py --mode postgres config --quiet
python3 scripts/compose_stack.py --mode postgres up -d --build
# 需要定时任务时，沿用同一文件集合启动唯一 Beat
python3 scripts/compose_stack.py --mode postgres --profile scheduler up -d
```

之后的 `ps`、`logs`、`exec`、`down` 也应保留相同的 `-f` 文件集合和项目名；不要只用基础文件重新执行 `up`。`migrate` 是 Compose 中的一次性服务，会在 API/worker 前运行。不要在生产实例上首次启用覆盖配置，直到活动 SQLite 源库、P0 基线、隔离演练和维护窗口都已确认。首次真实数据导入/迁移是单独的停写操作，不由本配置自动执行。PG 模式下后端镜像包含 PostgreSQL 17 客户端以供备份和恢复使用。

## 备份、恢复和回滚

切换前停止新任务并等待在途任务完成。停止 Compose 栈后，将整个 `deploy-data/`（包括 `db.sqlite3`、可能存在的 `-wal`/`-shm`、`resource/`、`config/`、`backup/`、`backup_sync/`、`celery_beat/`、`redis/`、`ollama/`）复制到外部备份位置；`.env` 单独妥善保管。恢复时保持所有写入者停止，用备份目录整体替换数据目录后启动同一镜像版本。SQLite 模式的 `backup_database` 执行 WAL checkpoint 并复制 SQLite/WAL/SHM；写入过程中不能把单个数据库文件的拷贝视为一致性快照。PostgreSQL 模式创建 `pg_dump -Fc` 备份，并用 `pg_restore --list` 检查归档。恢复必须指定新建的空数据库，例如：

```sh
docker compose -f compose.yaml -f compose.postgres.yaml exec api \
  python manage.py restore_postgres_backup /app/backup/database_postgresql_TIMESTAMP/database.dump
```

PostgreSQL 数据库恢复不搬移视频和资源目录。执行前先停止所有应用写入者，并确保目标数据库为空；恢复失败时丢弃并重建隔离目标库，不在部分恢复的数据库继续导入。

正式切换宿主机部署时，只让一套 API、Celery worker 与 Beat 写入这份数据。若 Compose 回退，停用新栈并从备份恢复完整数据目录，再启动原部署。不要直接把容器版与宿主机版同时指向同一个 SQLite 文件。
