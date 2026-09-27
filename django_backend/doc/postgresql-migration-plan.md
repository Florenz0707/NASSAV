# SQLite 迁移到 PostgreSQL 执行计划

日期：2026-09-27。状态：实施中（P1 代码配置已实现；P0 活动数据库源确认及真实数据演练/切换待操作方确认）。本计划只定义实施、演练、切换和回滚步骤；尚未更改运行数据库或迁移任何数据。当前应用已通过根目录 `compose.yaml` 编排，SQLite 与 Redis、API、三个 Celery worker 及可选 Beat 一起运行。[现有部署说明](compose-deployment.md)

## 目标与已确认基线

目标是在保留资源、推荐、Cookie、用户设置和现有任务行为的前提下，将 Django 的唯一业务数据库从 SQLite 切到 PostgreSQL。Redis 继续承担 Celery broker/result、缓存和 Channels，不和 PostgreSQL 合并。封面、视频、配置及备份文件仍保存在既有数据目录，迁移数据库不搬动这些文件。

2026-09-27 只读盘点：`django_backend/db.sqlite3` 约 10.7 MB，24 张业务及 Django 表，`PRAGMA quick_check` 返回 `ok`；其中资源 741 条、演员 209 条、类别 156 条、推荐条目 983 条、推荐 seed 911 条、AVID 屏蔽 353 条、Cookie 2 条。这是**宿主机数据库**的观察值；Compose 当前指向 `deploy-data/db/db.sqlite3`，它可能是另一份数据。实施 P0 必须确定实际运行的库，并从该库重新生成基线，不能用上述数字作为目标环境验收值。

