# P0 基线、访问模型与隔离回归样本

记录时间：2026-09-28 11:47 CST。分支：`chore/p0-baseline-and-regression`。本记录只核对配置、监听与只读连接，并在测试数据库和临时资源目录执行回归；未操作真实业务数据。

## 运行模式配置矩阵

来源：`django_project/settings.py`、`django_project/dev_commands.py`、`compose.yaml`、`compose.postgres.yaml`、`config/template-config.yaml`。Compose 两种模式以临时目录和虚构凭证渲染，包含 `scheduler` profile；表内结合 Compose 渲染结果与 Django 设置回退规则，不代表服务已启动。`-` 表示服务不监听网络端口。

| 模式            | 进程            | 数据库引擎与库/schema                                                    | Redis              | 监听或队列                                           | 凭证状态                       |
| --------------- | --------------- | ------------------------------------------------------------------------ | ------------------ | ---------------------------------------------------- | ------------------------------ |
| 本机开发模板    | API             | SQLite `django_backend/db.sqlite3`                                       | `localhost:6379/0` | 默认 `127.0.0.1:9790`                                | 数据库无需凭证                 |
| 本机开发模板    | scrape worker   | 同 API                                                                   | 同 API             | `scrape`，并发 1                                     | 同 API                         |
| 本机开发模板    | download worker | 同 API                                                                   | 同 API             | `download`，并发 1                                   | 同 API                         |
| 本机开发模板    | default worker  | 同 API                                                                   | 同 API             | `default`，并发 1                                    | 同 API                         |
| 本机开发模板    | Beat            | 同 API                                                                   | 同 API             | 无队列；本地 `nassav-beat` 写 `celery_beat/schedule` | 同 API                         |
| 默认 Compose    | API             | SQLite `/app/data/db/db.sqlite3`                                         | `redis:6379/0`     | 容器内 `0.0.0.0:9790`，无宿主机直出                  | 数据库无需凭证                 |
| 默认 Compose    | scrape worker   | 同 API                                                                   | 同 API             | `scrape`，并发 1                                     | 同 API                         |
| 默认 Compose    | download worker | 同 API                                                                   | 同 API             | `download`，并发 1                                   | 同 API                         |
| 默认 Compose    | default worker  | 同 API                                                                   | 同 API             | `default`，并发 1                                    | 同 API                         |
| 默认 Compose    | Beat            | 同 API                                                                   | 同 API             | 无队列；仅 `scheduler` profile 启动                  | 同 API                         |
| PostgreSQL 覆盖 | API             | PostgreSQL `${DB_NAME}` / `${DB_SCHEMA}`，未设置 schema 时由应用配置决定 | `redis:6379/0`     | 容器内 `0.0.0.0:9790`，无宿主机直出                  | 密码文件必需；虚构渲染中已配置 |
| PostgreSQL 覆盖 | scrape worker   | 同 API                                                                   | 同 API             | `scrape`，并发 1                                     | 同 API                         |
| PostgreSQL 覆盖 | download worker | 同 API                                                                   | 同 API             | `download`，并发 1                                   | 同 API                         |
| PostgreSQL 覆盖 | default worker  | 同 API                                                                   | 同 API             | `default`，并发 1                                    | 同 API                         |
| PostgreSQL 覆盖 | Beat            | 同 API                                                                   | 同 API             | 无队列；仅 `scheduler` profile 启动                  | 同 API                         |

两种 Compose 的前端均为容器内 `:80`，默认仅发布宿主机 `127.0.0.1:9780`；Redis、API 和 Worker 不发布宿主机端口。PostgreSQL 覆盖连接 Compose 外部数据库，实际主机和库名由部署环境提供。渲染核对了 `migrate`、API、三个 Worker 和 Beat 继承同一数据库环境；PostgreSQL 渲染样本使用 `host.docker.internal`、`nassav_p0`、`p0`，仅为验证环境变量传播，不代表真实部署。基础 Compose 未显式设置 `DB_ENGINE`，由应用配置决定；因此 `.env` 中的 `DB_ENGINE` 不能单独作为容器实际引擎的证据，此项留给 P2 处理。

