# Scripts 目录说明

本目录包含各种维护和管理脚本。

## ⚠️ 重要字段变更说明

**AVResource 标题字段已重命名**（2024）:

| 旧字段名           | 新字段名           | 说明                            |
| ------------------ | ------------------ | ------------------------------- |
| `title`            | `original_title`   | Scraper 获取的原文标题（日语）  |
| `source_title`     | `source_title`     | Source 获取的备用标题（无变化） |
| `translated_title` | `translated_title` | 翻译后的标题（中文，无变化）    |

**影响范围**:

- ✅ `fix_avid_prefix_titles.py` - 已更新
- ✅ `batch_translate.py` - 已更新
- ✅ `update_metadata_from_javbus.py` - 已更新

**编写新脚本时请注意**:

- 使用 `resource.original_title` 而非 `resource.title`
- 查询条件应使用 `original_title__isnull` 而非 `title__isnull`

## 📋 脚本分类

### 🔧 常用维护脚本

#### batch_translate.py

批量翻译资源标题

```bash
# 翻译所有待翻译的资源
uv run python scripts/batch_translate.py

# 限制翻译数量
uv run python scripts/batch_translate.py --limit 10

# 同步模式（不使用 Celery）
uv run python scripts/batch_translate.py --sync

# 查看状态统计
uv run python scripts/batch_translate.py --status
```

#### update_metadata_from_javbus.py

从 Javbus 更新资源元数据

```bash
# 更新所有资源
uv run python scripts/update_metadata_from_javbus.py

# 只更新指定 AVID
uv run python scripts/update_metadata_from_javbus.py --avid ABC-123

# 预览模式
uv run python scripts/update_metadata_from_javbus.py --dry-run

# 强制更新所有字段
uv run python scripts/update_metadata_from_javbus.py --force
```

#### fix_avid_prefix_titles.py

修复以 AVID 开头的错误标题

```bash
# 列出问题资源
uv run python scripts/fix_avid_prefix_titles.py --list-only

# 预览修复
uv run python scripts/fix_avid_prefix_titles.py

# 实际执行修复
uv run python scripts/fix_avid_prefix_titles.py --execute
```

#### fix_actor_names.py

修复数据库中被截断的演员名称

```bash
# 显示统计信息
uv run python scripts/fix_actor_names.py --stats

# 预览模式（不实际修改）
uv run python scripts/fix_actor_names.py --dry-run

# 实际执行修复
uv run python scripts/fix_actor_names.py

# 只修复指定的 AVID
uv run python scripts/fix_actor_names.py --avid ABC-001

# 批量修复多个 AVID
uv run python scripts/fix_actor_names.py --avids ABC-001 DEF-002 GHI-003

# 限制处理数量
uv run python scripts/fix_actor_names.py --limit 10

# 详细输出模式
uv run python scripts/fix_actor_names.py --verbose
```

#### fix_durations.py

修复视频时长字段

```bash
# 预览模式
uv run python scripts/fix_durations.py --dry-run

# 实际执行修复
uv run python scripts/fix_durations.py --apply

# 限制处理数量
uv run python scripts/fix_durations.py --apply --limit 100
```

#### populate_media_fields.py

从磁盘文件填充媒体字段

```bash
# 预览模式
uv run python scripts/populate_media_fields.py

# 实际执行
uv run python scripts/populate_media_fields.py --apply

# 强制覆盖现有值
uv run python scripts/populate_media_fields.py --apply --force
```

#### cleanup_unused_genres.py

清理未使用的类别

```bash
# 查看统计信息
uv run python scripts/cleanup_unused_genres.py --stats

# 预览将要删除的类别
uv run python scripts/cleanup_unused_genres.py --dry-run

# 实际执行删除
uv run python scripts/cleanup_unused_genres.py --execute

# 导出类别列表
uv run python scripts/cleanup_unused_genres.py --dry-run --export unused_genres.json
```

**注意**: 删除操作不可逆，建议先备份数据库

#### backfill_actor_avatars.py

为现有演员批量获取头像

```bash
# 为所有演员获取头像
uv run python scripts/backfill_actor_avatars.py

# 限制处理数量（测试）
uv run python scripts/backfill_actor_avatars.py --limit 10

# 预览模式（不实际修改）
uv run python scripts/backfill_actor_avatars.py --dry-run

# 调整延迟时间
uv run python scripts/backfill_actor_avatars.py --delay 0.5

# 显示详细日志
uv run python scripts/backfill_actor_avatars.py --verbose
```

