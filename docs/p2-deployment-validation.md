# P2 部署模式与任务启动隔离验证

日期：2026-09-28。分支：`fix/p2-deployment-mode-and-workers`。状态：待验收。验证仅使用 `/tmp/nassav-p2-*` 的独立目录、虚构密码与隔离 Compose 项目；没有连接、导入或切换现有开发库和生产库。PostgreSQL 验证服务由临时覆盖文件提供，不属于正式部署文件；正式覆盖文件仍只连接外部 PostgreSQL。

## 模式入口与静态配置

- 基础 `compose.yaml`：后端服务统一设置 `DB_ENGINE=sqlite`（默认）和 `NASSAV_COMPOSE_DB_MODE=sqlite`，并共享配置、数据库、资源、备份、日志与 Beat 目录。仅在基础模式误传 `DB_ENGINE=postgres` 时，Django 在连接前报模式冲突；`.env.example` 不再暗示修改 `DB_ENGINE` 即可切换容器数据库。
- 添加 `compose.postgres.yaml`：`migrate`、API、三个 worker 和 Beat 统一覆盖 PostgreSQL 引擎、目标主机、库名、用户、schema 与同一 secret 路径。模式标记改为 `postgres`。密码缺失或数据库不可达时失败，不回退 SQLite。
- 两种模式的 `docker compose config --quiet` 均通过。逐服务解析 `config --format json`，确认六个后端服务的引擎及数据库地址一致；`migrate` 成功是 API/worker/Beat 的启动前置条件，队列分别为 `default`、`scrape`、`download`，前端仅绑定 `127.0.0.1`。

## 隔离运行结果

| 模式       | 数据库与启动顺序                                                                                                  | API/前端                                                                              | 三个队列与 Beat                                                                                                   |
| ---------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| SQLite     | 独立目录中的 `/app/data/db/db.sqlite3`；Redis 健康后 `migrate` 退出码 0，之后启动 API/worker/Beat                 | API 和前端健康；API 实际连接 SQLite，`SELECT 1` 成功                                  | `active_queues` 显示三个独立消费者；向每个队列投递无业务副作用的 `celery.accumulate`，均返回对应队列名；Beat 运行 |
| PostgreSQL | 临时 PostgreSQL 17 容器，隔离库 `nassav_p2` / `public`；数据库健康后 `migrate` 退出码 0，之后启动 API/worker/Beat | API 和前端健康；`current_database()` / `current_schema()` 返回 `nassav_p2` / `public` | 三个队列的 `celery.accumulate` 均返回对应队列名；Beat 运行                                                        |

两套栈的 `migrate`、API、三个 worker 和 Beat 容器环境均逐项核对。PostgreSQL 失败场景另用 `--network none` 的临时容器验证：缺少密码在读取配置时失败；提供虚构密码但连接不可达时失败；均没有创建预设的 SQLite 回退文件。`tests/test_database_configuration.py` 对模式冲突与连接失败增加隔离子进程回归。

## 自动化检查

- `DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p2-fullpytest.sqlite3 NASSAV_CONFIG_PATH=config/template-config.yaml uv run pytest tests/ -v`：**290 通过、13 跳过**。跳过项保持未覆盖状态，测试库与目录均为隔离资源。
- `pre-commit run -a`：格式、Markdown/YAML、ruff、pyright、编译、前端构建与 lint 均通过。
- 两种模式的 `docker compose config --quiet` 和逐服务脱敏配置检查均通过。容器镜像使用单独的 `p2-validation` 标签构建；验证后已关闭两套栈。

## 执行入口、限制与回滚

基础模式：`docker compose -f compose.yaml -p nassav-p2-sqlite --profile scheduler up -d --no-build`。PostgreSQL 模式在此基础上添加 `-f compose.postgres.yaml` 和仅供测试的临时覆盖文件，使用单独项目名与数据目录。实际执行先用隔离标签构建镜像，再分别启动，结束后运行对应的 `down`；没有共享 SQLite、Redis 或资源目录。

真实外部 PostgreSQL 的连接、真实刮削/下载任务、Beat 定时触发与正式数据库迁移均未在本阶段执行。队列验证使用 Celery 内置任务，只证明三个消费者能接收和返回任务。已存在的本机 PostgreSQL 开发库及生产数据未改动。回滚代码时撤销 P2 提交；运行环境回滚须停止新栈并按[独立迁移计划](../django_backend/doc/postgresql-migration-plan.md)恢复原配置和数据，不能将两套写入者同时连接同一数据库。
