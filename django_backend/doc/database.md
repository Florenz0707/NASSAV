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

- **`AVResource` (`nassav_avresource`)**: 主表，保存 AV 元数据（除封面与视频文件外的所有字段）。
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
    - `watched` (Boolean, db_index): 是否已观看。
    - `is_favorite` (Boolean, db_index): 是否收藏。
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

- 新资源入库（SourceManager.save_all_resources）:
  - 从 scraper 得到 `AVDownloadInfo`（内存结构），包含 `original_title`, `source_title`, `avid`, `m3u8`, `actors`, `actor_avatars`, `genres`, `duration` 等。
  - 封面下载策略：优先从 Javbus 刮削结果中获取封面URL（`cover_url` 字段），使用 `scraper.download_cover()` 下载（带Referer头绕过防护）；如果Javbus没有封面则回退到Source提供的封面URL，使用 `source.download_file()` 下载。封面保存到 `resource/cover/{AVID}.jpg`。
  - 将元数据写入 `AVResource`：
    - `original_title`: Scraper获取的原始标题（通常为日语）。
    - `source_title`: Source获取的标题（备用）。
    - `translated_title`: 初始为空，等待翻译任务填充。
    - `translation_status`: 初始为 "pending"。
    - `metadata`: 保存原始 JSON。
    - `metadata_created_at`: 首次创建时设置为当前时间。
    - `metadata_updated_at`: 自动更新为当前时间。
  - 对 `actors`/`genres` 做 `get_or_create` 并设置 M2M 关系。
  - 若当前 source 为 `Jable` 且拿到了原始作品 HTML，会顺带解析 `div.models a.model`，把本地演员与 `ActorSourceMapping(source_name="jable")` 自动对齐。
  - 演员头像处理：从 `actor_avatars` 字典获取URL，更新 `Actor.avatar_url` 和 `avatar_filename`，使用 `utils.download_avatar()` 下载（带Referer头），保存到 `resource/avatar/` 目录。
  - `duration` 的写入规则：若爬取值是字符串（如 "150分钟"），解析为秒并写入；如果同时存在本地 MP4，优先用 `ffprobe` 获取的秒数覆盖。

- 下载任务完成（Celery `download_video_task`）:
  - 任务成功时：检测 `resource/{AVID}/{AVID}.mp4` 是否存在，若存在则通过 `stat()` 取得 `file_size` 并写入 `AVResource.file_size`，设置 `file_exists=True`，并写入 `video_saved_at` 为当前时间；若不存在则将 `file_exists=False`。
  - 任务失败或异常时：尽量将 `file_exists=False` 写入数据库并记录失败原因到日志/监控（不抛出未捕获异常以破坏重试机制）。

- 更新资源状态（API PATCH `/resource/{avid}/status`）:
  - 支持更新 `watched`（是否已观看）和 `is_favorite`（是否收藏）字段。
  - 更新时会自动触发 `metadata_updated_at` 字段更新为当前时间（auto_now=True）。
  - 前端通过禁用浏览器缓存的HTTP headers确保获取最新的 `metadata_updated_at` 值。

- 删除资源（API/视图）:
  - `DELETE /resource/{avid}` 和批量 `delete` / `delete-all` 共用完整删除操作：删除封面、缩略图、MP4、备份目录和 `AVResource` 行。纯数据库行或纯文件仍可删除；文件步骤失败不会删除数据库行，数据库步骤失败可重试。
  - `DELETE /downloads/{avid}` 和批量 `delete-video` 仅删除 MP4，并将 `file_exists=False`、`file_size=None`、`video_saved_at=None`；元数据保留。文件已删除但数据库更新失败时可重试清除状态。

- 推荐请求完成（RecommenderManager）:
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

- 对于涉及多表更新（写 `AVResource` + 设置 M2M actor/genre）使用 `transaction.atomic()` 保证原子性。
- 对于下载任务的后置更新（`file_exists`、`file_size`、`video_saved_at`）也使用事务以防止部分写入。

## 查询与搜索

