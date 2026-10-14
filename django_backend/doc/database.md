# 数据库与迁移

未发布P3存储子阶段新增0040的SourceCredential/SourceSessionSnapshot；开发叶节点为0040，不自动导入旧Cookie、不切换消费者，详见[凭证架构](source-credential-architecture.md)。新增表逆向会丢失凭证/快照，回退前必须备份密钥及数据，不能将个人凭证压回一份全局Cookie。

未发布P2新增0038应用账号/管理fence/审计/幂等receipt/登录绑定/配额预留，以及0039资源可用性和播放读取grant；开发叶节点为0039。结构迁移不自动授权管理员、不开放普通账号，回退新增状态丢失边界见[账号策略](account-policy-architecture.md)。正式发布v2.5.1叶节点仍为0036；下方P1的0037是该阶段当时记录。

未发布P1新增0037：共享规范身份池与按用户持有关系，结构迁移不自动分配旧资源所有者。当前开发迁移叶节点为0037；v2.5.1发布叶节点仍为0036。新增表、显式导入及逆向迁移的数据损失边界见[共享池架构](resource-pool-architecture.md)。本轮只验证隔离SQLite/PostgreSQL数据库，未迁移部署实例。

v2.5.1迁移叶节点为0036；从2.5.0的0032补齐0033–0036个人状态、JSON设置、推荐归属及观看列表。0027–0032的缓存、表名及播放基础见历史发布指南。已有实例按实际showmigrations升级，不把下方历史验证记录当作当前部署。维护窗口与逆向迁移数据影响见[v2.5.1发布检查](release-2.5.1.md)。

SQLite 是本地和默认 Compose 数据库，由 `Database.Path` 或 `DATABASE_PATH` 指定，Compose 中的文件及 WAL/SHM 位于 `deploy-data/db/`。本地开发可在忽略的 `config/config.yaml` 中将 `Database.Engine` 设为 `postgres`，并配置 `Host`、`Port`、`Name`、`User`、`Schema` 及 `Password` 或 `PasswordFile`；环境变量可覆盖对应值。`Schema` 默认 `public`，需预先存在且应用账号需有权限；应用不会自动创建 schema。例如：

```yaml
Database:
  Engine: postgres
  Host: 127.0.0.1
  Port: 5432
  Schema: nassav_dev
  Name: nassav_dev
  User: nassav_dev
  Password: your-local-development-password
```

模板中的密码为空。缺少凭证或 engine 值错误时 Django 启动失败，不回退到 SQLite。Compose 基础文件显式选择 SQLite；添加 `compose.postgres.yaml` 后统一选择 PostgreSQL，并挂载密码 secret。仅修改 `.env` 中的 `DB_ENGINE` 会被模式检查拒绝。所有后端服务共享相同配置目录和数据库模式。数据库连接切换不修改模型；schema 由 `search_path` 选定。部署说明见[这里](compose-deployment.md)。

数据库字段、密码文件及环境变量的优先级见[启动配置契约](configuration-contract.md)。密码文件必须是容器可读取的普通文件。

`backup_database` 按当前引擎选择 SQLite 文件快照或 PostgreSQL custom-format `database.dump`。PostgreSQL 文件位于 `backup/database_postgresql_{timestamp}/`，带引擎和服务端主版本元数据。PostgreSQL 恢复命令 `restore_postgres_backup` 只接受空数据库；先创建新的空库，再在配置指向该库时执行恢复。备份目录会由 `sync_backups` 一并同步。使用 PostgreSQL 时自动清理只处理 PostgreSQL 备份，保留 SQLite 快照供回滚。

## 个人状态与JSON配置（0033–0034，v2.5.1）

0033新增 `nassav_user_resource_state` 和 `nassav_user_preferences`，用户状态与共享资源分离；0034将现有六项个人设置值搬入JSONField、删除旧六列及legacy_imported_at、增加created_at，保留用户归属和updated_at。旧数据归属通过指定原操作者的命令导入，迁移不自动猜测；升级、级联和回退影响见[个人状态与设置](personal-state-architecture.md)。v2.5.0的历史发布叶节点为0032，当前须升至0036。

## Database Overview

- **Scope:** 介绍与 `AVResource` 相关的数据库表、它们之间的关系、字段语义、索引、以及元数据/封面/视频的持久化和更新流程。

## Models & Tables

- **`SourceCookie` (`source_cookie`)**: 存储下载源的 Cookie 配置表。
  - 关键字段：
    - `source_name` (Char, unique, primary_key): 源名称，主键。
    - `cookie` (Text): Cookie 字符串。
    - `user_agent` (Text, nullable): 与 Cookie 配套的 User-Agent；旧记录为 `NULL`。
    - `expires_at` (DateTime, nullable): 会话声明的到期时间；未知不表示永不过期。
    - `egress_profile` (Char(64), nullable): 用服务端密钥对规范化代理路线（含代理身份要素）计算的 HMAC-SHA256；不是公网出口 IP 证明。未知路线为 `NULL`。
    - `updated_at` (DateTime, auto_now): 整组会话的写入版本。