### 实际运行观察

- 本机主检出目录 `/home/florenz/NASSAV/django_backend` 的**当前有效 Django 配置**为 PostgreSQL `dbb`、schema `nassav`，数据库主机 `127.0.0.1`，Redis `localhost:6379/0`，数据库凭证已配置。只读 `SELECT current_database(), current_schema()` 返回 `dbb` / `nassav`，证明该配置可以连接开发库；没有读取或记录密码。
- 11:47 CST 的监听快照：`127.0.0.1:5432`（PostgreSQL）、`127.0.0.1:6379`（Redis）、`127.0.0.1:9780`（前端）存在；`:9790`（API）未监听。先前对 `/healthz` 的请求超时，不能记作健康检查通过。API、三个 Worker、Beat 的**运行时数据库连接**未能在此快照核实；下次它们启动后需逐进程检查，不能用当前配置代替进程实测。
- `docker ps` 仅显示独立 Byparr 容器；没有发现默认或 PostgreSQL 覆盖的完整 NASSAV Compose 栈。因此两种 Compose 目前只有配置渲染结论，没有运行时数据库和队列实测。正式 PostgreSQL 切换仍以独立迁移计划为准。

## 目标访问模型

用户于 2026-09-28 选择“经反向代理远程访问，单用户登录”。P1 应建立单用户登录会话；Cookie、设置、资源增删改、推荐反馈/重置、任务状态及任务 WebSocket 共用身份边界。反向代理负责 HTTPS/WSS，后端仍须校验会话、CSRF 与 WebSocket Origin，并明确会话过期与重连行为；健康探针仅供内部就绪检查。默认 Compose 在 P1 验收前继续环回发布。当前 `REST_FRAMEWORK` 使用 `AllowAny` 且无默认认证类，`TaskConsumer.connect()` 直接加入全局任务组，敏感端点和任务事件尚未受到该目标访问模型保护。

## 隔离回归样本

后端测试以 `DB_ENGINE=sqlite`、临时 SQLite 测试库和无凭证模板运行。`test_p0_regression.py` 的删除样本将封面、视频、缩略图和备份根目录指向 pytest 临时目录；下载进度使用内存 Redis 替身；WebSocket 使用内存 Channel Layer；备份样本在子进程创建临时 SQLite 库和备份目录。Cookie 使用虚构值；不会调用真实外站或写入开发 PostgreSQL。

| 场景                | 自动化样本                                                                                                                                                              | 结果及边界                                                              |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Cookie 读取/修改    | `test_source_cookie_api.py`                                                                                                                                             | 隔离测试通过；P1 需改为登录权限回归                                     |
| 设置修改            | `test_user_settings.py`                                                                                                                                                 | 隔离临时 INI 测试通过                                                   |
| 资源删除            | `test_p0_regression.py::test_resource_delete_removes_only_isolated_files`                                                                                               | 隔离 SQLite 与文件目录通过                                              |
| 推荐重置            | `test_recommendations_demo.py::test_recommendation_reset_endpoint_clears_history_but_preserves_blocklist`                                                               | 隔离 SQLite 通过                                                        |
| 资源添加/刷新       | `test_scrape_jobs.py` 的提交/状态用例、`test_metadata_format.py::test_refresh_resource_preserves_existing_actor_relations_when_scrape_fails`、前端 `scrapeJobs.test.js` | 假队列与假源下通过；真实外站、Ollama 和真实 Worker 流转待在隔离部署验证 |
| 下载进度            | `test_p0_regression.py::test_download_progress_round_trip_uses_fake_redis`                                                                                              | 假 Redis 通过；真实下载器与 Worker 推送待在隔离部署验证                 |
| WebSocket 连接/重连 | `test_p0_regression.py::test_websocket_reconnect_receives_new_events`、`test_ws.py`                                                                                     | 内存通道通过；反向代理后的会话/Origin 行为待 P1 验证                    |
| 数据库备份          | `test_p0_regression.py::test_sqlite_backup_uses_disposable_database_and_directory`                                                                                      | 临时 SQLite 备份通过；PostgreSQL 备份与空库恢复待独立隔离库验证         |