当前 Django 为 6.0，`settings.py` 仅配置 SQLite `DATABASE_PATH`、WAL 和超时；后端依赖没有 PostgreSQL 驱动。现有 `backup_database` 管理命令执行 SQLite `PRAGMA wal_checkpoint` 并复制数据库/WAL/SHM，Beat 每日调用它，`sync_backups` 再同步 `backup/`。这些路径随数据库切换一起调整。[Django 6.0 PostgreSQL 支持与驱动要求](https://docs.djangoproject.com/en/6.0/ref/databases/#postgresql-notes)

## 决策和边界

- 初始选 PostgreSQL 17 的固定主版本镜像；实施时在目标架构上核对镜像 digest 并固定，测试环境与正式环境使用相同主版本。Django 6.0 支持 PostgreSQL 14 及以上，优先采用 psycopg 3。具体补丁版本和 digest 在实施记录中填写。[Django 数据库文档](https://docs.djangoproject.com/en/6.0/ref/databases/#postgresql-notes)
- 首轮保留单数据库、单应用账号及现有 Django ORM 模型。不同时更换 Redis、前端、Byparr、资源目录或推荐算法；暂不引入 PgBouncer、主从复制和新的 PostgreSQL 专属索引。
- 数据迁移使用 Django 序列化数据加空库 `migrate`：它能跨 SQLite/PostgreSQL 处理模型字段与关联。`pg_dump` **只用于切换后 PostgreSQL 的备份**，不能直接把 SQLite 文件交给 `pg_restore`。[Django 数据导出/导入命令](https://docs.djangoproject.com/en/6.0/ref/django-admin/#dumpdata)、[PostgreSQL 备份格式](https://www.postgresql.org/docs/17/app-pgdump.html)
- 正式切换采用短暂停写，不做双写。P0 测得导出/导入耗时后再确定维护窗口。旧 SQLite 在观察期保持只读可恢复，不因切换成功立即删除。
- 不把本次数据库更换与新 schema 设计捆绑；仅在 PostgreSQL 上运行现有 migration。如果 migration 确实不兼容，先补一项跨数据库兼容修复并在两种引擎上测试，再进行数据切换。

## 阶段与放行条件

| 阶段              | 实施内容                                                                          | 放行条件                                                     |
| ----------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| P0 基线与源确认   | 找出实际运行 SQLite、记录表行数/关联数/最大主键、迁移状态、资源文件数量及备份位置 | 确认只有一份活动数据源、无已知损坏，维护窗口足够覆盖演练耗时 |
| P1 代码与隔离环境 | PostgreSQL 可选配置、psycopg、Compose 数据库服务、备份命令和测试                  | 两种数据库配置均能 `check`、`migrate`；备份/恢复独立验证     |
| P2 完整演练       | 将活动库的副本导入隔离 PostgreSQL，跑数据核对和业务回归                           | 所有关键表及关联匹配，新增数据不会撞主键，问题清单清零       |
| P3 停写切换       | 停 API/worker/Beat 写入、源库一致备份、最终导出、目标导入、验收、统一改连接       | 源与目标基线一致，全部进程显示 PostgreSQL 后才开放写入       |
| P4 观察与收尾     | 监测写入、备份、恢复、查询表现；更新文档和回滚记录                                | 一个完整备份周期及业务回归通过，旧 SQLite 按保留策略归档     |

### P0：确认源、风险和基线

1. 核对 `compose.yaml` 中 `DATABASE_PATH=/app/data/db/db.sqlite3` 对应的宿主机 `NASSAV_DATA_DIR`；分别检查宿主机、Compose 和任何旧进程的数据库路径。确认 API、三个 worker、Beat 的实际配置相同，并确认是否有旧宿主机定时任务仍在写入。
2. 以**活动数据库**为准记录 Django/迁移版本、每表行数、主键最大值、关键唯一列及关联表数量。至少包含 `AVResource`、Actor/Genre、M2M、SourceCookie、推荐快照/条目/seed/反馈/屏蔽/画像，以及 Django `auth`、`contenttypes`、`sessions` 和迁移记录。导出核对报告不得包含 Cookie 明文、用户凭证或资源元数据全文。
3. 核查空值、重复值与跨表引用。PostgreSQL 比 SQLite 更严格地执行数据类型和约束；尤其检查字符串长度、日期/时区、JSON 字段、唯一约束及空字符串/NULL 差异。ORM 的 `contains`/`icontains` 与排序在两个引擎上可能表现不同，按搜索、推荐和分页结果写回归样本。
4. 记录当前备份的可恢复性、实际 SQLite 数据大小和导出时间；评估包含 `SourceCookie` 的导出文件权限、磁盘空间和维护窗口。不要让导出的含凭证 fixture 进入 Git、普通日志或不受保护的共享目录。
5. 为当前运行中的刮削、下载、翻译和定时任务制定“停新任务、等在途完成”的具体步骤；不能只停止 API 而让 worker 和 Beat 继续写 SQLite。

### P1：代码、配置、Compose 和备份

- 在 `django_backend/pyproject.toml` 加入 psycopg 3 运行依赖并更新 `uv.lock`、镜像；在 `settings.py` 新增明确的 `DB_ENGINE=sqlite|postgres` 分支。PostgreSQL 配置使用 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER` 和独立的密码来源；SQLite 保留 `DATABASE_PATH` 供本地开发和回滚。WAL/`PRAGMA`/SQLite `timeout` 只属于 SQLite 分支，不传给 psycopg。错误或缺失的 PostgreSQL 配置应在启动时失败，不静默回退到 SQLite。
- 为根 Compose 加入 `postgres` 服务和持久化卷，固定镜像版本及 digest；仅内部网络可访问 5432。使用专用应用数据库与账号，密码放 Git 忽略的部署配置或 Compose secret。设置 `pg_isready` 健康检查，并让一次性 `migrate` 在数据库可连接后运行；健康检查不替代 schema/数据验证。API、scrape/download/default workers、Beat 和一次性命令必须使用同一数据库环境块。不要把 SQLite 卷移走或覆盖，直到回滚窗口结束。
- Compose 的数据库目录从 SQLite 文件卷切换为 PostgreSQL 数据卷。保留 `resource/`、`config/`、`backup/`、`backup_sync/`、`celery_beat/`、`redis/` 等现有卷语义；不要因更换数据库造成视频或封面丢失。已有 `NASSAV_DATA_DIR` 外部路径、前端网关和 Byparr 地址保持一致。
- 将 `backup_database` 改成按引擎选择适配器：SQLite 路径继续保持原行为，PostgreSQL 路径执行 `pg_dump -Fc` 并检查退出码、文件非空和可列出目录。PostgreSQL 备份文件以不同扩展名/元数据标识引擎及版本；不再向 PostgreSQL 执行 WAL checkpoint 或复制 `.sqlite3`。评估管理命令运行所在容器是否包含匹配版本的 PostgreSQL 客户端；可改成专用备份容器，但 Beat 调度与手工命令都要指向同一实现。[pg_dump 文档](https://www.postgresql.org/docs/17/app-pgdump.html)
- 调整 Beat 的每日数据库备份任务、`sync_backups` 的清理/同步规则、备份保留期和操作手册。迁移前后两种格式应能共存，清理不能误删仍需回滚的 SQLite 快照。PostgreSQL 恢复使用**全新空数据库**和 `pg_restore --exit-on-error`，至少做一次从备份恢复后读写验证。[pg_restore 文档](https://www.postgresql.org/docs/17/app-pgrestore.html)
- `django_backend/doc/database.md`、`doc/compose-deployment.md`、根 README、后端 README、`.env.example`、测试 README 与相关备份文档同步更新；部署文档明确 PostgreSQL 作为正式配置、SQLite 作为回滚/本地选项。

### P2：完整演练与导入方法

1. 用**停写后的 SQLite 副本**在隔离目录演练，或用 SQLite 官方备份机制生成一致快照；不要在写入中的 WAL 数据库上只复制主文件。演练所用数据不进入生产 PostgreSQL。记录导出、`migrate`、导入、校验和恢复各阶段耗时。
2. 空 PostgreSQL 库先运行 `python manage.py migrate --noinput`，完整覆盖全部历史迁移。特别检查 `nassav/migrations/0004_add_indexes.py` 的 `RunSQL` 与 `0018` 的 `RunPython`；新库迁移时不带源数据，避免历史回填与后续 fixture 导入互相重复。运行 `makemigrations --check --dry-run`，但不靠 `--fake` 跳过失败迁移。
3. 从 SQLite 按模型导出数据，保留显式主键；建议以 `manage.py dumpdata --all --natural-foreign --exclude contenttypes --exclude auth.permission --exclude sessions` 为起点，在演练中验证 Django 6.0 的实际命令输出。迁移生成的 `contenttypes` 和权限由目标 `migrate` 重建；会话默认不迁移，切换后现有会话失效。若存在实际用户、组、后台日志或会话需求，逐项确认包含范围，不直接删掉这些表。`django_migrations` 由目标迁移过程生成，不作为业务 fixture 导入。[Django dumpdata/loaddata](https://docs.djangoproject.com/en/6.0/ref/django-admin/#dumpdata)
4. 在已迁移的**空业务数据** PostgreSQL 上导入 fixture。不要先把生产目标库填入部分真实数据，再运行同一 fixture。导入失败清空并重建隔离库，修复数据或序列化问题后重演；不跳过异常行继续上线。
5. 显式核对整数主键序列：导入保留旧 PK 后，为相关 app 执行 `sqlsequencereset` 生成的 SQL，验证下一条插入不与现有 PK 冲突。Django 官方说明手工指定自增主键不会自动更新 PostgreSQL 序列。[Django 序列说明](https://docs.djangoproject.com/en/6.0/ref/databases/#manually-specifying-values-of-auto-incrementing-primary-keys)
6. 逐表比较行数；对资源、演员/类别、M2M、推荐关联和 Cookie 进行聚合/抽样核对。固定数个 AVID 做资源详情、搜索、分页、推荐、观看/收藏状态和 Cookie API 读写回归；在隔离库测试新增资源、刷新、下载状态写回与备份恢复。文件引用在既有资源目录中抽样检查，不需迁移视频内容。
7. 针对 PostgreSQL 再跑全量后端测试。测试账号须有创建测试数据库的权限，且测试库与生产库隔离；官方测试框架默认会创建独立数据库。[Django 测试数据库说明](https://docs.djangoproject.com/en/6.0/topics/testing/overview/#the-test-database)

### P3：正式停写与切换顺序

1. 预告维护窗口，在网关阻止新增写请求及异步任务提交；暂停唯一 Beat，等待 API 在途写入和三个 worker 队列执行完成。记录待处理任务 ID，确认没有旧宿主机进程继续写入。只读页面能否开放以维护窗口预案为准，不能让它间接触发缓存回填或数据库写入。
2. 完全停写后，对活动 SQLite 做一致快照：停相关进程后备份数据库文件及 WAL/SHM，或用 SQLite 备份 API；记录文件校验值、表行数和迁移版本。另备份 `resource/`、配置及已有 PostgreSQL 测试库之外的其他持久化数据。源库与保留副本都标记为只读。
3. 从这份**最终冻结快照**重新导出 fixture；不要用早先演练导出的旧 fixture。把目标生产 PostgreSQL 初始化为空库、运行同一代码版本的 `migrate`、导入、重置序列。迁移文件和模型版本须与导出阶段一致，禁止在切换中途引入额外 schema 变更。
4. 执行 P2 的数据核对及基础读写烟测。只在全部通过后调整所有 API/worker/Beat 连接，按数据库就绪→迁移任务完成→API→各 worker→Beat 的顺序启动。逐个进程确认连接的是 PostgreSQL；不要出现 API 写 PG、worker 写 SQLite 的混合状态。
5. 开放写入，先做单条资源添加/刷新、下载状态写回、推荐反馈、Cookie 更新与任务进度检查，再恢复正常任务负载。记录切换时间、首个新 PostgreSQL 写入 ID 和观察指标。

### P4：验收、备份与回滚

验收必须满足：迁移前后对应业务表行数一致；M2M/外键、关键唯一值、JSON 字段和抽样记录一致；主键序列能生成新 ID；`migrate --check` 没有未应用迁移；资源添加/刷新、下载状态、推荐反馈与 Cookie 更新成功；按新方案完成一次 `pg_dump` 及**独立空库恢复**。观察期间无持续数据库连接、锁等待、唯一约束或类型转换错误，并记录 PostgreSQL 内存/磁盘与查询延迟。

在首次 PostgreSQL 写入**之前**，若验收失败，可停目标进程、恢复原 SQLite 配置与原镜像/代码版本，重新启动原 API/worker/Beat。此时旧 SQLite 仍是切换点的完整数据。

首次 PostgreSQL 写入**之后**，直接切回冻结 SQLite 会丢失切换后的写入。回滚必须先停止所有新写入并选择：从 PostgreSQL 导出增量/整库恢复到新的 SQLite 副本，经核对后切回；或明确接受从切换点之后的数据丢失并记录影响范围。对于附件/视频文件，还须同步恢复与数据库状态一致的资源目录。无法验证反向迁移时，应优先修复 PostgreSQL 问题而非盲目切回。保留原 SQLite、最终 fixture 和首轮 PG 备份直到观察及回滚窗口结束。

### 测试和提交拆分

- 自动化：两种引擎的设置分支、缺失凭证失败、所有历史 migration 在空 PostgreSQL 的执行、fixture 导入与序列、自定义备份/同步/恢复、核心资源/推荐/Cookie 行为。SQLite 单元测试继续可用，但不能代表 PostgreSQL 兼容已通过。
- 必跑：相关测试、PostgreSQL 目标下 `cd django_backend && uv run pytest tests/ -v`、`python manage.py check`、`python manage.py makemigrations --check --dry-run`、根目录 `pre-commit run -a`。在线抓取、Ollama 与外部依赖测试如未启用，应列出未覆盖项，不能把跳过写成通过。
- 建议提交：`[Enhancement] Add PostgreSQL database configuration and Compose service`；`[Fix] Support PostgreSQL database backup and restore workflow`；`[Doc] Document SQLite to PostgreSQL cutover and validation`。切换本身单独记录操作时间、使用的镜像 digest、备份位置与验收结果，不包含凭证或 fixture 数据。

## 实施进度记录（2026-09-27）

- P1 代码配置：已加入显式 SQLite/PostgreSQL 设置分支、`psycopg`、外部 PostgreSQL Compose 覆盖文件和数据库凭证 secret 文件读取。PostgreSQL 服务由部署方在 Compose 外部管理；默认 Compose 仍使用 SQLite。Compose 覆盖不自动导入数据，但其一次性 `migrate` 服务会在后端启动前运行。
- 备份：已按引擎选择 SQLite 文件备份或 PostgreSQL custom-format `pg_dump`，校验归档可列出；新增仅针对空 PostgreSQL 数据库的 `restore_postgres_backup`。PG 模式的自动清理和同步保留 SQLite 回滚快照。
- 文档与自动化：已更新数据库、Compose、后端和根 README、备份说明及配置/保留策略测试。后端打包 PostgreSQL 17 客户端；PostgreSQL 服务由部署方在 Compose 外部管理。
- 尚未访问或修改任何真实数据库，未执行 `migrate`、数据导出/导入、Compose 启动或 P0 活动数据盘点。启动 PostgreSQL 覆盖配置前，操作方须提供可从容器访问的现有服务地址、数据库账号/密码文件，并确认源数据库与隔离目标库及测试权限。真实生产切换继续按 P0–P4 步骤另行放行。