迁移 `0021_sourcecookie_session_metadata` 只增加三个可空列，旧行数量及 Cookie 内容不变；可回退到上一迁移。`SourceCookieRepository` 把 Cookie、UA、到期时间、路线标识和版本作为同一快照传入 Django 共享缓存与进程缓存。读取共享缓存前核对数据库版本，避免迟到的旧缓存遮蔽新值。浏览器会话写入使用短事务锁行并比较 `updated_at`；人工设置、清除或较新的刷新发生后，较早启动的浏览器结果不写回。人工设置不带 UA 时清空历史 UA、到期时间和路线标识；清除 Cookie 时同样清空元数据。未知路线的自动会话不写入，已过期或路线不匹配的快照不会用于页面直连。旧行继续携带原 Cookie 和默认 UA 进行有限直连；P2 已接入详情、列表和搜索页面的浏览器会话提取与短直连验证；P3 已加入跨 API/worker 的站点级 Redis 刷新租约；人工写入仍不等待该锁，旧自动 Cookie 写入也会检查启动时版本和租约持有权。

- **`AVResource` (`nassav_av_resource`)**: 主表，保存 AV 元数据（除封面与视频文件外的所有字段）。
  - 关键字段：
    - `avid` (Char, unique, db_index): AV 编号，主查找键。
    - `original_title` (Char, db_index): Scraper 获取的原始标题（通常为日语，来自 Javbus）。
    - `source_title` (Char, nullable): Source 获取的标题（备用，来自 MissAV/Jable 等）。
    - `translated_title` (Char, nullable, max length 1024): 翻译后的标题（中文，由 Ollama 翻译）。
    - `translation_status` (Char, db_index): 翻译状态，可选值：pending（待翻译）、translating（翻译中）、completed（已完成）、failed（翻译失败）、skipped（跳过）。
    - `source` (Char, db_index): 抓取来源/Downloader 名称。
    - `release_date` (Char, db_index): 原始发布日期字符串。
    - `duration` (Integer, nullable): 时长（以秒为单位）。注意：爬取数据常为 "150分钟" 字符串，入库时解析为秒；若 mp4 文件存在，则优先使用 `ffprobe` 返回的实际秒数。
    - `metadata` (JSONField, nullable): 原始/完整的爬取 JSON，作为审计与补偿数据源。
    - `m3u8` (Text, nullable): 下载使用的 M3U8 URL（若有）。
    - `cover_filename` (Char, nullable): 相对于 `resource/{avid}/` 的封面文件名（仍把文件保存到磁盘）。
    - `file_exists` (Boolean, db_index): 指示 MP4 是否已下载并存在于磁盘上。
    - `file_size` (BigInteger, nullable): MP4 文件大小（字节）。
    - `watched` (Boolean, db_index): 旧共享已观看快照，仅用于显式导入/回退；运行时使用UserResourceState个人投影。
    - `is_favorite` (Boolean, db_index): 旧共享收藏快照；运行时使用UserResourceState个人投影。
    - `metadata_created_at` (DateTime, nullable): 元数据首次创建时间。
    - `metadata_updated_at` (DateTime, auto_now): 元数据最后更新时间，自动更新。
    - `video_saved_at` (DateTime, nullable): 视频保存时间。
    - `created_at` (DateTime): 记录创建时间。
  - 索引：`avid`, `original_title`, `source`（用于快速检索与分页）。
  - 默认排序：按 `metadata_updated_at` 降序。

- **`Actor` (`nassav_actor`)**: 演员表，去重存储演员名字并建立 M2M。
  - 关键字段：
    - `name` (Char, unique, db_index): 演员名称。
    - `avatar_url` (URLField, nullable): 头像图片URL（来自Javbus，可能为空）。
    - `avatar_filename` (Char, nullable): 头像文件名（存储在 resource/avatar/）。
    - `updated_at` (DateTime, auto_now): 最后更新时间，自动更新。
  - 默认排序：按 `name` 升序。

- **`ActorSourceMapping` (`nassav_actor_source_mapping`)**: 演员到外部 source 身份的持久化映射表。
  - 关键字段：
    - `actor` (FK): 关联本地 `Actor`。
    - `source_name` (Char, db_index): 外部源标识，当前主要用于 `jable`。
    - `source_actor_name` (Char): source 侧展示名。
    - `source_actor_slug` (Char, nullable): source 侧稳定标识；对 Jable 为 `models/{slug}` 中的 slug。
    - `source_actor_url` (URLField): source 侧演员页 URL。
    - `aliases` (JSONField): source 侧别名列表。
    - `match_method` / `confidence` / `is_verified` / `is_active`: 映射来源与可信度控制字段。
    - `last_seen_at` / `created_at` / `updated_at`: 使用与维护时间。
  - 约束：
    - `(actor, source_name)` 唯一，保证同一演员在同一 source 下只有一条主映射。
    - `(source_name, source_actor_slug)` 唯一，避免两个本地演员绑定到同一个 source slug。

- **`Genre` (`nassav_genre`)**: 类型/标签表。
  - 关键字段：
    - `name` (Char, unique, db_index): 类别名称。
  - 默认排序：按 `name` 升序。

