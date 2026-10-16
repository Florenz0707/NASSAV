# 全栈 Compose 部署（P4）

从仓库根目录运行。基础 `compose.yaml` 选择 SQLite；PostgreSQL 需显式添加 `compose.postgres.yaml`。不要通过 `.env` 中的 `DB_ENGINE` 切换 Compose 模式；数据目录中的 `db/.nassav-db-mode` 是持久期望模式；若缺失或与当前 Compose 文件不一致，所有后端进程在连接数据库前退出。当前镜像针对 **Linux amd64**：下载器固定为 upstream `v0.5.1-beta` 的 glibc x64 包，并在构建时校验归档 SHA-256。镜像还安装下载器运行所需的 ICU 与 ffmpeg。其他架构会在构建时明确失败，需先确定对应发布包与校验值。Byparr 使用已经验证的镜像 digest，容器内地址为 `http://byparr:8191`。独立开发用 Byparr Compose 仍可保留；全栈 Byparr 不暴露宿主机端口。

配置来源、启动校验与开发 `.env` 语法见[启动配置契约](configuration-contract.md)。

`deploy-data/config` 绑定到 `/app/config` 后，目录内的 `config.yaml` 符号链接按容器路径解析。若链接指向宿主机仓库的绝对路径，或相对路径越出挂载目录，容器未挂载目标时会报配置不可读/不可解析。建议按下方步骤复制实际 YAML 文件，核对文件可读与内容有效后重启；不能仅凭宿主机 `readlink` 成功判断容器可读。资源目录本身作为 bind source 的符号链接另见权限迁移说明。

## 空目录准备

在仓库根目录执行：

