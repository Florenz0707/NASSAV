**Database Overview**

- **Scope:** 介绍与 `AVResource` 相关的数据库表、它们之间的关系、字段语义、索引、以及元数据/封面/视频的持久化和更新流程。

**Models & Tables**

- **`AVResource` (`nassav_avresource`)**: 主表，保存 AV 元数据（除封面与视频文件外的所有字段）。
  - 关键字段：
    - `avid` (Char, unique, db_index): AV 编号，主查找键。
    - `title` (Char): 标题，支持索引用于搜索。
    - `source` (Char): 抓取来源/Downloader 名称。
    - `release_date` (Char): 原始发布日期字符串。
    - `duration` (Integer, seconds): 时长（以秒为单位）。注意：爬取数据常为 "150分钟" 字符串，入库时解析为秒；若 mp4 文件存在，则优先使用 `ffprobe` 返回的实际秒数。
    - `metadata` (JSONField): 原始/完整的爬取 JSON，作为审计与补偿数据源。
    - `m3u8` (Text): 下载使用的 M3U8 URL（若有）。
    - `cover_filename` (Char): 相对于 `resource/{avid}/` 的封面文件名（仍把文件保存到磁盘）。
    - `file_exists` (Boolean): 指示 MP4 是否已下载并存在于磁盘上。
    - `file_size` (BigInteger): MP4 文件大小（字节）。
    - `metadata_saved_at`, `video_saved_at`, `created_at` (DateTime)：时间戳。
  - 索引：`avid`, `title`, `source`（用于快速检索与分页）。

- **`Actor` (`nassav_actor`)**: 演员表，去重存储演员名字并建立 M2M。字段：`name` (unique, db_index)。

- **`Genre` (`nassav_genre`)**: 类型/标签表，字段：`name` (unique, db_index)。

- M2M 关系：`AVResource.actors` 与 `AVResource.genres`（分别通过中间表保存关联）。

**持久化 & 更新流程（简要）**

- 新资源入库（SourceManager.save_all_resources）:
  - 从 scraper 得到 `AVDownloadInfo`（内存结构），包含 `title`, `avid`, `m3u8`, `actors`, `genres`, `duration` 等。
  - 将封面图片下载并保存到磁盘：`resource/{AVID}/{cover_filename}`，`cover_filename` 写入 `AVResource.cover_filename`。
  - 将元数据写入 `AVResource`（`metadata` 保存原始 JSON），对 `actors`/`genres` 做 `get_or_create` 并设置 M2M 关系。
  - `duration` 的写入规则：若爬取值是字符串（如 "150分钟"），解析为秒并写入；如果同时存在本地 MP4，优先用 `ffprobe` 获取的秒数覆盖。

- 下载任务完成（Celery `download_video_task`）:
  - 任务成功时：检测 `resource/{AVID}/{AVID}.mp4` 是否存在，若存在则通过 `stat()` 取得 `file_size` 并写入 `AVResource.file_size`，设置 `file_exists=True`，并写入 `video_saved_at` 为当前时间；若不存在则将 `file_exists=False`。
  - 任务失败或异常时：尽量将 `file_exists=False` 写入数据库并记录失败原因到日志/监控（不抛出未捕获异常以破坏重试机制）。

- 删除资源（API/视图）:
  - 删除磁盘上的封面/MP4 后，会尝试更新 `AVResource`：将 `file_exists=False`、`file_size=None`、`video_saved_at=None`。元数据（JSON）默认保留，除非明确发起数据库删除操作。

**导入历史元数据**

- 为了从现有 `resource/{AVID}/{AVID}.json` 迁移，项目包含脚本 `scripts/migrate_metadata_to_db.py`：支持 `--dry-run` 与 `--apply`，会把 JSON 内容写入 `AVResource.metadata` 并构建/更新 M2M 关系。该脚本也调用解析函数把字符串格式时长转换为秒（并在 MP4 存在时优先使用 `ffprobe`）。

**一致性与事务控制**

- 对于涉及多表更新（写 `AVResource` + 设置 M2M actor/genre）使用 `transaction.atomic()` 保证原子性。
- 对于下载任务的后置更新（`file_exists`、`file_size`、`video_saved_at`）也使用事务以防止部分写入。

**查询与搜索**

- 常见查询：
  - 按 `avid` 精确查找（主键索引）。
  - 按 `actor`：通过 `Actor` 表反向关联 `resources`（`Actor.resources.all()` 或 `AVResource.objects.filter(actors__name__icontains=...)`）。
  - 按 `genres`：类似 `AVResource.objects.filter(genres__name__in=[...])`。
  - 全文/模糊匹配建议：对 `title` 使用数据库的全文/trigram 扩展（在 PostgreSQL 上）以提高搜索体验。

**监控与回滚**

- 所有写入操作记录日志（`loguru`），出错时生成可审计的异常/报告（导入脚本会输出 `errors` 和 `mismatches` 报表）。
- 在大规模变更前：先执行 `--dry-run`，并备份现有 JSON/资源目录。

**建议 / 注意事项**

- 保持 `metadata` 的完整性：不要删除原始 JSON 直到导入验证完成并备份完成。
- 若转向生产级数据库（Postgres），为 `actors`/`genres` 添加唯一约束和必要的索引，并考虑使用 `GIN` 索引优化 `metadata` JSON 查询。
- 定期运行对比/校验任务，确保磁盘文件（cover/mp4）与 `AVResource.file_exists`、`file_size` 一致。

文件: `nassav/models.py`, 导入脚本: `scripts/migrate_metadata_to_db.py`, 修复脚本: `scripts/fix_durations.py`。
