# Scripts 目录说明

本目录包含维护、数据重建和验证脚本；参数与用法按下文分类维护。历史一次性脚本处置通过 Git 追溯，当前验证边界见[部署与验证边界](../doc/compose-deployment.md#近期改动与验证边界)。

## 来源凭证维护

管理命令`create_source_credential_keyring`、`import_source_credentials`、`rotate_source_credentials`的用途、权限、默认预览、有界重加密和密钥备份要求见[凭证架构](../doc/source-credential-architecture.md#显式导入与轮换)。导入不覆盖新凭证，不改旧表；未知Cookie加密隔离。不要用这些命令自动开放多用户或切换正在运行的旧消费者。

## 任务下载停止与恢复探针

`probe_task_download_control.py` 只使用 ffmpeg 合成媒体及回环 HTTP，拒绝未知版本二进制和已存在的工作目录，不连接 Django/DB/Redis。运行参数为 `--binary <固定二进制绝对路径>` 和 `--workspace <不存在的目录>`；工作区保留日志、媒体和 report.json，退出码非零表示能力门槛失败。依赖 Linux `/proc`、ffmpeg、libx264 与固定 N_m3u8DL-RE。实验结束后可删除该新建工作区；不得指定正式资源目录。当前停止与续传边界见[任务控制架构](../doc/task-control-architecture.md#下载续传边界)。

## Byparr 会话复用 P0 探测

`probe_byparr_session.py` 在运行中的 Django 容器内使用有效配置，对单个已知页面执行只读对照；不写 Cookie 表。先阅读[部署与验证边界](../doc/compose-deployment.md#近期改动与验证边界)。参数为 `source`（`jable`/`missav`）、`kind`（`detail`/`listing`）、HTTPS 页面 URL；详情页还需 `--avid`。URL 必须属于已配置源域名且不带凭据；只允许 Jable 分页查询 `from=02`。可用 `--reuse-url` 指定同站另一详情页，MissAV 同时传 `--reuse-avid`，在同一次浏览器会话中测试跨页复用。默认不把存储或浏览器 Cookie 发送到目标站；完整会话对照必须在获准的试验窗口显式加 `--allow-session-replay`。只保存脚本输出的脱敏 JSON，不保存原始 Byparr 响应。

```bash
# 在与正式 Django 相同的容器、配置和代理路线内运行；先将脚本复制到容器临时目录
# docker cp django_backend/scripts/probe_byparr_session.py nassav-api-1:/tmp/probe_byparr_session.py
# docker exec -w /app nassav-api-1 python /tmp/probe_byparr_session.py jable detail https://jable.tv/videos/<verified-avid>/ --avid <VERIFIED-AVID>
```

一次调用只启动一次目标页浏览器获取，跨页参数仅增加直连验证；分别按两个时间窗口记录。MissAV 页面即使包含业务结构，若嵌入 `challenge-platform` 脚本，探测将分别报告 `validation=valid_embedded_marker` 和 `production_validation=challenge`，不能把前者当成当前生产路径成功。生产 Cookie 不应写入命令行或日志。试验结束清除容器中的临时脚本。

## MissAV P5 只读对照

`probe_p5_missav.py` 在正式 API 容器内用同一代理，从主页发现当前详情页；每个时段取至少 20 个有效详情页，比较无 Cookie 直连、已验证 Cookie+UA 直连，并用至少 5 个 Byparr 有效详情页作为耗时对照。参数：`--window W1|W2`、`--count 20..100`（默认 20）及必需的 `--allow-session-replay`。脚本输出脱敏 JSONL，不读取或写入 Cookie 表、Redis、任务队列；运行方式和结果见 [历史现场记录查询方式](#历史现场记录)。

## Byparr 固定版本部署

`byparr/compose.yaml` 将已验证的 `3.0.4` 镜像固定到 digest，监听宿主机
`127.0.0.1:8192`。Django 在同机宿主机运行时使用这个地址。当前试验记录见
[历史现场记录查询方式](#历史现场记录)。

```bash
cd django_backend/scripts/byparr
# 浏览器代理使用 django_backend/config/config.yaml 的 Proxy.Enable/url
docker compose config
docker compose up -d
docker compose logs --tail=100 byparr
docker compose down
```

`Proxy.url` 写宿主机可用的代理地址即可；Django 向 Byparr 发送请求时会把本机回环地址换为容器可用的 `host.docker.internal`，并单独传递代理认证。需确认代理允许来自容器的连接。只有独立调用 Byparr、且没有 Django 请求头时，才需要在未纳入 Git 的 `.env` 中设置 `BYPARR_PROXY_SERVER` 作为默认值。修改项目代理配置后重启 Django API 和 scrape worker。启动前检查 8192 端口是否已被占用；如有旧试验容器，先停止该试验容器再启动 Compose。

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

批量翻译资源标题；异步模式需启动 `uv run nassav-worker-default` 监听默认队列。

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
# 仓库未附带人工映射文件，需明确指定实际文件
uv run python scripts/import_jable_genre_mappings.py --input /path/to/jable_genre_manual_matches.yaml

# 仅预览
uv run python scripts/import_jable_genre_mappings.py --input /path/to/jable_genre_manual_matches.yaml --dry-run

```

**功能说明**:

- 读取用户通过 `--input` 提供的人工审核映射文件；仓库不附带默认 YAML
- 仅导入 `confidence in {"high", "medium"}` 的条目
- 通过 `update_or_create` 写入 `GenreSourceMapping(source_name="jable")`
- 自动跳过 `low` 置信度项和数据库中不存在的本地类别
- 自动清理 `jable_name` 中类似 `1234 部影片` 的尾部计数字样
- 这类写库脚本默认以 `--dry-run` 预览和日志核对作为主要验证方式，不额外维护脚本测试文件

#### check_recommendation_blacklist_filter.py

直接使用推荐 seed 黑名单召回 Jable 资源，并复用推荐过滤逻辑检测黑名单是否生效

```bash
# 检测前 20 个黑名单条目
uv run python scripts/check_recommendation_blacklist_filter.py

# 强制刷新 Jable 缓存，并输出详细日志
uv run python scripts/check_recommendation_blacklist_filter.py --force-refresh --verbose

# 多翻页并保存完整检测结果
uv run python scripts/check_recommendation_blacklist_filter.py --max-pages 2 --json-output /tmp/blacklist-check.json
```

**功能说明**:

- 读取 `RecommendationSeedProfile(is_blocked=true)` 中的 actor / genre 黑名单
- 对 Jable source slug 直接请求 model / tag / category 页面；genre slug 会同时尝试 `/tags/` 和 `/categories/`，用于验证两类标签差异
- 对只有名称、没有 source slug 的黑名单，回退到 Jable 搜索
- 对候选补充 Jable 详情页元数据后，复用推荐过滤逻辑检查是否被过滤
- 发现漏过滤候选时会输出 `LEAK` 日志，并以退出码 `1` 结束；全部过滤成功时退出码为 `0`

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

离线生成 OpenAPI；当前没有注册 Schema/Swagger HTTP 入口。默认脚本使用实例配置，输出 doc/openapi.yaml；无凭证生成临时文件优先使用：

```bash
DJANGO_SETTINGS_MODULE=django_project.refactoring_test_settings \
  uv run python manage.py spectacular --file /tmp/nassav-openapi.yaml
```

接口和固定快照的关系见[接口说明](../doc/interface.md)。

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

## Byparr 会话复用 P5 只读预筛

`probe_p5_jable.py` 在运行中的 API 容器内发现 Jable 当前详情页，只把浏览器 Cookie+UA 留在探针进程内存；种子必须经 3 秒同页直连验证。每窗口对 20 个不同详情页执行直连优先、必要时浏览器回退，并输出不含 Cookie、UA、代理和完整 URL 的 JSONL。执行前需确认脚本对应容器内代码版本与代理路线；显式 `--allow-session-replay` 才会发送浏览器会话。参数：`--window W1|W2`、`--count 20..100`（默认 20）、`--allow-session-replay`。脚本不写数据库或共享 Redis，不能代替 API/worker 并发和 24 小时灰度。现场结果与 NO-GO 判定见[历史现场记录查询方式](#历史现场记录)。

```bash
# 从仓库根目录执行；将 stdout 保存为脱敏证据，stderr 单独检查
# docker exec -i -e DJANGO_SETTINGS_MODULE=django_project.settings -w /app nassav-api-1 \
#   python - --window W1 --allow-session-replay \
#   < django_backend/scripts/probe_p5_jable.py > /tmp/nassav-p5-w1.jsonl
```

## MissAV 详情路径只读对照

`probe_missav_paths.py` 使用运行中 API 容器的 Byparr 和代理配置，对首页发现的不同番号交错比较 `/cn/{avid}`、发现路径及字幕候选。只有通过同站点、非挑战、标题番号和视频 UUID 校验才算有效。使用 `--resource-targets` 时仅从现有 `AVResource.source=MissAV` 行读取目标番号，并对比 `/en/{avid}`；不会修改资源、Cookie、Redis 或任务。输出 JSONL 仅含番号、路径类型、耗时和失败类型，不保存页面、Cookie、UA、代理或完整 URL。参数：`--count`（1..100，默认 20）、`--offset`（仅首页发现模式，默认 0）、`--subtitle-count`（默认 8）、`--root-count`（默认 0）、`--resource-targets`。正式站点实测应在 API 容器执行并将 stdout 单独保存；不要从宿主机改用另一条网络路线。结果见[历史现场记录查询方式](#历史现场记录)。

```bash
# 从仓库根目录执行；容器镜像通常不包含 scripts/，故仅复制到容器临时目录
docker exec nassav-api-1 mkdir -p /tmp/nassav-path-probe/scripts
docker cp django_backend/scripts/probe_p5_missav.py nassav-api-1:/tmp/nassav-path-probe/scripts/
docker cp django_backend/scripts/probe_missav_paths.py nassav-api-1:/tmp/nassav-path-probe/scripts/
docker exec -e PYTHONPATH=/tmp/nassav-path-probe:/app nassav-api-1 \
  python /tmp/nassav-path-probe/scripts/probe_missav_paths.py \
  --count 20 --subtitle-count 8 > /tmp/nassav-path-probe.jsonl
# 生产库已有目标：将参数换为 --resource-targets --count 20 --root-count 3
```

## Byparr blockMedia 隔离对照

`probe_byparr_media.py` 在 API 容器中对隔离 Byparr 实例做配对测量。参数：`--window W1|W2`、`--count 1..100`（默认 20）、`--base-url`（必须是具有 `/ready` 且报告 v3.0.4 的隔离计时实例）、`--samples-file`（第二窗口重用第一窗口 JSONL 中的番号清单）。奇偶样本交错默认/阻止媒体的顺序，第二窗口反转；默认有效而阻止媒体失败时停止。输出脱敏 JSONL，不读写 Cookie、Redis、任务或配置。`byparr/instrument_media_experiment.py` 仅在固定 Byparr 镜像中运行，调用上游原函数并返回阶段计时。结果与限制见[历史现场记录查询方式](#历史现场记录)。

```bash
# 创建仅本次实验使用的容器，与正式 API 使用同一网络；镜像固定
# 如网络名称不同，先核对实际网络名称再替换 nassav_internal
image='ghcr.io/thephaseless/byparr@sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6'
docker create --name nassav-byparr-media-experiment --network nassav_internal \
  --shm-size 512m --add-host host.docker.internal:host-gateway -e PYTHONPATH=/app \
  --entrypoint /app/.venv/bin/python "$image" /tmp/instrument_media_experiment.py
docker cp django_backend/scripts/byparr/instrument_media_experiment.py \
  nassav-byparr-media-experiment:/tmp/instrument_media_experiment.py
docker start nassav-byparr-media-experiment
# 在 API 临时目录准备探针和两个既有发现函数
# 三个文件分别是 probe_byparr_media.py、probe_p5_jable.py、probe_p5_missav.py
docker exec nassav-api-1 mkdir -p /tmp/nassav-media-probe/scripts
for script in probe_byparr_media.py probe_p5_jable.py probe_p5_missav.py; do
  docker cp "django_backend/scripts/$script" "nassav-api-1:/tmp/nassav-media-probe/scripts/$script"
done
docker exec -e PYTHONPATH=/tmp/nassav-media-probe:/app nassav-api-1 \
  python /tmp/nassav-media-probe/scripts/probe_byparr_media.py \
  --window W1 --count 20 --base-url http://nassav-byparr-media-experiment:8191 \
  > /tmp/nassav-media-w1.jsonl
# W2 将第一窗口结果复制到 API 临时目录，改为 --window W2 并加 --samples-file
# 验证完成后只清理本次临时容器和 /tmp/nassav-media-probe
```

等待 PoC 的候选容器使用相同镜像和包装器，额外设置 `BYPARR_EXPERIMENT_WAIT=business`，并把 `byparr/business_ready.py` 复制到 `/tmp/business_ready.py`。用 `--source Jable --count 10 --ready-base-url http://nassav-byparr-ready-experiment:8191` 做对照；此时两臂均为 `blockMedia=false`。候选保持原挑战求解，业务就绪时才读取新 HTML 快照，且由探针实际解析播放地址、番号、标题和封面。默认容器须报告 `waitMode=networkidle`，候选须报告 `waitMode=business`。只有阶段测量先确认等待瓶颈时才执行该 PoC；不能直接修改正式 Byparr。

## Byparr 第四步候选验收

`BYPARR_EXPERIMENT_WAIT=business_bounded` 是第三步等待 PoC 的隔离候选。与原 networkidle 同时启动最多 2 秒的业务内容检查；完整详情出现时提前返回，否则继续原等待，不重新计时或导航。候选容器需额外复制 `byparr/bounded_wait.py` 到 `/tmp/`。正式服务没有接入此模式。

冷请求：每窗口使用 `probe_byparr_media.py --source Jable --count 20 --ready-base-url <隔离候选地址>`，默认实例报告 networkidle，候选报告 business_bounded；W2 加 `--samples-file` 重用番号且反转配对顺序。两个窗口各检查不存在详情。暖请求：在同一 API 网络与配置代理路线中，用 `probe_p5_jable.py --window W1 --count 20 --allow-session-replay --browser-base-url <隔离候选地址>`；W2 重做同页种子验证并重新发现至少 20 个不同详情。Cookie+UA 只在探针进程内使用，不写数据库或共享缓存。完整解析须匹配请求番号、播放地址、标题和封面。所有请求含失败均计入暖 P95，输出包含 UTC 记录时间及前 10 页浏览器调用数。

`assess_byparr_acceptance.py --cold W1冷.jsonl W2冷.jsonl --warm W1暖.jsonl W2暖.jsonl` 离线核对两个窗口的 20 个不同有效详情、直连有效率至少 95%、零错误页误接纳、暖 P95 小于 5 秒且小于原 Byparr 中位数的 25%、前 10 页至多一次浏览器调用。退出 2 表示 NO-GO；通过预筛也仍需后续 API/worker、任务/下载/WebSocket 与 24 小时观察才能放行。数据和结论见[历史现场记录查询方式](#历史现场记录)。

`probe_byparr_runtime.py --phase serial|mixed --avids AVID ...` 只能在专用 `nassav-wait-postgres`、`nassav-wait-redis` 与 `/tmp/acceptance-resource` 环境中运行。创建样本资源，调用真实 Cookie/资源 API、Celery 刮削队列及 ASGI WebSocket；worker 分别设置 `-c 1`/`-c 2`，混合阶段另执行同步刷新。候选包装器的 `/experiment-stats` 只返回请求/错误/在途计数，不用于正式 API。Cookie 失败保留为失败，但独立任务检查继续执行。

评估器可加 `--runtime SERIAL.jsonl MIXED.jsonl`，将预筛、API/worker、媒体下载和回滚门槛分开报告；仅预筛通过时输出 PRE_SCREEN_PASS，运行阶段任何失败或缺项输出 NO_GO，全部通过才能 READY_FOR_OBSERVATION。这也不代表已完成 24 小时观察。本轮 Jable 自动 Cookie API 500 已阻止灰度，详细证据见第四步记录。

## 外部搜索隔离现场验收

`probe_external_search_runtime.py --fetch-pages 1` 验证 MissAV/Jable 演员、类别搜索、指定源任务提交及缓存。可用 `--source missav|jable --entity actor|genre` 缩小验证范围，`--keyword` 删除临时 MissAV 映射以验证名称搜索回退；`--fetch-pages` 仅允许 1 或 2。运行 `PYTHONPATH=/app python scripts/probe_external_search_runtime.py --fetch-pages 1`，宿主机使用 `uv run`。

探针强制数据库路径 `/tmp/nassav-external-search-acceptance.sqlite3` 和 Redis 主机 `nassav-external-search-test-redis`；仅在临时运行时迁移、创建测试实体/映射和登录用户，任务只进入临时队列。首个验收失败即退出 2。不得用于正式库。输出仅为状态、来源、条数与耗时，不输出 Cookie、UA、任务状态令牌。需已启用的 Byparr、同出口代理和两个下载源；日志目录写到 `/tmp/search-log`。

## probe_async_search_runtime.py

用法：`PYTHONPATH=/app python scripts/probe_async_search_runtime.py`。

- `--fetch-pages`：1–5，默认 1；大于 1 时要求在终态之前观察到 running 阶段结果。
- `--cases`：选取 `missav-genre`、`missav-actor`、`missav-keyword`、`jable-genre`、`jable-actor`，默认全部。
- 逐页链路验收：`PYTHONPATH=/app python scripts/probe_async_search_runtime.py --fetch-pages 2 --cases missav-genre jable-genre`。

另外输出首批结果耗时、观察到的阶段版本及 Redis 通知版本；通知必须覆盖已观察阶段和终态，且不含卡片和签名 token。脚本自身订阅 Channels Redis 群组，登录 WebSocket 的权限与透传由 `test_access_control.py` 验证。

仅允许 `DATABASE_PATH=/tmp/nassav-external-search-acceptance.sqlite3` 和 Redis 主机 `nassav-external-search-test-redis`。准备隔离配置，使用真实 Byparr 和源代理；运行目录必须可写入独立配置、日志与资源缓存。会创建临时用户、演员、类别及映射，并启动/关闭并发 1 的真实 Celery worker。默认使用单页抓取窗口，可通过参数调整；依次验证 MissAV 类别、演员、关键词和 Jable 类别、演员，输出计数、提交耗时、总耗时及图片字节数。验收完成后删除临时容器和存储。

## 持久任务恢复与真实 worker 验收

`recover_tasks` 管理命令使用与 worker 相同的恢复用例，参数和旧实例退出确认见[部署说明](../doc/compose-deployment.md#持久任务控制版本切换与回滚)。命令不是心跳超时清理器，身份未知保留现场。

`accept_task_control_workers.py` 生成 `/tmp/nassav-task-control-p7-*` 内的媒体、配置、DB 和资源，启动临时 loopback Redis、本地来源/图片/翻译 HTTP fixture 和真实 prefork Celery worker；API 命令经已授权的 DRF APIClient 执行，非 eager。要求 redis-server、ffmpeg/ffprobe、Pillow 及已校验的 P0 CLI；CLI 不打包进仓库。它会对自己创建的 worker 注入崩溃、Redis 断线、目录权限失败，结束时停止这些实例并删除临时目录，不触碰正式服务。

```bash
# 从 django_backend 执行；binary 必须匹配 P0 SHA。
uv run python scripts/accept_task_control_workers.py \
  --binary /tmp/nassav-task-control-p0/tools/N_m3u8DL-RE \
  --report /tmp/nassav-p7-sqlite-report.json
# PostgreSQL 必须是独立容器、空测试库 nassav_task_control，Unix socket 仅在 /tmp。
uv run python scripts/accept_task_control_workers.py \
  --binary /tmp/nassav-task-control-p0/tools/N_m3u8DL-RE \
  --postgres-socket /tmp/nassav-task-control-p1-pg \
  --report /tmp/nassav-p7-postgres-report.json
```

固定 SHA 为 `d2fa5b4b79f243320c509a85835327a520d8c160c600d99921e764bfc519fec7`。脚本不是线上探针；本地来源和翻译替身不代表 Jable/MissAV/JavBus/Ollama 已验收。当前部署复验步骤见[部署说明](../doc/compose-deployment.md#验证)。

## HLS 恢复校验超时验收

`uv run python scripts/accept_hls_validation_timeout.py` 只启动临时 loopback HTTP 服务及私有目录，使用真实 curl 注入首次部分响应超时，直接测试网络 fetch 的有界重试、随后本地缓存校验不增加请求，以及暂停优先级；恢复流程自身仅请求清单与密钥，不请求缓存分片。注入请求期限缩短为 0.25s，正常实现请求预算仍为 60s；输出 JSON，非通过退出非零。可以在后端镜像中只读挂载此后端目录后执行，容器使用 `--network none`、临时文件系统，Python 入口为 `/opt/venv/bin/python`，不会连接正式 DB/Redis、外站或真实资源卷。这是容器网络/校验回归，不是完整真实视频来源验收。

## Compose 后端运行目录权限

仓库根目录的 `scripts/prepare_backend_permissions.py` 是不连接 DB/Redis 的宿主机工具。`--data-dir`、`--resource-dir`、正整数 `--uid`、`--gid` 必填；默认只读检查，输出 JSON，需修复或不安全路径退出非零。`--repair --writers-stopped` 在确认所有写入者停止后准备目录/修复属主，需 chown 权限。`--include-published` 显式增加旧正式媒体的属主/owner 权限迁移；默认不遍历这些文件。它不删除缓存/锁、不取消任务、不迁移数据库，也不处理 Redis/Ollama 卷和 PostgreSQL 密码文件。链接目标须先人工核对并传真实路径；硬链接、符号链接与特殊文件拒绝。范围及首次部署、旧实例迁移见[部署说明](../doc/compose-deployment.md#后端运行身份与任务目录权限)。

推荐映射脚本不会由默认 Beat 或推荐 job 自动执行；部署者可显式运行上述脚本，或另行
配置 cron。Jable 与 JavBus 共用全局 `Proxy.Enable` / `Proxy.url`，不使用视频下载代理。

## 历史现场记录

早期 probe 的现场测量及 NO-GO 结论曾记录在 validation-status.md，该文件已由文档清理提交删除。需要复核上述历史实验时，从仓库根目录读取删除前版本，不用近期缓存/迁移的隔离结果代替来源实验：

```bash
git show cc6ab42^:django_backend/doc/validation-status.md
```

当前部署步骤与近期验证边界见[部署说明](../doc/compose-deployment.md#近期改动与验证边界)，代理出口约束见[代理路由](../doc/proxy-routing.md)。历史实验结果仅对记录中的时段、来源和出口有效。

## 个人数据导入

### 应用管理员与审计（0038–0039）

`bootstrap_app_admin --username <原操作者>`默认预览；新增角色不从Django标志推断。后续阶段具备运行接入条件、迁移及归属确认后，显式`--apply --request-id <UUID>`引导首个admin，已有可用admin时拒绝。`prune_audit_events --days 180 --limit 500 [--apply]`有界清理审计，默认预览；不清理持久幂等receipt。均从后端以`uv run python manage.py`运行，详见[账号策略](../doc/account-policy-architecture.md)。

### 旧资源持有导入（0037）

`uv run python manage.py import_resource_library --username <配置中的原操作者>`默认只读预览；显式加`--apply`才写入共享池与该账号持有。维护窗口先备份并停止资源写者，确认原操作者、规范番号冲突及已有池身份；重复运行保留已编辑关系，但已移出关系会重新导入。不修改资源/个人标记/文件/Cookie，访问范围先按原操作者私有标记，详见[共享池架构](../doc/resource-pool-architecture.md)。

`uv run python manage.py import_personal_data --username nassav [--settings-file config/user_settings.ini] [--apply]`：默认只读预览，明确原操作者后加 `--apply` 导入旧共享收藏/观看和只读INI。既有个人行不覆盖，0034移除导入标记后仅创建缺失行；人工删除行后再次导入可能恢复旧值，账号及取值错误不写入，具体维护窗口见[个人状态](../doc/personal-state-architecture.md)。

### 旧共享推荐归属导入

`uv run python manage.py import_recommendation_data --username <配置中的原操作者>`默认只预览；确认后加`--apply`。维护窗口先停止旧消费者、备份并迁移0035，在首次个人推荐前导入。只向该账号导入未归属历史、反馈关系、种子计数和黑名单，已有个人数据或活动job时拒绝合并，无残余旧行时重复执行为零操作。不改共享资源/缓存/文件，回退冲突见[推荐架构](../doc/recommendation-architecture.md#用户归属第三阶段)。

## 共享资源回收

`manage.py resource_gc`默认只读预览，写操作要求显式action、应用管理员actor、理由、对象版本与request_id，执行另需默认关闭的RESOURCE_GC_ENABLED。参数/安全边界见[回收架构](../doc/resource-gc-architecture.md#派发与管理)。旧check_resources/videos/actor_avatars_consistency在共享/范围版本布局拒绝执行，不绕过新日志修复文件。

### 保留个人资源黑名单的旧推荐补导入

从django_backend目录：`uv run python manage.py import_recommendation_data --username <原操作者> --preserve-personal-blocklist`先预览，再在维护窗口增加--apply。仅目标历史/种子为空、旧AVID黑名单为空且无目标活动job时可用；当前个人黑名单完全保留。不是通用合并开关；既有历史/种子、待合并旧黑名单及活动job仍拒绝。详见[推荐架构](../doc/recommendation-architecture.md#显式旧推荐安全补导入)及[目标迁移记录](../doc/postgres-multi-user-migration-20261015.md)。