```sh
cp .env.example .env
# 将 .env 的 NASSAV_UID/NASSAV_GID 设置为 id -u / id -g 的结果
# 将 .env 中 SECRET_KEY 替换为 openssl rand -hex 32 的输出
mkdir -p deploy-data/{config,db,resource,resource_backup,backup,backup_sync,log,celery_beat,redis,ollama}
cp django_backend/config/compose-config.example.yaml deploy-data/config/config.yaml
# 所有后端使用同一非 root 身份；首次部署以该宿主机用户准备目录
python3 scripts/prepare_backend_permissions.py --data-dir "$PWD/deploy-data" --resource-dir "$PWD/deploy-data/resource" --uid "$(id -u)" --gid "$(id -g)" --repair --writers-stopped
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

如果 `init` 报 `Permission denied: .../deploy-data/db`，先核对 `.env` 的 `NASSAV_DATA_DIR` 与 `/app/data/db` 的预期 bind 目录一致。Docker 可能先把 `deploy-data` 建成 `root:root 755`，此时普通用户无法新建 `db`。只创建并授权这个子目录，再重试 `init`：

```sh
sudo install -d -m 0755 -o "$(id -u)" -g "$(id -g)" deploy-data/db
python3 scripts/compose_stack.py --mode postgres init
```

上例路径须替换为本机实际的 `NASSAV_DATA_DIR/db`；不要递归修改整个数据目录的属主。已有 `db` 目录时，先核对里面的数据库文件和备份，再调整该目录权限。`init` 只写入模式声明，不会启动或迁移数据库。

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

浏览器中再检查一次资源添加/刷新任务直至终态、一个实际下载的进度和文件、WebSocket 断线重连。真实外部页面和代理出口需要在目标环境按[部署与验证边界](compose-deployment.md#近期改动与验证边界)测量；内部 TCP 和 `/healthz` 无法替代样本页验证。改端口时同步调整 `curl`。

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

## 下载 worker 版本切换

原 Celery task 名称和路由保持，不代表旧、新锁实现可混用。旧 worker 的无条件删锁会破坏新执行的 owner 保护；更新前停止旧版本继续消费，并检查在途任务、租约与队列记录，再按确认的版本启动 API/worker。不要清空共享 Redis 或手工删除当前 owner 的锁作为升级步骤。

切换验收至少包含去重/积压任务、重试、失租失败、CLI 中止、进度/文件及 DB 状态和 WebSocket 终态。正常完成后 DB 仍可能只记录告警；资源/媒体一致性需单独检查。本文没有执行切换，隔离/eager 通过不代表混合版本或目标环境接受；当前结果见[部署与验证边界](compose-deployment.md#近期改动与验证边界)。宿主机进程使用同样版本边界，见[进程管理](host-processes.md)。

任务控制 P1–P5 增加 DB 迁移 0022–0025、下载/刮削 job_id 和翻译 expected_generation。先停止旧发布者/消费者、排空旧任务并备份，在隔离副本验证迁移后统一更新 API/worker。旧 worker 不能接收新 kwargs，未带版本的旧翻译消息也不能推断派发时归属。部署前等待 P6/P7 全流程门槛，包括前端持久快照与自动恢复；本轮只实施隔离验证，未授权正式迁移或服务切换。

存在 paused 工作区、promoting 日志或未知 writer 保留租约时，不能直接回滚到不认识这些记录的版本。终止/核查新活动任务并完成清理后再回滚；不要清空 Redis 或无条件删除保留锁。默认备份排除 `.tasks`，保留暂停任务需另行保全其 DB 与私有目录，不能认为普通媒体备份已包含续传检查点。

## 持久任务控制版本切换与回滚

本轮 P0–P7 的隔离验收已完成，正式库迁移和目标环境切换未执行。生产上线应在明确维护窗口按如下顺序进行：

1. 备份数据库及正式资源，记录当前镜像、CLI SHA、配置与活动任务；迁移涉及 0022–0025。
2. 暂停新增提交，排空旧 download/scrape/default 队列并确认旧 worker 停止消费。旧消息没有 job_id，不能由新前端承诺可暂停/终止；旧 worker 不认识 TaskJob，不允许混用。
3. 使用现有 DB 模式护栏和 `migrate` 服务迁移，再同时替换 API、三个 worker 与前端；保留原任务名和队列。P3 的固定 CLI/ffmpeg 及私有 `.tasks` 写入权限必须满足。若未部署 worker，仅 API 接受的 pending 任务不会自动执行。
4. 检查任务 GET/控制鉴权、CSRF、WS 提示、目录权限和恢复 Loop 日志。先用可删除样例完成下载/刮削暂停恢复及终止，确认正式视频/共享头像保留，再开放提交。P7 的本地网络 fixture 不证明真实站点、Ollama、容器或 HTTPS/WSS 网关已接受。

每个 worker ready 启动恢复 Loop，不要求 scheduler profile。必要时从相同配置的后端运行一次：

```bash
uv run python manage.py recover_tasks --stale-seconds 30 --retry-seconds 300 --limit 100
```

输出 recovered/unconfirmed/alive/cleaned/events/failed 和派发汇总，不含私有检查点。alive 保留执行，unconfirmed 保留控制状态与文件；看到心跳过期不能直接删工作区或 Redis 锁。扫描确认本地 writer 退出后只释放其 owner 的 Redis key，不删除新 owner 的锁。

容器重建、主机重启或进程命名空间变化后，自动扫描可能无法确认旧实例。管理员须根据旧容器身份/启动记录，确认它已经停止且所有后代均退出；无需且不可向新容器中同号 PID 发信号。**只有完成该核查后**，对快照当前 task_id（翻译中为 child attempt）执行：

```bash
uv run python manage.py recover_tasks --confirm-stopped-attempt ATTEMPT_UUID --all-writers-stopped
```

这是操作人的退出断言，不是额外的自动证明；命令仍拒绝已知活着的本地 worker、近期心跳及旧 generation。重复确认不再次恢复执行。取消意图进入 cancelled 并清理私有文件，否则进入 paused；随后通过页面决定恢复或终止。普通 HTTP 终止始终等待 writer 确认。

回滚代码前先停止新提交，暂停/终止新任务，等待清理和 promoting 日志完成；确认没有运行/待派发/暂停占名额的新任务及子翻译，停下全部新消费者，再切换整套旧版本。不能只回滚 worker、让旧任务绕过控制；也不能回滚后自动删除 `.tasks`。新增表/字段可先保留；反向迁移是独立数据库维护操作，须另行备份与演练，不作为代码回滚自动步骤。

## 后端运行身份与任务目录权限

Compose 的 API、migrate、三个 worker、Beat、ollama-model 统一使用 `NASSAV_UID:NASSAV_GID`，默认 `1000:1000`。在 `.env` 设置为宿主机实际账号的 `id -u` / `id -g`；不支持 root 或各服务不同身份，compose_stack 渲染护栏会拒绝。Redis、Byparr、Ollama、前端保留各自镜像身份，不改变它们的卷属主。Beat 的 PID 文件和 schedule 都在 `/app/celery_beat/`。变更 user 后必须重新创建容器，restart 不会应用新身份。

已有 root 目录不能只改 user 就启动。先暂停/终止任务，确认所有旧 API/worker、Beat 及下载器后代停止，再预览限定范围：

```bash
python3 scripts/prepare_backend_permissions.py --data-dir /实际/deploy-data --resource-dir /实际/resource --uid 1000 --gid 1000
# 仅在确认上述所有写入者停止后执行；需要现有文件的 chown 权限
sudo python3 scripts/prepare_backend_permissions.py --data-dir /实际/deploy-data --resource-dir /实际/resource --uid 1000 --gid 1000 --repair --writers-stopped
```

脚本只递归检查/修复后端 config、db、log、resource_backup、backup、backup_sync、celery_beat，以及资源 `.tasks`、三类 `.nassav-*-locks`；默认正式媒体只修改资源根与 cover/avatar/video/recommendation_cover 目录本身，不遍历媒体文件。旧 root 部署迁移时，增加 `--include-published` 才检查/修复这些目录中的正式文件（同样需停止写入者，保持内容与 inode）。修复保留内容、锁 inode、缓存及已有 group/other 权限，补足 owner 读写和目录执行权限，不使用 777。默认只读检查，不创建路径；需修复时退出 1。显式 repair 创建缺失运行目录，先拒绝符号链接、硬链接与特殊文件再修改。`--writers-stopped` 是操作者对停止事实的断言，不是脚本自动检测。

`deploy-data/resource -> django_backend/resource` 的挂载方式可以保留：Docker 绑定其实际目录，链接自身的属主不决定目标文件权限。数据目录的 resource 若是符号链接，核实实际目标后显式将 `--resource-dir` 设为真实路径；脚本不会自动跟随链接。旧正式文件为 root:root 644 时，仅修复目录不足以完成迁移；原生文件覆盖的备份会受 Linux protected_hardlinks 限制，旧同步写入也可能缺少写权限。停写后执行：

```bash
resource_path=$(realpath deploy-data/resource)
# 先检查；需要修复时退出非零，不写入数据
python3 scripts/prepare_backend_permissions.py --data-dir "$PWD/deploy-data" --resource-dir "$resource_path" --uid 1000 --gid 1000 --include-published
# 确认所有写入者停止后，限定于这些运行目录和正式文件修复；不改变内容
sudo python3 scripts/prepare_backend_permissions.py --data-dir "$PWD/deploy-data" --resource-dir "$resource_path" --uid 1000 --gid 1000 --include-published --repair --writers-stopped
```

TaskAssets 在已持久记录的提交日志之后、DB 写入 fence 之外准备旧文件备份。可用时仍使用硬链接；仅在 EPERM/EACCES/EXDEV/EOPNOTSUPP 时尝试不跟随链接的有界分块复制，期间检查控制和归属，验证完整 checksum 后才发布。临时复制不充当有效备份；原文件在备份校验通过前不替换。无法读旧文件、磁盘/目录权限错误等仍显式失败，不改成 root 服务或关闭内核保护。

`POSTGRES_PASSWORD_FILE` 不在修复范围，须自行保证所选 UID 能读取，保留凭证文件最小权限。配置在其他路径或自定义写入目录时也需单独核对，不让此脚本猜测范围。

`.tasks` 残留不生成任务，任务来自 DB；删缓存不等于取消。paused 的工作区保留；succeeded/failed/cancelled 且 writer 退出证明成立后才清理，权限失败显示 cleanup_state=failed，由 worker 恢复 Loop 重试。所有 worker 停止时不执行自动重试。取消卡在 RECOVERY_UNCONFIRMED 时，核实旧实例及后代退出后使用上文 `recover_tasks --confirm-stopped-attempt ... --all-writers-stopped`；该命令保留 generation/fencing，只处理指定旧 attempt，不能用手动删除或清空 Redis 绕过。

## 资源文件锁的写入权限

发布和删除共同使用 `COVER_DIR` 父目录下的 `.nassav-delete-locks/{AVID}.lock`。API、scrape/download worker 必须共享同一路径，并能创建和打开锁文件。容器以 root 写入宿主机资源卷后切回本机用户运行时，可能遗留 root 属主的 `755` 锁目录或 `644` 锁文件，导致 PermissionError。此时删除返回 `failed_stage: lock`，没有执行文件或数据库删除。

先使用 `id`、`stat` 核对实际服务用户和锁目录/锁文件属主。若所有 API/worker 都使用同一宿主机 UID/GID，只修复该锁目录和其中普通 `.lock` 文件的属主；例如本机服务 UID/GID 为 1000:1000 时：

```bash
# 替换为实例中 COVER_DIR 的父目录；先核实路径、服务身份及其中没有符号链接。
lock_dir=/home/florenz/NASSAV/django_backend/resource/.nassav-delete-locks
sudo chown 1000:1000 "$lock_dir"
sudo find "$lock_dir" -maxdepth 1 -type f -name '*.lock' -exec chown 1000:1000 {} +
```

锁文件目前不自动删除；操作结束释放 flock、进程退出也释放锁，文件存在不代表占锁。需要回收时只能在所有相关写入进程完全停止后另行维护。不要在服务运行时删除锁文件或替换锁目录：其他进程可能持有旧 inode 上的锁，重建文件会破坏互斥。也不要递归修改整个资源目录或设置 `777`。多用户/容器并行写入应统一运行身份，或预先配置共享组和目录/文件写权限；避免再次由不同身份创建不可写的锁。修复后先验证取锁，再手动重试原请求，不能用真实资源删除作为权限探针。

## 持久抓取缓存版本切换

更新缓存消费者前备份数据库、暂停旧 API/worker 消费，执行 `uv run python manage.py migrate` 应用 0027，再一致更新 API、scrape/download worker 和 Beat。缓存初始为空，首次仍冷抓取；不回填旧元数据或 m3u8。容器 config/config.yaml 可省略 ResourceCache 块使用默认值，或按 Compose 配置样例补充并重启。只有 Beat 运行时才自动有界清理；`provider_cache` 默认只预览。目标 PostgreSQL、真实站点热缓存收益与暂停恢复仍需部署验收，详见[缓存架构](resource-cache-architecture.md)。

## 表名规范化迁移 0028

本次切换需要维护窗口：旧版消费者仍查询旧表名，不能与迁移后的新版混跑。正式执行前保留旧镜像标签与 0027 数据库备份，核对当前数据库引擎、schema、已应用迁移以及 14 个目标表名均未占用。正常入口统一使用 scripts/compose_stack.py 对应的数据库模式与 Compose 文件，勿误用默认 SQLite 栈。

1. 禁止新写入与任务提交，停止 Beat 派发；按任务控制协议暂停/结束当前执行，确认写入者退出，再停止 API 和全部 worker（含恢复线程）。保留暂停工作区及队列，不删除锁/任务私有文件。
2. 使用当前引擎备份数据库并验证可恢复；PostgreSQL 使用 custom-format 备份。把配置、数据库模式声明和镜像版本与备份一并记录。不要用宿主机默认 SQLite 文件代替实际 PostgreSQL 数据库。
3. 用准备好的新版后端一次性容器审阅 `python manage.py migrate --plan` 与 `python manage.py sqlmigrate nassav 0028`，确认仅 14 次表重命名。设置有限 lock_timeout，若等待现存连接超时则保留停止状态并排查，不绕过锁或混跑旧服务。
4. 在同一配置/secret/schema 下执行迁移（PostgreSQL 可使用下方同连接限时入口）。核对目标表存在、旧表消失、业务行数、主键、多对多关联、索引及约束，并确认迁移记录到 0028。
5. 同步启动新版 API、scrape/download/default worker 与 Beat，验收资源列表/详情、演员/类别关联、任务查询与控制、推荐历史/反馈及缓存统计。仅迁移数据库不能替代代码部署。

若需回退，先停止新版写入者，用含该迁移的新版代码执行 `python manage.py migrate nassav 0027`，确认旧表恢复后再启动旧镜像。回退表名不会撤销上线后的业务写入；恢复整个备份仅在数据回退方案明确时执行。若数据库已经存在 0028 以后的迁移，先审阅回退计划，不能直接照抄此命令。

当前自动化验证使用合成数据和隔离实例；正式迁移及维护窗口需要单独确认与记录。

PostgreSQL 一次性迁移进程可在同一连接设置 5 秒锁等待上限，保留配置中的 search_path；锁等待超时则退出并由原子迁移回滚，不启动消费者：

```bash
python manage.py shell -c "from django.db import connection; from django.core.management import call_command; connection.cursor().execute(\"SET lock_timeout = '5s'\"); call_command('migrate', 'nassav', '0028')"
```

此入口仅用于 PostgreSQL；SQLite 使用普通 migrate 命令。该会话设置只作用于此次进程，不更改数据库或角色的全局配置。

## 当前发布准备

当前制品版本2.5.3，迁移叶节点0051；从2.5.1升级核查0037–0051及旧资源、角色、凭证和推荐归属，不能只改版本字符串。维护窗口、备份、全部消费者更新与回退见[v2.5.3发布检查](release-2.5.3.md)和[切换手册](multi-user-cutover.md)。本轮只准备制品，不执行正式迁移、部署或远端发布。下方早期验证记录明确保留日期，不作为当前实例状态。

## 近期改动与验证边界

以下为截至 2026-10-08、`e854e7d` 的实现与已有执行记录，不表示本次文档修订重新运行全部测试或部署。历史 validation-status 与早期设计文档已移除，旧版本证据可从 Git 历史查看；当前契约以任务、推荐、缓存架构和数据库文档为准。

| 范围                    | 提交与已有验证                                                                                                                                                          | 尚未证明的范围                                                     |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 共享事实/播放缓存 P1–P5 | `7e80f14`、`6799434`、`cbf52a7`、`dd02b58`、`bc1d654`；最终后端隔离 831 passed / 28 skipped；缓存迁移 SQLite 升级/回退通过                                              | 真实站点冷/热延迟、链接有效期、跨 worker 容量与缓存清理运行效果    |
| 外部搜索缓存            | `708d689`、`ae7ca7a`；后端隔离 852 passed / 28 skipped，覆盖 TTL、强制刷新、取消竞争、成功发布与库存重算                                                                | 目标 Redis 配置、真实搜索命中收益和部署后时效观察                  |
| MissAV 播放列表         | `df50905`；专项 32 项、后端隔离 858 passed / 28 skipped；容器内临时加载补丁，对 ADN-495 只读验证实际 Referer + 全局代理可取得有效 HLS，未保存资源                       | 全部站点/资源、实际下载及新版镜像发布；单样本不替代正式刮削验收    |
| 外部添加与推荐 UI       | `50dab8b`、`b4970cc`；前端 check 72 项通过、后端恢复专项 12 项通过；模拟浏览器覆盖保存/失败重试、分页及布局                                                             | 真实 API/worker 联调；执行器告警仅补充诊断说明，未新增自动恢复逻辑 |
| 表名规范化              | `e854e7d`；后端隔离 860 passed / 28 skipped；SQLite 与临时 PostgreSQL 17 nassav schema 各 2 项通过，覆盖 0027→0028→0027→0028、字段/关系/索引/约束；SQL 仅 14 次表重命名 | 正式 0028、业务流恢复、备份恢复演练与切换后的长期运行              |

上述实现阶段根目录 `pre-commit run -a` 均通过；跳过项为显式在线等 opt-in 范围，不代表目标环境已经验收。前端浏览器使用模拟 API/WS，后端隔离设置使用网络替身和临时数据；迁移专项 PostgreSQL 使用一次性独立实例。用户此前确认任务/资产权限和推荐可用，不扩大为本表中新功能的部署验收。

2026-10-08历史只读核查观察到活动 PostgreSQL 的 nassav schema 已应用至 0027、尚未应用 0028；agent 没有执行正式迁移或更新服务。新安装使用完整迁移链；已有实例先核对 showmigrations，再按本文 0027 缓存切换与 0028 表名维护窗口处理，统一 API、全部 worker 与 Beat 的代码/配置版本。旧表名消费者不得混跑，回退先停新消费者，再使用新代码逆向迁移，最后切回旧镜像。备份恢复、真实暂停续传、另一设备 HTTPS/WSS 与高并发性能仍需独立验收。

## 在线播放（默认关闭）

P1–P4及本地播放/个人进度已实现0029–0032迁移、Nginx媒体路径、独立播放页与一次有界兼容刷新；最新职责见播放及进度架构。启用须统一 API/worker/Nginx、先迁移后打开开关，并审核 CDN 域名和代理目标安全策略；Proxy.url 模式须核查实际 DNS/CONNECT ACL 后设置 NASSAV_PLAYBACK_PROXY_TARGETS_TRUSTED。详见[在线播放架构](online-playback-architecture.md#配置与部署)。本轮未执行正式数据库或容器切换。

MissAV 媒体修复需重新构建并创建 API 容器（curl_worker 随代码打包，不安装额外 curl CLI），控制接口和数据库结构不变。每在途媒体请求有独立可终止进程，应观察总 RSS 与启动开销后调整 NASSAV_PLAYBACK_MAX_MEDIA_REQUESTS；现有代理目标可信声明仍必需。开发时临时候选模块的成功不能当作运行服务已更新。

P3/P4 更新与回滚、Compose 短时实测及真实设备/长时发布条件见[在线播放验收](release-2.5.3.md#验证边界)。新旧会话协议不要混跑：先关闭在线播放入口、撤销旧会话并统一消费者，应用至0032后再开放受控验收。前端、API 与媒体均通过同源 HTTPS 网关，勿仅部署播放器或仅更新 worker。

## 个人状态与JSON设置（0033–0034，v2.5.1）

收藏、观看、备注与六项通用偏好改为用户数据库状态，升级须备份旧数据库/INI、停止所有旧写入者、应用0033和0034并统一API/worker/前端版本，然后用新版一次性API容器显式导入原操作者数据。导入默认只读预览，加apply后写入；不覆盖已编辑的个人数据、源INI保持只读。实例尚未导入时会显示默认个人状态，勿当作原数据被删除。完整参数、相同数据库模式的Compose入口与回退数据损失见[个人状态与设置](personal-state-architecture.md)。本轮只在隔离数据库验证，未修改正式实例。

0034会将当前数据库已有个人设置搬入JSON，并删除旧六列和导入时间列，增加创建时间；不要让0033版本消费者与新版本混跑。原INI仍仅通过显式命令导入缺失的设置行，不能因为增加JSON列就省略未完成的旧数据归属导入。详见[0034升级/回退](personal-state-architecture.md#json设置与0034当前实现)。

## v2.5.1个人推荐与跨设备接续

当前新增迁移为0035推荐归属；播放设置继续使用用户JSON，跨设备使用既有0032进度。部署前备份并停止旧API/scrape worker/Beat的写入，统一升级后迁移；迁移取消旧活动推荐job，不允许混跑旧全局历史消费者。旧共享推荐历史、反馈和三类黑名单保留NULL owner不可见，在首次个人推荐前运行import_recommendation_data预览并明确导入原操作者。已有个人推荐数据时拒绝自动合并，回退重复身份保护见[推荐架构](recommendation-architecture.md#用户归属第三阶段)。

本轮未开放多账号准入或普通用户共享资产控制，仍使用is_operator；跨设备为同账号的不同登录共享进度，各播放会话仍分别鉴权。音量/倍速/默认模式为用户设置，不替代服务器代理、容量、播放开关或Cookie配置。正式数据迁移、真实外站worker和实体设备验收由部署者单独执行，隔离浏览器测试不等同目标部署验收。

v2.5.1还须应用0036观看列表及播放事件去重字段；历史不从旧进度回填。移出已观看/历史删除的新接口与个人中心前端需统一更新。正式启动前先完成import_personal_data及适用的import_recommendation_data归属导入，再进行个人推荐；原有个人数据存在时不要强行重导入。维护窗口与0033–0036回退边界见[发布检查](release-2.5.3.md)。

## 共享执行器开关

Compose全部后端继承`NASSAV_SCOPED_SOURCE_CREDENTIALS`、`NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE`及`NASSAV_SHARED_LIBRARY_ENABLED`。开关默认false；共享执行器要求范围凭证，HTTP/配额/正式版本读取/GC已分阶段接入，但正式目标切换仍待P8，保持关闭。密钥路径为容器内路径（例如`/app/config/source-keys.json`，配置目录已挂载），文件只允许服务UID读取，先完成密钥备份、迁移/显式导入及全消费者维护窗口，不混跑旧Cookie/资产写入者。此配置接入不代表现有实例已迁移或允许普通账号登录。

多用户准入另由全部后端继承的NASSAV_MULTI_USER_ENABLED控制，默认false且依赖上述两模式。必须同步发布包含X-NASSAV-Context与WS subprotocol的新前端，先在operator范围核验，再在目标门槛通过后逐步开放；不要让旧浏览器/消费者继续提交无上下文命令。多用户模式使用应用管理中心，Django内置后台关闭，详见[准入架构](multi-user-admission-architecture.md)。本轮未修改部署开关或生产数据库。

## 独立来源 keyring 挂载

宿主机绝对路径不会自动出现在容器内。原配置目录方案继续有效：把已有 keyring 放在挂载的 config 目录内，`NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE` 填对应容器路径。若原 keyring 保存在仓库外或 `secrets/`，优先采用独立只读文件绑定，避免复制、重新生成密钥或挂载整个秘密目录。

在根 `.env` 设置 `NASSAV_SOURCE_CREDENTIAL_KEYRING_HOST_FILE` 为**已有**文件的宿主机绝对路径（例如 `/home/florenz/NASSAV/secrets/source-credentials.json`）。在仓库根目录执行：

```bash
# PostgreSQL；SQLite 部署仅将 --mode 改为 sqlite
python3 scripts/compose_stack.py --mode postgres --credentials config --quiet
python3 scripts/compose_stack.py --mode postgres --credentials up -d --no-deps --force-recreate api scrape-worker download-worker default-worker
```

`--credentials` 追加 `compose.credentials.yaml`，为 API、三个 worker、migrate、beat 和 ollama-model 统一绑定文件到 `/run/nassav/source-credentials.json`，并覆盖容器内 keyring 环境变量。绑定只读、禁止自动创建宿主机路径，不主动启用任何业务开关；后续部署/运维命令继续带该参数。直接使用 Docker Compose 时，在原数据库/GPU文件之外追加 `-f compose.credentials.yaml`，不要只运行基础 SQLite 栈。

显式指定文件重建的 PostgreSQL 部署，命令应保留全部覆盖文件：

```bash
docker compose -f compose.yaml -f compose.postgres.yaml -f compose.credentials.yaml up -d --build
```

若日常使用不带 `-f` 的 `docker compose up -d --build`，需把完整文件集合持久化在根 `.env`，避免下次重建丢失 keyring 挂载（Linux 示例）：

```dotenv
COMPOSE_FILE=compose.yaml:compose.postgres.yaml:compose.credentials.yaml
NASSAV_SOURCE_CREDENTIAL_KEYRING_HOST_FILE=/absolute/path/to/existing/source-credentials.json
NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE=/run/nassav/source-credentials.json
```

SQLite 去掉 `compose.postgres.yaml`；已有 GPU 覆盖文件也须保留。`COMPOSE_FILE` 只影响没有显式 `-f` 的原生 Compose 命令；显式 `-f`、以及自行拼接文件集合的 `compose_stack.py` 仍必须携带凭证覆盖文件或 `--credentials`，不能假定该变量会追加到显式文件后。不要在镜像中复制 keyring，也不要将容器路径填写为宿主机相对路径。`docker compose config --quiet` 只校验；完整 `config` 输出可能包含环境变量秘密，不要粘贴日志。

播放提交同样在创建会话前读取 keyring。若 `/resources/{avid}/playback-sessions` 返回503，先区分响应中的凭证加载错误与媒体准备/容量错误；在服务UID下调用 `build_credential_records()`、对本人资源调用 `build_playback_source_binding()` 可只读核查，不创建播放会话，不触发来源网络，输出仅限成功/失败与安全错误类别。缺失挂载时容器的 `/healthz` 仍可能健康，不能据此判断来源凭证可用。重建前核对活动任务/播放并保留现有视频路径，重建后对全部API/worker核查只读绑定、原密钥加载及当前凭证解密。

渲染预检验证来源凭证启用时的容器路径、宿主机文件存在/私有权限、全消费者绑定一致性；未启用时不要求 keyring。Unix 文件应为0600或更严格且服务 UID 可读取；重建前核对活动任务/播放及维护窗口，统一重建全部消费者。`restart` 不会应用新增挂载或环境变量，已有数据库密文必须继续使用原 keyring及历史密钥。

故障定位：`Credential keyring cannot be loaded` 可能是路径不存在、无法读取或结构不合法；权限过宽另报 `must be private`。先在容器服务UID下调用加载器验证，不输出文件内容，不能通过放宽权限、退回 SECRET_KEY 或生成新密钥掩盖问题。当前实例已只读复现宿主机路径未挂载，并用临时同UID容器验证原 keyring 可加载；这不等于运行服务已应用挂载，也不代表重新刮削已完成。修复分支 `fix/compose-keyring-mount` 执行部署入口 pytest、全量隔离 pytest 和 `pre-commit run -a`，无数据库迁移。

2026-10-16再次复现：原生重建仅携带基础/PostgreSQL文件，四个容器丢失独立绑定，播放创建在 `build_playback_source_binding` 报凭证加载失败并返回503。本轮将宿主机/容器keyring路径分别持久化到部署 `.env`，保留当前视频路径，四消费者使用原镜像和完整文件集合统一重建；四服务加载原密钥、解密已有active凭证及YUJ-062本人播放来源绑定只读检查通过。此前核对活动任务/播放均为0。此记录不代表真实播放出画验收；后续显式 `-f` 命令仍必须保留凭证覆盖文件。分支 `fix/persist-credential-compose-config` 更新配置示例/部署说明并执行全量 `pre-commit run -a`，无后端代码或数据库变更。