- **`GenreSourceMapping` (`nassav_genre_source_mapping`)**: 本地类别到外部 source 标签/分类身份的持久化映射表。
  - 关键字段：
    - `genre` (FK): 关联本地 `Genre`。
    - `source_name` (Char, db_index): 外部源标识，当前预期主要用于 `jable`。
    - `source_genre_name` (Char): source 侧展示名。
    - `source_genre_slug` (Char, nullable): source 侧稳定标识；对 Jable 为 `tags/{slug}` 或 `categories/{slug}` 中的 slug。
    - `source_genre_url` (URLField): source 侧标签页或分类页 URL。
    - `aliases` (JSONField): source 侧别名或人工补充同义词。
    - `match_method` / `confidence` / `is_verified` / `is_active`: 映射来源与可信度控制字段。
    - `last_seen_at` / `created_at` / `updated_at`: 使用与维护时间。
  - 约束：
    - `(genre, source_name)` 唯一，保证同一本地类别在同一 source 下只有一条主映射。
  - 说明：
    - `source_genre_slug` 不要求唯一；多个本地类别共享同一个 source 标签/分类 slug 是允许的。

- **`RecommendationSnapshot` (`nassav_recommendation_snapshot`)**: 推荐快照表。
  - 关键字段：
    - `recommender_id` (Char, db_index): 推荐器标识。
    - `strategy_id` (Char, db_index): 推荐策略标识。
    - `request_fingerprint` (Char, db_index): 去除随机因素后的请求指纹，用于识别“同一组推荐配置”。
    - `request_payload` (JSONField): 实际执行时的请求参数，包括 limit、seed 参数、历史过滤开关与 `random_seed`。
    - `seed_summary` (JSONField): 本次推荐使用的 seeds 摘要。
    - `item_count` (PositiveInteger): 返回结果数量。
    - `random_seed` (BigInteger): 本次排序使用的随机种子。
    - `generated_at` (DateTime, db_index): 快照生成时间。
  - 用途：
    - 推荐结果审计
    - 为“刷新推荐”提供最近推荐历史
    - 后续策略分析和回放

- **`RecommendationItem` (`nassav_recommendation_item`)**: 推荐结果明细表。
  - 关键字段：
    - `snapshot` (FK): 所属推荐快照。
    - `rank` (PositiveInteger): 在该 snapshot 中的名次。
    - `avid` (Char, db_index): 推荐项对应的资源编号。
    - `title` / `detail_url` / `cover_url` / `source`: 展示与来源字段。
    - `score` (Float): 最终推荐分数。
    - `search_rank` (Integer, nullable): 在外站搜索结果中的位置。
    - `reasons` (JSONField): 对前端展示的推荐理由列表。
    - `matched_seeds` (JSONField): 命中的 seeds 摘要。
    - `score_breakdown` (JSONField): 各 factor 的打分分解。
    - `raw_metrics` (JSONField): views / likes 等原始热度指标。
  - 约束：
    - `(snapshot, rank)` 唯一，保证每个快照中的排序位唯一。

- **`RecommendationItemSeed` (`nassav_recommendation_item_seed`)**: 推荐结果命中的结构化 seed 明细表。
  - 关键字段：
    - `item` (FK): 所属推荐结果明细。
    - `seed_type` (Char, db_index): seed 类型，当前为 `actor` 或 `genre`。
    - `seed_value` / `normalized_value` / `seed_key`: seed 的展示值、归一化值与逻辑键。
    - `source` / `source_name` / `source_identifier`: seed 来源与外部 source 侧身份。
    - `aliases` (JSONField): seed 的别名列表。
    - `weight` / `resource_count` / `preference_score`: 本轮推荐时该 seed 的权重上下文。
  - 约束：
    - `(item, seed_key)` 唯一，保证同一推荐结果里同一 seed 只记录一次。
  - 用途：
    - 替代 `RecommendationItem.matched_seeds` 上的统计职责
    - 支撑近期 seed 暴露统计与后续 seed 级反馈分析

- **`RecommendationAvidBlocklist` (`nassav_recommendation_avid_blocklist`)**: AVID 级永久屏蔽表。
  - 关键字段：
    - `avid` (Char, unique, db_index): 被永久屏蔽的资源编号。
    - `source` (Char, db_index): 屏蔽来源，当前主要为 `manual` 或迁移过来的 `legacy_feedback`。
    - `reason` (Char): 屏蔽原因。
    - `created_at` / `updated_at`: 创建与最近更新时间。
  - 用途：
    - 对用户明确拉黑/屏蔽的具体作品做永久屏蔽
    - 供推荐流程直接构建 `blocked_avids`

- **`RecommendationSeedProfile` (`nassav_recommendation_seed_profile`)**: 推荐因素画像表。
  - 关键字段：
    - `seed_type` (Char, db_index): `actor` 或 `genre`。
    - `value` / `normalized_value`: seed 展示值与归一化值。
    - `source_name` / `source_identifier`: 外部 source 侧稳定身份，可用于表达库外演员/类别。
    - `aliases` (JSONField): 该 seed 的别名。
    - `is_blocked` (Bool, db_index): 是否显式屏蔽该推荐因素。
    - `block_reason` (Char): 屏蔽原因。
    - `recommended_count` / `accepted_count` / `disliked_count`: 推荐次数、采纳次数、不喜欢次数。
    - `last_recommended_at`: 最近一次命中的时间。
  - 约束：
    - `(seed_type, normalized_value, source_name, source_identifier)` 唯一。
  - 用途：
    - 表达演员 / 类别级别的长期偏好画像
    - 支持对库中已有演员 / 类别进行显式屏蔽
    - 为后续 actor / genre 级别的降权与统计提供基础

