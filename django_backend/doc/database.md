## Database Overview

- **Scope:** 介绍与 `AVResource` 相关的数据库表、它们之间的关系、字段语义、索引、以及元数据/封面/视频的持久化和更新流程。

## Models & Tables

- **`SourceCookie` (`source_cookie`)**: 存储下载源的 Cookie 配置表。
  - 关键字段：
    - `source_name` (Char, unique, primary_key): 源名称，主键。
    - `cookie` (Text): Cookie 字符串。
    - `updated_at` (DateTime, auto_now): 更新时间，自动更新。

- **`AVResource` (`nassav_avresource`)**: 主表，保存 AV 元数据（除封面与视频文件外的所有字段）。
  - 关键字段：
    - `avid` (Char, unique, db_index): AV 编号，主查找键。
    - `original_title` (Char, db_index): Scraper 获取的原始标题（通常为日语，来自 Javbus）。
    - `source_title` (Char, nullable): Source 获取的标题（备用，来自 MissAV/Jable 等）。
    - `translated_title` (Char, nullable): 翻译后的标题（中文，由 Ollama 翻译）。
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

- **`RecommendationFeedback` (`nassav_recommendation_feedback`)**: 推荐反馈表。
  - 关键字段：
    - `item` (OneToOne FK): 对应的推荐结果明细。
    - `avid` (Char, db_index): 被反馈的资源编号。
    - `feedback` (Char, db_index): 显式反馈类型，当前支持 `like` / `dislike`。
    - `feedback_value` (SmallInteger): 归一化后的反馈值，`like=1`，`dislike=-1`。
    - `created_at` / `updated_at`: 反馈创建与最后更新时间。
  - 用途：
    - 记录用户对推荐结果的显式偏好
    - 聚合为 `avid` 级别的直接偏好记忆
    - 聚合为演员 / 类别 seed 级别的学习信号，参与后续推荐打分

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
  - 删除磁盘上的封面/MP4 后，会尝试更新 `AVResource`：将 `file_exists=False`、`file_size=None`、`video_saved_at=None`。元数据（JSON）默认保留，除非明确发起数据库删除操作。

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
    - 聚合历史 `avid` 反馈，形成直接资源偏好分
    - 聚合历史 `matched_seeds` 反馈，形成演员 / 类别 seed 偏好分
    - 将这些学习信号注入 `RecommendationRequest`，供 `FeedbackSignalFactor` 参与打分
  - 对演员 seed，如果名称中包含括号别名，会展开多个搜索关键词参与召回
  - 若演员存在 `ActorSourceMapping(source_name="jable")`，则推荐器会优先使用 `models/{source_actor_slug}` 的 async block 召回该演员作品，再回退到普通搜索
  - 还会将 Jable 热榜/最近更新候选作为 discovery 补充写入同一批 `RecommendationItem`
  - 若最近推荐过滤后没有剩余候选，会回退到不过滤历史的候选列表，避免返回空结果

- 推荐反馈提交（API `POST /recommendations/feedback`）:
  - 根据 `snapshot_id + avid` 定位唯一的 `RecommendationItem`
  - 对该推荐项执行显式反馈 upsert：
    - `like` 写为 `feedback_value=1`
    - `dislike` 写为 `feedback_value=-1`
    - `clear` 删除已有反馈记录

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

- 所有写入操作记录日志（`loguru`），出错时生成可审计的异常/报告（导入脚本会输出 `errors` 和 `mismatches` 报表）。
- 在大规模变更前：先执行 `--dry-run`，并备份现有 JSON/资源目录。

## 建议 / 注意事项

- 保持 `metadata` 的完整性：不要删除原始 JSON 直到导入验证完成并备份完成。
- 若转向生产级数据库（Postgres），为 `actors`/`genres` 添加唯一约束和必要的索引，并考虑使用 `GIN` 索引优化 `metadata` JSON 查询。
- 定期运行对比/校验任务，确保磁盘文件（cover/mp4）与 `AVResource.file_exists`、`file_size` 一致。

文件: `nassav/models.py`, 修复脚本: `scripts/fix_durations.py`。