回归入口见 `django_backend/tests/README.md`。本阶段首次全量后端测试出现两项环境相关失败：子进程测试继承外层 `NASSAV_CONFIG_PATH`，以及 Jable 直连测试依赖当前模板策略。测试已显式设置各自配置后重跑，结果为 **282 passed、13 skipped**；前端刮削状态测试 **5 passed**。13 项跳过不记作通过；具体原因以 pytest 的跳过报告为准。

## 验证命令与结果

- `docker compose -f compose.yaml --profile scheduler config --format json`：通过；使用临时数据目录、虚构 `SECRET_KEY`，仅输出脱敏后的引擎、库名/schema、Redis、端口和队列。
- `docker compose -f compose.yaml -f compose.postgres.yaml --profile scheduler config --format json`：通过；使用临时虚构密码文件、`host.docker.internal`、`nassav_p0` 和 `p0`。
- `DB_ENGINE=sqlite DATABASE_PATH=/tmp/nassav-p0-pytest.sqlite3 NASSAV_CONFIG_PATH=config/template-config.yaml uv run pytest tests/ -v`：282 通过、13 跳过；测试数据库由 pytest 隔离。初次失败两项，原因及修正见上节。
- `cd vue_frontend && node --test tests/scrapeJobs.test.js`：5 通过。
- `pre-commit run -a`：首轮格式钩子自动修正新文件，复跑通过。

## 模块职责与后续定位

| 模块                                       | 当前职责                                                   | P5 候选边界                                            |
| ------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------ |
| `nassav/views.py`                          | HTTP 参数、响应、资源文件删除、推荐与任务 API              | 视图保留校验和响应映射；文件操作与业务编排迁至应用服务 |
| `nassav/tasks.py`、`nassav/scrape_jobs.py` | Celery 路由任务、下载进度/去重锁、刮削状态快照与通知       | 调度/重试和业务执行分开，维持任务名及消息字段          |
| `nassav/resource_service.py`               | 资源添加/刷新/删除、源获取、刮削、封面、ORM 保存及翻译提交 | 应用编排与外部获取/持久化适配分开                      |
| `RecommendationsView.vue`                  | 推荐查询、参数、反馈/屏蔽/重置、页面状态及展示             | API/store 管数据变更，页面管交互与展示                 |
| `src/stores/resource.js`                   | 资源 API、批量提交、刮削快照合并/轮询、下载状态和 Toast    | 网络、任务状态与提示职责分开                           |

已定位的旧说明：根 README 的“启动 Celery Worker”与生产部署片段仍给出单 Worker 命令；`django_backend/doc/debug.md` 同样如此。根 README 的备份章节已有 PostgreSQL 描述，旧单 Worker 文案才是 P2 重点。历史文件 `origin_project/go_backend/main` 是被 Git 跟踪的 ELF 可执行文件；仓库其他目录（除本路线图）未发现构建或运行引用。P6 再决定移除或归档，不在 P0 删除。

## 验收状态与回滚

P0 交付物已形成，状态为**待验收**。尚未覆盖：运行中的 API/三个 Worker/Beat 对 PostgreSQL 的逐进程实测、两种 Compose 的启动验证、真实外站/下载/代理场景以及 PostgreSQL 备份恢复。前两项在服务可用或独立数据目录下复核；真实外站与 PostgreSQL 恢复分别在 P1/P2 和数据库迁移计划的隔离环境处理。当前提交只增加文档与测试，不改业务配置；回滚为撤销本分支提交。不得把本地开发库可连接误认为生产切换完成。