- **`RecommendationFeedback` (`nassav_recommendation_feedback`)**: 推荐反馈表。
  - 关键字段：
    - `item` (OneToOne FK): 对应的推荐结果明细。
    - `avid` (Char, db_index): 被反馈的资源编号。
    - `feedback` (Char, db_index): 显式反馈类型，当前持久化 `like` 与 `dislike`；接口提交 `clear` 会删除反馈记录。
    - `feedback_value` (SmallInteger): 归一化后的反馈值，`like=1`，`dislike=-1`。
    - `created_at` / `updated_at`: 反馈创建与最后更新时间。
  - 用途：
    - 记录用户对具体推荐结果的显式反馈事件
    - 作为迁移与审计上下文保留
    - 与 `RecommendationAvidBlocklist`、`RecommendationSeedProfile` 联合构成新的长期偏好状态

- **M2M 关系**：`AVResource.actors` 与 `AVResource.genres`（分别通过中间表保存关联）。

## 持久化 & 更新流程（简要）

### 资源新增与刷新

`resource_workflow.ResourceService` 编排完整用例；`resource_service.resource_service` 保留同步消费者的生产实例，资源 job 也使用相同用例。读取、来源、刮削、资产、保存、翻译提交和事件能力由装配入口注入。

1. 读取已存在记录并获取来源信息。`resource_data.AVDownloadInfo` 的原始标题字段是 `title`，来源备用标题是 `source_title`，并包含 avid/m3u8/source/actors/genres/duration 等；`original_title` 是数据库字段。
2. 有 HTML 时先保存原始页面；可选刮削后处理封面。文件位于 `COVER_DIR/{AVID}.html` 和 `COVER_DIR/{AVID}.jpg`，默认分别在 `resource/cover/`。封面优先使用 Javbus 刮削 URL，再使用来源封面能力。
3. 来源把 HTML 解析为 `SourceRelations`，用例构造 `ResourceSaveInput` 交给 `DjangoResourcePersistence`。保存器不接收 HTML 或源实例，在下载信息副本上合并刮削数据，不修改来源缓存。
4. 保存 `AVResource` 及关系。刮削的 `title` 映射到 `original_title`，来源标题规范化到 `source_title`；有刮削时 metadata 保留完整下载信息字典，无刮削时保留原 metadata 并更新来源字段。`translation_status` 置为 pending；已有译文不会因此自动清空。
5. 来源演员候选与刮削关系交给 ORM Adapter，按 source ID 同步映射和保护冲突；Jable HTML 解析发生在来源 Adapter 内。actor/genre 关联和时间戳保留原规则。duration 解析为秒；本地视频存在时使用 ffprobe 的秒数覆盖。
6. 保存后按选项处理演员头像，再按已刮削数据提交翻译；完整资源结果返回后发布新增/刷新事件。头像在 `AVATAR_DIR`，封面在 `COVER_DIR`，视频在 `VIDEO_DIR`，自定义目录以实际 settings 为准。

文件与数据库不是统一事务：HTML/封面可能先保存，即使写库失败也不会自动补偿删除文件；写库失败不会发布资源新增事件。资源响应采用 `resource_presentation` 的既有字段，ORM 返回对象仍是读取能力允许的过渡契约。

### 下载结果写入

真实 `nassav.tasks.download_video_task` 调用 DownloadUseCase，`DjangoDownloadPersistence` 负责写库：

- 文件检查路径为 `VIDEO_DIR/{AVID.upper()}.mp4`，默认 `resource/video/{AVID}.mp4`。文件存在时写 file_exists、file_size、video_saved_at；不存在时清除大小/保存时间并置 file_exists 为 false。
- 正常流程仍先发下载成功事件，再持久化文件状态；写库失败仅告警，用例仍可返回成功，不能根据成功通知认定 DB 已同步。
- 下载失败时尽量置 file_exists 为 false，已有大小/保存时间沿用失败处理规则；不把失败当作删除视频操作。重试由 Celery 入口适配，次数和队列保持。
- 失租或 Redis 续租失败时中止 CLI 并抑制后续成功状态，迟到执行不能修改后继 owner 的进度或清理其队列。Redis 锁保护不等于跨文件/DB 的事务。

### 翻译状态

单条与批量由 TitleTranslationUseCase 共享标题选择：original_title 优先，缺失时使用 source_title。TranslatorManager 和 DjangoTranslationRepository 分别处理文本与状态读写。

批量按实际标题字段、指定 AVID 和 skip_existing 筛选；置 translating 前固定本批快照。翻译器异常、返回数量不匹配或逐项保存异常时，仅将本批仍 translating 的记录置 failed，保留已完成项和旧译文，不影响其他批次。HTTP 重新翻译通过 TranslationRequests 显式清空译文/重置 pending 后提交；提交失败维持已重置状态并返回既有 translation_error，不自动回滚重置。

- 更新资源状态（API PATCH `/resource/{avid}/status`）:
  - 部分更新当前用户的watched、is_favorite、watch_later或notes，个人version递增并支持expected_version冲突检查。
  - 更新个人状态不修改共享metadata_updated_at；详情ETag绑定用户/个人版本，共享Last-Modified不能独立验证个人投影。

- 删除资源（API/视图）:
  - `DELETE /resource/{avid}` 和批量 `delete` / `delete-all` 共用完整删除操作：删除封面、缩略图、MP4、备份目录和 `AVResource` 行。纯数据库行或纯文件仍可删除；文件步骤失败不会删除数据库行，数据库步骤失败可重试。
  - `DELETE /downloads/{avid}` 和批量 `delete-video` 仅删除 MP4，并将 `file_exists=False`、`file_size=None`、`video_saved_at=None`；元数据保留。文件已删除但数据库更新失败时可重试清除状态。

