# 可执行脚本清单与清理记录

核查日期：2026-09-28。范围为当前后端的 `scripts/`、Django 管理命令、测试 Shell 脚本和容器/本地启动入口；`origin_project/` 是历史参考实现，不属于当前运行入口。本次依据代码引用、文档入口、配置、现行数据模型和脚本默认行为判断；没有运行会修改真实数据库或访问外部站点的脚本。

## 已移除的历史入口

| 入口                                             | 处置依据                                                                                                                                                         |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/fix_refresh_inconsistency.py`           | 对旧批量刷新缺陷做一次性、无预览开关的数据修补；无代码或文档调用。视频状态已有 `check_videos_consistency` 和 `check_resources_consistency` 可检查/修复。         |
| `scripts/fix_source_titles.py`                   | 旧数据的 `source_title` 一次性回填；现行 `ResourcePersistence.save` 经 `normalize_source_title` 在添加/刷新时规范化标题。                                        |
| `nassav/management/commands/import_resources.py` | 读取旧布局的逐 AVID JSON 目录；与当前数据库优先的资源布局不符，且向已从 `AVResource` 改名的 `title` 字段写值。正式 PostgreSQL 迁移使用独立的 dump/restore 计划。 |

删除仅影响这些命令入口；未改数据库记录、迁移文件或资源目录。历史实现仍可从 Git 历史查看。

## 保留的 `scripts/` 入口

| 脚本                                       | 当前用途或保留理由                                                                        |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `backfill_actor_avatars.py`                | 对已有演员从作品重新获取缺失的头像 URL；与仅修复已有 URL 对应文件的脚本不同。             |
| `backfill_jable_actor_mappings.py`         | 补齐现有 Jable 作品的演员映射，仍有定向行为测试。                                         |
| `batch_translate.py`                       | 按需批量翻译，支持同步、队列、预览和指定资源。                                            |
| `check_recommendation_blacklist_filter.py` | 在线检查推荐黑名单是否漏过滤，属于诊断工具。                                              |
| `cleanup_unused_genres.py`                 | 按需预览和清除无资源关联的类别。                                                          |
| `export_jable_home_tags.py`                | 获取新的 Jable 标签候选，供人工映射核对。                                                 |
| `fix_actor_avatars.py`                     | 检查并修复已知头像 URL 对应的缺失文件。                                                   |
| `fix_actor_names.py`                       | 按需修复异常演员名；核心判断有测试覆盖。                                                  |
| `fix_avid_prefix_titles.py`                | 按需识别并重新刮削异常原标题。                                                            |
| `fix_durations.py`                         | 用 MP4 或元数据修复异常时长；现有一致性命令不覆盖该字段。                                 |
| `generate_openapi.py`                      | 生成 API 文档，也可直接运行 `manage.py spectacular`。                                     |
| `generate_thumbnails.py`                   | 对缺失或过期封面缩略图按需重建。                                                          |
| `import_jable_genre_mappings.py`           | 对人工审核的映射文件按需导入；仓库未附带默认 YAML，运行时须通过 `--input` 指定文件。      |
| `match_local_genres_to_jable_tags.py`      | 对当前数据库类别和标签导出结果生成新映射建议。                                            |
| `populate_media_fields.py`                 | 从现有文件重建媒体字段，保留给数据恢复或迁移校验；覆盖 `cover_filename` 和 MP4 修改时间。 |
| `sync_recommendation_actor_mappings.py`    | 从新增推荐历史补写演员映射，可定期运行。                                                  |
| `update_metadata_from_javbus.py`           | 当前按数据库资源列表批量补齐/更新元数据，支持预览和指定 AVID。                            |

## 其他活动入口

| 类型            | 入口与判断                                                                                                                                                                                                                                                                                |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Django 管理命令 | `backup_avid_list`、`backup_database`、`sync_backups`、`restore_postgres_backup` 用于备份/恢复；`check_actor_avatars_consistency`、`check_resources_consistency`、`check_videos_consistency`、`cleanup_logs` 用于定期校验/维护；`ensure_ollama_model` 被 Compose 和容器入口调用。均保留。 |
| 测试 Shell 脚本 | `tests/test_api.sh`、`test_full_task_queue.sh`、`test_mock_download.sh`、`test_progress_display.sh`、`test_websocket.sh` 为手动场景验证入口，不作为生产任务，保留。                                                                                                                       |
| 启动入口        | `docker-entrypoint.sh` 被后端镜像使用；`django_project/dev_commands.py` 的五个命令在 `pyproject.toml` 注册；`scripts/byparr/compose.yaml` 用于宿主机独立 Byparr。均保留。                                                                                                                 |