**功能说明**:

- 自动从Javbus获取演员头像URL
- 下载头像图片到 `resource/avatar/` 目录
- 按作品数倒序处理（优先处理热门演员）
- 支持断点续传（已有头像的演员自动跳过）

#### backfill_jable_actor_mappings.py

通过演员已有的 Jable 作品页，回填 `ActorSourceMapping` 中的 Jable 模型名和 slug

```bash
# 预览前 10 个演员
uv run python scripts/backfill_jable_actor_mappings.py --dry-run --limit 10

# 实际执行回填
uv run python scripts/backfill_jable_actor_mappings.py

# 开启详细日志
uv run python scripts/backfill_jable_actor_mappings.py --verbose --limit 20

# 冲突时跳过（on conflict do nothing）
uv run python scripts/backfill_jable_actor_mappings.py --skip-existing

# 允许仅凭单候选 fallback 回填
uv run python scripts/backfill_jable_actor_mappings.py --allow-single-fallback
```

**功能说明**:

- 默认只处理已有 Jable 作品、且尚未建立 Jable mapping 的演员
- 启动时会打印缺口概览，区分“可由本脚本处理”和“没有 Jable 作品因而无法处理”
- 从作品页 `.models a.model` 解析 `source_actor_name` 和 `source_actor_slug`
- 通过本地演员名及括号别名匹配正确的 Jable model
- 默认不会因为“页面上只有一个 model”就盲目落库；如确需这样做，可显式传 `--allow-single-fallback`
- 支持 dry-run 预览，不会修改数据库
- 支持 `--skip-existing`，当 slug 已绑定到其他演员时直接跳过

#### sync_recommendation_actor_mappings.py

基于推荐历史中的 `RecommendationItem`，离线同步 Jable 演员映射

```bash
# 同步最近 100 个推荐结果
uv run python scripts/sync_recommendation_actor_mappings.py

# 仅同步最近 20 个推荐结果
uv run python scripts/sync_recommendation_actor_mappings.py --limit 20

# 输出详细日志
uv run python scripts/sync_recommendation_actor_mappings.py --verbose
```

**功能说明**:

- 从最近的推荐结果中提取去重后的 Jable `avid`
- 对每个 `avid` 做 JavBus + Jable 双源对齐
- 自动补写缺失的 `ActorSourceMapping`
- 适合作为 cron / 定时任务执行，不阻塞推荐接口

#### export_jable_home_tags.py

抓取 Jable 首页中的标签和分类链接，并导出到本地临时 JSON 文件

```bash
# 使用默认临时文件输出
uv run python scripts/export_jable_home_tags.py

# 指定输出路径
uv run python scripts/export_jable_home_tags.py --output /tmp/jable-tags.json

# 查看详细日志
uv run python scripts/export_jable_home_tags.py --verbose
```

**功能说明**:

- 访问 `https://jable.tv/` 首页
- 解析首页中指向 `/tags/...` 和 `/categories/...` 的链接
- 将 `name`、`url`、`kind` 导出到 JSON 文件，默认路径为 `/tmp/nassav_jable_home_tags.json`

#### match_local_genres_to_jable_tags.py

读取本地 `Genre` 和已导出的 Jable 首页标签，生成类别到 Jable 标签的匹配建议

```bash
# 使用默认输入输出
uv run python scripts/match_local_genres_to_jable_tags.py

# 指定输入与输出
uv run python scripts/match_local_genres_to_jable_tags.py --input /tmp/jable-tags.json --output /tmp/jable-genre-matches.json

# 调整阈值和候选数
uv run python scripts/match_local_genres_to_jable_tags.py --min-score 0.72 --candidate-limit 3
```

**功能说明**:

- 从数据库读取当前资源库中的 `Genre`
- 读取 `export_jable_home_tags.py` 生成的标签 JSON
- 基于精确匹配、规范化匹配和字符串相似度，给出每个类别的最佳候选和备选列表
- 输出 JSON 默认路径为 `/tmp/nassav_jable_genre_tag_matches.json`

#### import_jable_genre_mappings.py

读取人工整理的 Jable 类别映射 YAML，并将 `high` / `medium` 置信度项写入 `GenreSourceMapping`