- 推荐请求完成（RecommendationWorkflow 与 DjangoRecommendationContext）:
  - 执行推荐前会根据：
    - `recommender_id`
    - `strategy_id`
    - `request_fingerprint`
      查询最近几次同配置推荐的快照
  - 将这些快照中的 `avid` 作为“最近推荐历史”注入当前请求，优先避免重复返回
  - 若过滤后剩余候选少于本次 `limit`，会回补一部分近期已推荐候选，避免连续刷新时返回数不足
  - 推荐执行完成后：
    - 写入一条 `RecommendationSnapshot`
    - 为每个返回项写入一条 `RecommendationItem`
  - 执行推荐前还会读取 `RecommendationFeedback`：
    - 读取 AVID 黑名单，形成直接过滤集合
    - 聚合历史 seed 画像，形成演员 / 类别 seed 偏好分
    - 将这些学习信号注入 `RecommendationRequest`，供 `FeedbackSignalFactor` 参与打分
  - 对演员 seed，如果名称中包含括号别名，会展开多个搜索关键词参与召回
  - 若演员存在 `ActorSourceMapping(source_name="jable")`，则推荐器会优先使用 `models/{source_actor_slug}` 的 async block 召回该演员作品，再回退到普通搜索
  - 搜索页、演员页、热榜和最近更新页在继续翻页时统一使用 `from=NN`，而不是旧的 `page=N`
  - 还会将 Jable 热榜/最近更新候选作为 discovery 补充写入同一批 `RecommendationItem`
  - 对 discovery 候选，会在配置上限内抓取 Jable 详情页补充 actor/genre 元数据；若详情命中本轮 seed，会写入 `matched_seeds` 和 `RecommendationItemSeed`
  - 若最近推荐过滤后没有剩余候选，会回退到不过滤历史的候选列表，避免返回空结果

- 推荐反馈提交（API `POST /recommendations/feedback`）:
  - 根据 `snapshot_id + avid` 定位唯一的 `RecommendationItem`
  - 对该推荐项执行显式反馈 upsert：
    - `like` 写为 `feedback_value=1`
    - `dislike` 写为 `feedback_value=-1`
    - `clear` 删除当前反馈记录
  - `like` 会累计命中 seed 的 `accepted_count`
  - `dislike` 会累计命中 seed 的 `disliked_count`
  - 如果同一推荐项从旧反馈切换为新反馈或清除反馈，系统会按差异修正 seed 的正负反馈计数
  - AVID 级屏蔽由 `POST /recommendations/avid-blocklist` 独立写入

## 一致性与事务控制

- 当前资源保存先 update_or_create 主记录，再追加演员/类别关系与来源映射，没有覆盖整个保存操作的外层 transaction.atomic；ORM 单步事务不保证完整多表原子性，异常可能留下部分关系。文件和 DB 同样没有整体补偿事务。
- 对于下载任务的后置更新（`file_exists`、`file_size`、`video_saved_at`）也使用事务以防止部分写入。

## 查询与搜索

- 常见查询：
  - 按 `avid` 精确查找（主键索引）。
  - 按 `actor`：通过 `Actor` 表反向关联 `resources`（`Actor.resources.all()` 或 `AVResource.objects.filter(actors__name__icontains=...)`）。
  - 按 `genres`：类似 `AVResource.objects.filter(genres__name__in=[...])`。
  - 按标题搜索：支持 `original_title`、`source_title`、`translated_title` 的模糊匹配。
  - 按状态过滤：watched/is_favorite使用当前用户的UserResourceState投影，file_exists等字段仍取共享资源，不读取旧共享标记快照。
  - 按翻译状态过滤：`translation_status` 字段支持精确匹配。
  - 全文/模糊匹配建议：对标题字段使用数据库的全文/trigram 扩展（在 PostgreSQL 上）以提高搜索体验。

- 聚合查询（Actors/Genres 列表）：
  - 使用 `Actor.objects.annotate(resource_count=Count('resources'))` 获取演员及其作品数统计。
  - 使用 `Genre.objects.annotate(resource_count=Count('resources'))` 获取类别及其作品数统计。
  - 支持按 `resource_count` 或 `name` 排序，可实现"最热演员"或"作品最多类别"等功能。
  - 在过滤 M2M 关系时使用 `distinct()` 避免重复记录（如同时按 actor 和 genre 过滤时）。

## 监控与回滚

- 大规模修复前使用现行一致性管理命令生成报告，并保留日志及数据库备份。
- 在大规模变更前：先执行 `--dry-run`，并备份现有 JSON/资源目录。

## 建议 / 注意事项

- 数据库模式和恢复按本页行为及[Compose 部署](compose-deployment.md)验证；当前业务数据以数据库记录为准，不依赖旧布局的逐资源 JSON 导入命令。
- Actor.name 与 Genre.name 已有唯一约束和索引，SQLite/PostgreSQL 共用模型。metadata 的 PostgreSQL GIN 索引不是当前已声明能力；新增索引须依据实际查询与独立迁移验收。
- 定期运行对比/校验任务，确保磁盘文件（cover/mp4）与 `AVResource.file_exists`、`file_size` 一致。