- 常见查询：
  - 按 `avid` 精确查找（主键索引）。
  - 按 `actor`：通过 `Actor` 表反向关联 `resources`（`Actor.resources.all()` 或 `AVResource.objects.filter(actors__name__icontains=...)`）。
  - 按 `genres`：类似 `AVResource.objects.filter(genres__name__in=[...])`。
  - 按标题搜索：支持 `original_title`、`source_title`、`translated_title` 的模糊匹配。
  - 按状态过滤：`watched=True`、`is_favorite=True`、`file_exists=True` 等。
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

- 数据库迁移和恢复依照 [PostgreSQL 迁移计划](postgresql-migration-plan.md)验证；当前业务数据以数据库记录为准，不依赖旧布局的逐资源 JSON 导入命令。
- 若转向生产级数据库（Postgres），为 `actors`/`genres` 添加唯一约束和必要的索引，并考虑使用 `GIN` 索引优化 `metadata` JSON 查询。
- 定期运行对比/校验任务，确保磁盘文件（cover/mp4）与 `AVResource.file_exists`、`file_size` 一致。

文件: `nassav/models.py`, 修复脚本: `scripts/fix_durations.py`。

## P4 管理状态

`GET /api/source/cookie` 继续返回旧的 `source/cookie/mtime`，另计算 `session_source`、`user_agent_paired`、`session_expired`、`verified_direct_reuse`。后者仅在 Cookie、UA、路线摘要俱全、未到期且与当前源代理路线相同时为真；人工 Cookie 即使附带 UA 也只是“已保存”。接口不返回完整 UA。人工 POST 不带 `user_agent` 会原子清空旧 UA、到期时间和路线标识，不需清库即可关闭或恢复会话复用。

### Jable 自动 Cookie 写入（2026-10-01）

Jable 的 Byparr 自动获取入口在浏览器首页业务校验和同页直连验证后，通过现有 `set_session_if_version` 原子保存 Cookie、UA、到期时间及出口信息。复用既有字段，无需数据库迁移；版本变化或刷新租约失效时拒绝写入。见 [修复验证记录](jable-auto-cookie-fix-record.md)。

## MissAV 演员、类别搜索映射

复用 `ActorSourceMapping`、`GenreSourceMapping`，源名为 `missav`。可填写原站的 `source_actor_slug` / `source_genre_slug`，或填写 `/en/actresses/{名称}` / `/en/genres/{名称}` URL；保存时提取并解码 slug，MissAV 保留大小写（例如 `VR`）。不保存动态 `dmN` 前缀作为 slug。旧记录没有自动回填；此前已被转小写的 MissAV slug 可通过原站 URL 重新保存修正。缺少映射时按实体名称关键词搜索，不擅自生成映射或写入生产数据。字段没有变化，无需迁移。

## 外部搜索任务与默认源（2026-10-01）

本次不新增数据库表，无需迁移。`default_external_search_source` 保存在实例共享 `config/user_settings.ini`，默认模板与旧文件自动补齐规则已同步。

搜索任务使用 Redis `nassav:search:job:{task_id}` 快照和 `nassav:search:lock:{query_hash}` 查询锁。复用既有 JobStore 持久化与终态保护；快照 TTL 24 小时，成功结果复用窗口 300 秒，提交后 1800 秒未完成则读取时标记超时并释放锁。`cancelled` 也是终态，取消立即释放查询锁并保留阶段结果；终态不允许迟到结果覆盖。查询摘要包含实体、源、分页、排序、强制刷新、中文版本、域名、代理线路和抓取页数。

### 搜索逐页快照

每个非空源页面完成后更新同一个 Redis 快照的 `result`、`pages_completed` 和单调递增的 `version`；`result.data.external_meta.partial` 在采集中为 true，成功终态为 false。失败终态保留最后的阶段结果，仍不允许迟到页覆盖终态。阶段结果不写入 Django 成功结果缓存或前端会话缓存。WebSocket 仅广播任务 ID、状态、版本和更新时间，卡片数据依旧通过已登录且验证签名的查询接口读取。不新增模型或字段，无数据库迁移。

## 会话存储契约

会话读写由 `CookieRepository` ABC 约束，生产实现仍为 `SourceCookieRepository`。Source 的会话获取、验证和刷新协调位于 `SourceSessionLifecycle`，可注入独立存储与协调器。完整快照字段、数据库版本校验、人工写入优先、CAS 和缓存格式保持现有行为；本轮迁移没有 schema 或迁移文件变化。