```bash
# 使用默认映射文件导入
uv run python scripts/import_jable_genre_mappings.py

# 仅预览
uv run python scripts/import_jable_genre_mappings.py --dry-run

# 指定输入文件
uv run python scripts/import_jable_genre_mappings.py --input doc/jable_genre_manual_matches.yaml
```

**功能说明**:

- 读取 `doc/jable_genre_manual_matches.yaml`
- 仅导入 `confidence in {"high", "medium"}` 的条目
- 通过 `update_or_create` 写入 `GenreSourceMapping(source_name="jable")`
- 自动跳过 `low` 置信度项和数据库中不存在的本地类别
- 自动清理 `jable_name` 中类似 `1234 部影片` 的尾部计数字样
- 这类写库脚本默认以 `--dry-run` 预览和日志核对作为主要验证方式，不额外维护脚本测试文件

#### fix_actor_avatars.py

检查并修复演员头像文件

```bash
# 只检查不修复（默认模式，安全）
uv run python scripts/fix_actor_avatars.py

# 或明确指定 dry-run
uv run python scripts/fix_actor_avatars.py --dry-run

# 实际执行修复和下载
uv run python scripts/fix_actor_avatars.py --fix

# 限制处理数量（测试用）
uv run python scripts/fix_actor_avatars.py --fix --limit 10

# 强制重新下载所有头像（即使文件已存在）
uv run python scripts/fix_actor_avatars.py --fix --force

# 组合使用：强制重新下载前 5 个演员的头像
uv run python scripts/fix_actor_avatars.py --fix --force --limit 5
```

**参数说明**:

- `--fix`: 实际执行修复操作（默认只检查不修复）
- `--dry-run`: 只检查不修复（默认模式，可省略）
- `--limit N`: 限制处理的演员数量，用于测试
- `--force`: 强制重新下载所有头像，即使文件已存在

**功能说明**:

- 检查所有演员的 `avatar_filename` 字段是否为空
- 如果为空但有 `avatar_url`，尝试下载头像
- 验证 `avatar_filename` 对应的文件是否实际存在
- 如果文件不存在，使用 `avatar_url` 重新下载
- 自动过滤占位符URL（nowprinting.gif）
- 使用配置的代理设置（如果启用）
- 提供详细的统计报告

**注意事项**:

- 默认 DRY-RUN 模式不会实际下载，只显示需要处理的项
- `--force` 参数会重新下载所有头像，请谨慎使用

### 🎨 资源处理脚本

#### generate_thumbnails.py

生成封面缩略图

```bash
# 生成所有尺寸的缩略图
uv run python scripts/generate_thumbnails.py

# 强制重新生成
uv run python scripts/generate_thumbnails.py --force

# 只生成特定尺寸
uv run python scripts/generate_thumbnails.py --sizes small,medium
```

**依赖**: `uv add pillow`

### 📚 文档生成脚本

#### generate_openapi.py

生成 OpenAPI 文档

```bash
# 生成 OpenAPI 文档
uv run python scripts/generate_openapi.py
```

输出文件: `doc/openapi.yaml`

## 🔍 使用注意事项

### 通用建议

1. **预览先行**: 大多数脚本支持 `--dry-run` 或预览模式，建议先预览
2. **备份数据**: 执行修改操作前建议备份数据库
3. **检查日志**: 注意查看脚本输出的日志信息
4. **限制数量**: 首次使用时可用 `--limit` 限制处理数量

### 环境要求

- Python 3.11+
- uv 包管理器
- Django 环境已配置
- Redis 服务运行中（Celery 任务需要）

### 依赖检查

```bash
# 检查必需的系统工具
ffprobe --version  # 用于 fix_durations.py
jq --version       # 用于测试脚本

# 安装 Python 依赖
uv sync
```

## 📝 编写新脚本的建议

1. **添加 shebang**: `#!/usr/bin/env python`
2. **详细的文档字符串**: 包括功能、用法、选项说明
3. **支持参数**: 使用 argparse 提供命令行选项
4. **预览模式**: 提供 `--dry-run` 选项
5. **进度提示**: 处理大量数据时显示进度
6. **错误处理**: 捕获并记录错误，不要让脚本崩溃
7. **日志输出**: 使用 logger 记录关键操作

## 🔗 相关文档

- [数据库架构](../doc/database.md)
- [API 接口文档](../doc/interface.md)
- [调试指南](../doc/debug.md)
- [B2 任务实现](../doc/b2_implementation.md)