文件: `nassav/models.py`, 修复脚本: `scripts/fix_durations.py`。

## P4 管理状态

`GET /api/source/cookie` 继续返回旧的 `source/cookie/mtime`，另计算 `session_source`、`user_agent_paired`、`session_expired`、`verified_direct_reuse`。后者仅在 Cookie、UA、路线摘要俱全、未到期且与当前源代理路线相同时为真；人工 Cookie 即使附带 UA 也只是“已保存”。接口不返回完整 UA。人工 POST 不带 `user_agent` 会原子清空旧 UA、到期时间和路线标识，不需清库即可关闭或恢复会话复用。

### Jable 自动 Cookie 写入（2026-10-01）

Jable 的 Byparr 自动获取入口在浏览器首页业务校验和同页直连验证后，通过现有 `set_session_if_version` 原子保存 Cookie、UA、到期时间及出口信息。复用既有字段，无需数据库迁移；版本变化或刷新租约失效时拒绝写入。见 [Cookie 回归说明](../tests/README.md)。

## MissAV 演员、类别搜索映射

复用 `ActorSourceMapping`、`GenreSourceMapping`，源名为 `missav`。可填写原站的 `source_actor_slug` / `source_genre_slug`，或填写 `/en/actresses/{名称}` / `/en/genres/{名称}` URL；保存时提取并解码 slug，MissAV 保留大小写（例如 `VR`）。不保存动态 `dmN` 前缀作为 slug。旧记录没有自动回填；此前已被转小写的 MissAV slug 可通过原站 URL 重新保存修正。缺少映射时按实体名称关键词搜索，不擅自生成映射或写入生产数据。字段没有变化，无需迁移。

## 外部搜索任务与默认源（2026-10-01）

该功能最初不新增表；第二阶段0033改用用户数据库设置，旧INI不再运行时读取，见[迁移与归属](personal-state-architecture.md)。

搜索任务使用 Redis `nassav:search:job:{task_id}` 快照和 `nassav:search:lock:{query_hash}` 查询锁。复用既有 JobStore 持久化与终态保护；快照 TTL 24 小时，成功结果复用窗口 300 秒，提交后 1800 秒未完成则读取时标记超时并释放锁。`cancelled` 也是终态，取消立即释放查询锁并保留阶段结果；终态不允许迟到结果覆盖。查询摘要包含实体、源、分页、排序、强制刷新、中文版本、域名、代理线路和抓取页数。

### 搜索逐页快照

每个非空源页面完成后更新同一个 Redis 快照的 `result`、`pages_completed` 和单调递增的 `version`；`result.data.external_meta.partial` 在采集中为 true，成功终态为 false。失败终态保留最后的阶段结果，仍不允许迟到页覆盖终态。阶段结果不写入 Django 成功结果缓存或前端会话缓存。WebSocket 仅广播任务 ID、状态、版本和更新时间，卡片数据依旧通过已登录且验证签名的查询接口读取。不新增模型或字段，无数据库迁移。

## 会话存储契约

会话读写由 `CookieRepository` ABC 约束，生产实现仍为 `SourceCookieRepository`。Source 的会话获取、验证和刷新协调位于 `SourceSessionLifecycle`，可注入独立存储与协调器。完整快照字段、数据库版本校验、人工写入优先、CAS 和缓存格式保持现有行为；本轮迁移没有 schema 或迁移文件变化。

核心能力与 ORM Adapter 的分工见[任务架构](task-control-architecture.md)与[推荐架构](recommendation-architecture.md)，复验命令见[测试说明](../tests/README.md)。本轮职责整理未引入 schema 或数据库迁移。

## 持久任务记录（任务控制 P1）

迁移 `0022_taskjob_taskcommand_taskattempt_taskartifact_and_more` 新增 TaskJob、TaskAttempt、TaskArtifact 与 TaskCommand，不修改现有资源数据。新下载及 HTTP 刮削提交已接入持久记录，Redis 仅作兼容投影；旧消息仍兼容但不支持控制。迁移执行情况按目标实例核对，不能从本文推断。当前控制协议与职责见[任务控制架构](task-control-architecture.md)。

- TaskJob 保存稳定 UUID、类型/AVID、操作人、整体状态、version/generation、输入选项、检查点、时间线与清理汇总。`active_key` 唯一约束保留运行/等待/暂停任务的同类型同 AVID 名额，终态置空；任务没有 Redis 的 24 小时过期规则。
- TaskAttempt 保存每次 Celery 派发 UUID、generation/role、执行 owner/identity、心跳与起止时间。恢复新建 attempt，旧消息不重新激活；pending 是可重试派发记录，发布失败保留，领取时原子拒绝重复执行。
- TaskArtifact 预留工作区相对路径、资产类型、checksum、提交/删除状态与目标清单。文件暂存、提升、恢复及删除由 TaskAssets 按归属清单执行。
- TaskCommand 的 `(job, request_id)` 唯一约束记录控制幂等键及动作，重复请求即使跨越后续状态变化也不得再次恢复或派发；同一键用于不同动作返回冲突。

P2 迁移 `0023_taskassettarget` 新增正式资产发布标记表，按 `(root, relative_path)` 唯一；marker 表示本次发布归属，不以内容相同作为同一发布的证据。TaskArtifact 的 staged → promoting → committed 日志记录旧 checksum/marker、私有旧文件备份与新 marker。先持久化准备，再在短 DB 写入 fence 下提升文件和保存业务记录；失败回滚 DB 后按日志补偿文件。恢复仅在 writer 停止后执行；缺失备份、后续发布或未知文件变化保留现场并报告失败，不承诺 DB/文件系统全局原子性。

存在 promoting 日志时禁止恢复任务，须先收尾日志。终态 cleanup_state 独立于业务状态，清理失败的 `cleanup_retry` 只重新置为 pending，不创建 attempt 或复活执行。成功任务也可清理剩余私有备份；正式资产保留。部署必须核对迁移 0022/0023 已应用。

SQLite/PostgreSQL 均通过版本条件更新和事务保证并发控制；SQLite 的瞬时锁竞争可有限重试，不忽略其他数据库错误。暂停处理中禁止恢复，终止优先于暂停；确认执行停止后才进入 paused/cancelled。`cancelled` 与 `cleanup_state` 独立，DB 控制记录不证明文件已经清理。

P4 迁移 `0024_taskevent_taskeventreceipt_and_more` 新增资源提交事件出箱及收件去重记录：TaskEvent 按 `(job, event)` 唯一，稳定 UUID 跨派发重试不变；TaskEventReceipt 按 `(event, consumer)` 唯一。资源与事件登记在同一个受控事务内，派发在事务外，失败保留 pending。现有日志消费者去重，新增具有业务副作用的消费者仍需自己的幂等收件。部署须核对 0024；验证和限制见[事件出箱架构](task-control-architecture.md)。

P5 迁移 `0025_avresource_translation_generation_and_more` 新增私有翻译 generation/owner 字段，不作为资源 API 字段展示。元数据保存与归属失效在同一 ORM 事务内；请求和领取递增 generation，结果及异常仅更新本 owner/version。TaskAttempt.role=translation 表示所属子派发，父执行交接为 stopped，整体 queued 等待子执行；恢复新 generation/main，已保存资源直接交接新 child。TaskJob.translation 与整体状态/时间线共同持久化，不将资源 pending 状态解释为父任务恢复。部署须核对 0025，见[所属翻译架构](task-control-architecture.md)。

P7 不增加 schema。恢复扫描依据 TaskAttempt 的 worker host/boot_id/PID namespace/PID/start_ticks，心跳超时只触发核查；身份未知保持原控制状态并记 RECOVERY_UNCONFIRMED。原 writer 确认退出后 stopped attempt，按取消意图进入 cancelled 或保留 paused，翻译归属仅收尾该子执行。未恢复的 promoting 日志禁止恢复和正式资源删除，避免删除后旧补偿恢复文件；后台重试日志和清理，失败不复活任务。

迁移顺序为 0022 → 0023 → 0024 → 0025；实施前备份并停用旧消费者，生产迁移及回滚操作见[部署说明](compose-deployment.md#持久任务控制版本切换与回滚)。SQLite/PostgreSQL 隔离证据见[部署与验证边界](compose-deployment.md#近期改动与验证边界)，不代表生产切换验收。

持久任务的当前架构、执行归属、资产提交及扩展检查清单见[任务控制架构](task-control-architecture.md)。历史阶段的迁移/部署状态只代表记录当时；本轮验收确认及仍需独立验证的范围以[部署与验证边界](compose-deployment.md#近期改动与验证边界)为准。

## 推荐任务与历史代次（0026）

`RecommendationJob` 保存创建者、参数、执行 UUID、state/version、结果、绝对 deadline
及补派时间；与下载/刮削 TaskJob 独立。任务 ID 是公开身份，执行 UUID 不对外暴露。
`RecommendationState` 使用 pk=1 保存历史 generation，清空历史递增；
成功提交检查 generation 和任务执行归属，snapshot 与成功结果原子保存。
部署先应用迁移 0026，重启 API/worker。迁移不更改已有推荐 snapshot 内容。

## 持久抓取缓存（0027）

ResourceMetadataCache 与 ResourcePlaybackCache 独立于 AVResource，无业务资源外键。唯一键为 AVID/提供者类型/名称/上下文哈希/版本路径哈希；JSON 为原站解析结果，不含收藏、观看、翻译或任务状态。播放表限定 source。迁移空表，不回填混合 metadata 或旧播放地址；有效期、领取代次与可替换存储接口见[缓存架构](resource-cache-architecture.md)。

## 表名规范化（迁移 0028）

业务模型显式声明 Meta.db_table，表名全小写，单词之间使用下划线；AV/AVID 等缩写作为单词整体。source_cookie 与其他已经符合规范的表保留现名。字段、模型身份、ContentType/权限、数据与 API 契约保持；序列和约束沿用已有名称，本轮规范仅针对表名。

| 原表名                         | 新表名                           |
| ------------------------------ | -------------------------------- |
| `nassav_avresource`            | `nassav_av_resource`             |
| `nassav_avresource_actors`     | `nassav_av_resource_actors`      |
| `nassav_avresource_genres`     | `nassav_av_resource_genres`      |
| `nassav_taskjob`               | `nassav_task_job`                |
| `nassav_taskattempt`           | `nassav_task_attempt`            |
| `nassav_taskartifact`          | `nassav_task_artifact`           |
| `nassav_taskcommand`           | `nassav_task_command`            |
| `nassav_taskassettarget`       | `nassav_task_asset_target`       |
| `nassav_taskevent`             | `nassav_task_event`              |
| `nassav_taskeventreceipt`      | `nassav_task_event_receipt`      |
| `nassav_recommendationstate`   | `nassav_recommendation_state`    |
| `nassav_recommendationjob`     | `nassav_recommendation_job`      |
| `nassav_resourcemetadatacache` | `nassav_resource_metadata_cache` |
| `nassav_resourceplaybackcache` | `nassav_resource_playback_cache` |

0028_normalize_table_names 包含 12 个 AlterModelTable，资源主表的两个隐式多对多关联表由 Django 自动改名，共影响 14 张物理表。TaskJob、TaskAttempt、RecommendationJob 的索引显式固定原名称，不重建索引。历史 0002/0004 等迁移保留原表名，以支持空库安装与回退链。迁移不搬运资源文件或重置任务/缓存；执行前检查名称冲突并按[部署步骤](compose-deployment.md#表名规范化迁移-0028)备份和停止旧消费者。

验证记录（2026-10-08）：阶段提交标题 `[Enhancement] Normalize database table names with reversible migration`。`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`：860 passed/28 skipped；迁移专项 SQLite 与独立 PostgreSQL 17 nassav schema 各 2 passed，覆盖完整字段/主键/关系行、全部声明索引/约束/外键及 0027→0028→0027→0028。`makemigrations --check --dry-run` 返回 No changes detected；PostgreSQL `sqlmigrate nassav 0028` 仅生成 14 次 ALTER TABLE RENAME。正式数据库、镜像和服务尚未切换。

## 在线播放会话：迁移 0029

PlaybackSession 显式使用 nassav_playback_session，新增用户/资源关系及状态、版本、执行归属、私有描述和期限。资源删除级联撤销会话，原站事实缓存独立；详细状态与清理规则见[在线播放架构](online-playback-architecture.md)。升级/回退只影响新会话表，不修改已有表身份；正式切换先备份并统一消费者，功能默认关闭。

### 在线播放刷新基线（0030）

nassav_playback_session 增加 refresh_count（默认 0）和 manifest_identity（默认空 JSON）。后者仅保存有界引用路径、类别和 SHA-256（密钥/init 读取前为 null），用于同会话一次刷新兼容检查；不保存源站地址或媒体内容。0030 可逆，回退丢弃这两个新字段并保留会话/资源/用户关系。正式切换须停止混合版本 API/worker，备份后迁移；退出新消费者再回退。

## 0031：本地播放会话模式

PlaybackSession.media_kind（nassav_playback_session，varchar16，默认source）区分来源HLS与local MP4。迁移只增加字段，历史会话仍为source，可逆、不修改正式资源/文件/关系。local descriptor私有保存发布marker及文件指纹；公开快照不包含路径/指纹，沿用会话期限与终态清理。不新增进度表。部署前备份、统一API/worker消费者并执行migrate；不在运行旧会话时回退删除字段，回退前关闭会话。

## 个人播放进度（0032）

PlaybackProgress 独立持久化个人位置，表 nassav_playback_progress；唯一(user, avid, media_key)，用户删除级联，资源/会话删除保留。清除以墓碑撤销旧写入权，不增加共享watched语义。迁移回退删除进度表，回退前备份新增个人数据；详细协议见[播放进度架构](playback-progress-architecture.md)。

## 0035：推荐个人归属

迁移0035增加四个owner外键，Item/ItemSeed/Feedback沿snapshot继承；黑名单/种子唯一身份增加owner并保留NULL旧数据的条件唯一约束。迁移取消旧活动推荐job，不复制给所有账号，不改正式资源/缓存/文件。维护窗口停止旧消费者、备份、迁移后，在首次个人推荐前运行import_recommendation_data预览并显式归属原操作者。不同用户出现相同旧唯一身份时回退主动拒绝，见[推荐架构](recommendation-architecture.md#用户归属第三阶段)。JSON新增推荐偏好无需增加列，GET只读补齐、PUT仅合并合法提交键。

第三阶段播放设置与第四阶段跨设备接续复用0034的用户JSON及0032的PlaybackProgress，不增加表或列；本轮唯一新增结构迁移仍为0035推荐归属。继续观看查询先选择user/AVID最新ledger，再过滤完成/清除/媒体变化，资源删除不级联进度；不同登录共用个人ledger，但不能共用播放session控制权。

## 0036：观看历史与稍后观看

新增nassav_user_watch_history（user/resource级联外键、last_watched_at、media_kind），唯一(user,resource)，索引(user,-last_watched_at,-id)。UserResourceState新增watch_later（默认false）和watch_later_added_at（可空）；PlaybackSession新增history_sequence（默认0）和history_recorded_at（可空），用于播放事件去重与乱序保护。

0036只新增空历史表/默认字段，不推测回填旧进度或watched，不修改视频和原站缓存。回退删除历史表及新增字段，原收藏/观看/备注/版本保持，新增历史/稍后观看数据会丢失；升级/回退前备份并停止混合版本消费者。正式部署须应用0036，隔离迁移验证不代替部署验收。

未发布P3范围消费者新增0041 source_credential_key_policy；开发叶节点为0041。该结构不导入秘密或切换配置，专用写入密钥fence及迁移影响见[凭证架构](source-credential-architecture.md)。
