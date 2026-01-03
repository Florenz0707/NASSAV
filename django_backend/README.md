# NASSAV Django Backend

基于 Django + Celery 构建的视频资源管理后端服务。

## 功能特性

### 核心功能
- 🎬 **多源资源获取**：支持 8+ 视频源，自动按权重遍历获取
- 📥 **异步视频下载**：基于 Celery 的异步下载队列，支持 M3U8 流媒体
- 📊 **实时进度追踪**：从 N_m3u8DL-RE 解析下载进度，支持 REST API 查询和 WebSocket 实时推送
- 🔍 **元数据刮削**：从 JavBus 等站点获取详细元数据（发行日期、演员、类别等）
- 🌐 **AI 智能翻译**：基于 Ollama 的日译中标题翻译，支持批量翻译和异步任务
- 🔒 **智能去重机制**：多层去重检查（Redis 锁 + Celery 队列检查），确保同一 AVID 在队列中只出现一次
- 🚦 **全局下载锁**：确保同一时间只有一个下载任务执行，避免 N_m3u8DL-RE 多实例并发
- ⚡ **并发控制**：Celery Worker 配置为单并发，下载任务串行执行
- 📁 **统一资源管理**：所有资源按 AVID 分目录存储（封面、视频分离）
- 🔌 **WebSocket 实时通知**：前端可实时接收任务状态、下载进度、完成通知
- 📡 **Redis 消息支持**：基于 Redis 的消息队列和实时通信

### 近期新增特性（2026-01）
- ✨ **细粒度刷新控制**：支持独立刷新 m3u8、元数据、翻译（3个开关互不干扰）
- 🎯 **批量操作接口**：支持批量添加、刷新、删除资源，批量提交下载任务
- 📑 **数据库全面迁移**：所有元数据从文件系统迁移至 SQLite，统一通过 ORM 访问
- 🏷️ **演员类别聚合**：新增演员列表、类别列表 API，支持按作品数排序和搜索
- 🖼️ **演员头像支持**：从 Javbus 自动获取演员头像，支持批量回填和 API 查询
- 📷 **封面优化策略**：优先使用 Javbus 封面（质量稳定），Source 封面作为回退方案
- 🖼️ **智能缩略图生成**：按需生成多尺寸封面（small/medium/large），支持 ETag 缓存
- 🔄 **条件请求优化**：元数据和封面接口支持 ETag/Last-Modified，减少带宽占用
- 🧹 **翻译质量提升**：添加翻译结果清洗机制（10+ 清洗规则），移除前缀、注释、格式标记
- 🗂️ **source_title 规范化**：统一 AVID 格式（大写 + 前缀），保证数据一致性
- 📝 **DisplayTitle 配置**：支持通过配置文件选择显示标题类型（source_title/translated_title/title）
- 🎛️ **Translator 配置系统**：支持多翻译器配置，可通过 config.yaml 激活不同模型
- 🧪 **完整测试覆盖**：新增翻译清洗、序列化器、API 端点等测试用例

## 技术栈

| 组件                    | 版本    | 说明                          |
|-----------------------|-------|-----------------------------|
| Python                | 3.12+ | 运行环境                        |
| Django                | 5.1+  | Web 框架                      |
| Django REST Framework | 3.15+ | API 框架                      |
| Django Channels       | 4.3+  | WebSocket 支持                |
| Celery                | 5.4+  | 异步任务队列                      |
| Redis                 | -     | 消息队列 & 分布式锁 & Channel Layer |
| curl_cffi             | -     | HTTP 请求（绕过反爬）               |
| N_m3u8DL-RE           | -     | M3U8 下载工具                   |
| Ollama                | -     | AI 翻译引擎（支持多模型）             |
| SQLite                | 3     | 元数据存储（通过 Django ORM）       |

## 项目结构

```
django_backend/
├── manage.py                      # Django 管理脚本
├── pyproject.toml                 # 依赖配置
├── config/
│   ├── config.yaml               # 应用配置文件
│   └── template-config.yaml      # 配置模板
├── django_project/                # Django 项目配置
│   ├── settings.py               # Django 配置
│   └── celery.py                 # Celery 配置
├── nassav/                        # Django 应用
│   ├── source/                   # 资源源管理（多源适配器）
│   ├── scraper/                  # 刮削器模块
│   ├── translator/               # 翻译器模块（Ollama + 多模型支持）
│   ├── m3u8downloader/          # M3U8 下载器封装
│   ├── models.py                 # 数据库模型（AVResource, Actor, Genre 等）
│   ├── serializers.py            # DRF 序列化器
│   ├── services.py               # 服务层
│   ├── tasks.py                  # Celery 异步任务（下载、翻译）
│   ├── urls.py                   # API 路由
│   └── views.py                  # API 视图
├── resource/                      # 资源目录（新布局）
│   ├── cover/                     # 封面图片，文件名格式为 {AVID}.jpg
│   │   └── {AVID}.jpg
│   ├── video/                     # 视频文件，文件名格式为 {AVID}.mp4
│   │   └── {AVID}.mp4
│   └── resource_backup/           # 旧的按 AVID 子目录备份（保留原始 HTML/JSON/MP4）
├── tools/                         # 工具目录
│   └── N_m3u8DL-RE              # M3U8 下载工具
└── log/                          # 日志目录
```

## 快速开始

### 1. 安装依赖

```bash
cd django_backend
uv sync
```

### 2. 配置文件

复制模板并编辑配置：

```bash
cp config/template-config.yaml config/config.yaml
```

配置示例：

```yaml
Proxy:
  Enable: true
  url: http://127.0.0.1:3000

UrlPrefix: null

# 显示标题配置（source_title/translated_title/title）
DisplayTitle: source_title

# 翻译器配置
Translator:
  active: ollama  # 激活的翻译器
  ollama:
    base_url: http://localhost:11434
    model: huihui_ai/hunyuan-mt-abliterated:latest
    temperature: 0.3
    timeout: 60

# 刮削器配置（从 JavBus 获取详细元数据）
Scraper:
  javbus:
    domain: www.javbus.com
  busdmm:
    domain: www.busdmm.ink

# 下载源配置（权重越高优先级越高）
Source:
  jable:
    domain: jable.tv
    weight: 1000
  missav:
    domain: missav.ai
    weight: 200
  # ... 更多下载源
```

### 3. 下载工具

下载 [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE/releases) 并放置到 `tools/` 目录：

```bash
mkdir -p tools
# 下载对应平台的 N_m3u8DL-RE 并放入 tools/ 目录
chmod +x tools/N_m3u8DL-RE  # Linux/macOS
```

### 4. 启动服务

#### 启动 Redis（必需）

```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# macOS
brew install redis
brew services start redis
```

#### 启动 Django 服务

**方式一：使用 ASGI 服务器（推荐，支持 WebSocket）**

```bash
# 使用 Uvicorn（推荐）
uv run uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --reload

# 或使用 Daphne
uv run daphne -b 0.0.0.0 -p 8000 django_project.asgi:application
```

**方式二：使用 Django 开发服务器（不支持 WebSocket）**

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

**注意**：如果要使用 WebSocket 实时通知功能，必须使用 ASGI 服务器（Uvicorn 或 Daphne）。

#### 启动 Celery Worker（异步下载）

```bash
# 标准启动（已配置单并发）
uv run celery -A django_project worker -l info

# 或手动指定并发数为 1
uv run celery -A django_project worker -l info --concurrency=1
```

**重要说明：**

- Worker 已配置为单并发模式（`CELERY_WORKER_CONCURRENCY=1`）
- 全局下载锁确保同一时间只有一个 N_m3u8DL-RE 实例在运行
- 任务去重机制防止同一 AVID 重复提交到队列

## API 文档

#### 源管理
| 方法   | 端点                     | 说明              |
|------|------------------------|-----------------|
| GET  | `/api/source/list`     | 获取可用下载源列表       |
| POST | `/api/source/cookie`   | 设置下载源 Cookie（手动/自动） |

#### 资源管理
| 方法     | 端点                              | 说明                                      |
|--------|----------------------------------|-------------------------------------------|
| GET    | `/api/resources/`                | 资源列表（搜索/筛选/分页/排序，支持演员/类别过滤）       |
| GET    | `/api/actors/`                   | 演员列表及作品数统计（支持分页/搜索/排序）             |
| GET    | `/api/genres/`                   | 类别列表及作品数统计（支持分页/搜索/排序）             |
| GET    | `/api/resource/{avid}/preview`   | 资源详情首屏预览（metadata + thumbnail_url）    |
| GET    | `/api/resource/metadata`         | 获取资源完整元数据（支持 ETag 条件请求）             |
| GET    | `/api/resource/cover`            | 获取封面/缩略图（支持多尺寸：small/medium/large） |
| POST   | `/api/resource`                  | 添加新资源                                   |
| POST   | `/api/resource/refresh/{avid}`   | 刷新资源（细粒度控制：m3u8/metadata/translate）  |
| DELETE | `/api/resource/{avid}`           | 删除资源及相关文件                               |

#### 批量操作
| 方法   | 端点                              | 说明                            |
|------|----------------------------------|---------------------------------|
| POST | `/api/resources/batch`           | 批量资源操作（add/refresh/delete） |
| POST | `/api/downloads/batch_submit`    | 批量提交下载任务                      |

#### 下载管理
| 方法     | 端点                        | 说明           |
|--------|---------------------------|--------------|
| GET    | `/api/downloads/abspath`  | 获取视频文件访问路径   |
| POST   | `/api/downloads/{avid}`   | 提交下载任务       |
| DELETE | `/api/downloads/{avid}`   | 删除已下载视频      |

#### 任务队列
| 方法  | 端点                         | 说明                         |
|-----|----------------------------|----------------------------|
**重要变更说明：**

1. **细粒度刷新控制**：`POST /api/resource/refresh/{avid}` 现在支持三个独立开关：
   - `refresh_m3u8`：是否刷新 m3u8 链接（默认 `true`）
   - `refresh_metadata`：是否刷新元数据（默认 `true`）
   - `retranslate`：是否重新翻译标题（默认 `false`）

2. **批量操作增强**：`POST /api/resources/batch` 支持对每个资源单独设置刷新参数

3. **缩略图优化**：封面接口支持按需生成多尺寸缩略图（`size=small|medium|large`），并提供 `ETag`/`Last-Modified` 支持条件请求

4. **已移除接口**：
   - `GET /api/resource/list`（已被 `/api/resources/` 取代）
   - `GET /api/downloads/list`（可用 `/api/resources/?status=downloaded` 替代）

5. **DisplayTitle 配置**：可在 `config.yaml` 中配置显示哪种标题（`source_title`/`translated_title`/`title`）

#### 调试接口（仅 DEBUG 模式）
| 方法   | 端点                          | 说明                  |
|------|------------------------------|----------------------|
| POST | `/api/downloads/mock/{avid}` | 模拟下载任务（测试用，可配置持续时间）务 |
| GET  | `/api/downloads/list`     | 获取已下载列表     |
| GET  | `/api/downloads/metadata` | 获取下载元数据     |
| POST | `/api/downloads`          | 提交下载任务      |
| GET  | `/api/tasks/queue/status` | 获取任务队列状态    |

### WebSocket 端点

| 端点                                     | 说明              |
|----------------------------------------|-----------------|
| `ws://localhost:8000/nassav/ws/tasks/` | 实时任务队列通知和下载进度推送 |

WebSocket 支持以下消息类型：

- `progress_update`: 下载进度实时更新（百分比、速度）
- `task_started`: 任务开始通知
- `task_completed`: 任务完成通知
- `task_failed`: 任务失败通知
- `queue_status`: 队列状态更新

注意：封面与缩略图现在支持按需生成与多尺寸返回（`size=small|medium|large`），并在响应中提供 `ETag` 与 `Last-Modified`，前端可使用 `If-None-Match` / `If-Modified-Since` 来减少带宽。

## 任务去重与并发控制

### 去重机制

系统采用多层去重策略，确保同一 AVID 在整个任务队列中只出现一次：

1. **Redis 任务锁**：提交任务时创建 `nassav:task_lock:{AVID}` 键
2. **Celery 队列检查**：检查 active、scheduled、reserved 三种状态的任务
3. **参数精确匹配**：通过任务名称和 AVID 参数精确识别重复任务

### 全局下载锁

为避免 N_m3u8DL-RE 多实例并发导致的资源竞争：

1. **获取锁**：任务执行前等待获取 `nassav:global_download_lock`
2. **智能等待**：最多等待 30 分钟，每 5 秒检查一次
3. **自动释放**：任务完成后自动释放锁，异常情况下 1 小时自动过期

# 运行测试
uv run pytest tests/

# 批量翻译脚本
uv run ./scripts/batch_translate.py --sync --dry-run  # 预览
uv run ./scripts/batch_translate.py --sync --execute  # 执行
uv run ./scripts/batch_translate.py --sync --force    # 强制重译

# 修复工具脚本
uv run ./scripts/fix_source_titles.py --stats         # 查看统计
uv run ./scripts/fix_source_titles.py --execute       # 修复 source_title 格式
uv run ./scripts/generate_thumbnails.py               # 生成缩略图
4. **串行执行**：确保同一时间只有一个下载任务在执行

### Celery 配置

```python
CELERY_WORKER_CONCURRENCY = 1  # 单并发
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # 每次只预取一个任务
```

## 开发命令

```bash
# 运行开发服务器
uv run python manage.py runserver 0.0.0.0:8000

# 启动 Celery Worker（单并发模式）
uv run celery -A django_project worker -l info

# 进入 Django Shell
uv run python manage.py shell

# 检查项目配置
uv run python manage.py check

# 查看 Celery 队列状态
uv run celery -A django_project inspect active
uv run celery -A django_project inspect scheduled
```

## 实时进度追踪

### 工作原理

系统通过以下方式实现下载进度的实时追踪：

1. **进度解析**：从 N_m3u8DL-RE 的标准输出实时解析进度信息（百分比、速度）
2. **Redis 存储**：将进度数据存储到 Redis，键名格式：`nassav:task_progress:{AVID}`
3. **WebSocket 推送**：每次进度更新时通过 Channel Layer 推送到所有连接的客户端
4. **REST API 查询**：通过 `GET /api/tasks/queue/status` 查询当前任务进度
5. **自动清理**：任务完成后自动删除进度数据，或 1 小时后自动过期

### 前端集成示例

#### WebSocket 实时订阅（推荐）

```javascript
const ws = new WebSocket('ws://localhost:8000/nassav/ws/tasks/');

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);

    switch (message.type) {
        case 'progress_update':
            // 实时进度更新
            const {avid, percent, speed} = message.data;
            console.log(`${avid}: ${percent}% @ ${speed}`);
            updateProgressBar(avid, percent);
            break;

        case 'task_completed':
            // 下载完成
            console.log(`Task ${message.data.avid} completed`);
            break;

        case 'queue_status':
            // 队列状态更新
            updateQueueDisplay(message.data);
            break;
    }
};
```

#### REST API 轮询（备选）

```javascript
// 定期查询任务状态（包含进度信息）
setInterval(async () => {
    const response = await fetch('/nassav/api/tasks/queue/status');
    const {data} = await response.json();

    data.active_tasks.forEach(task => {
        if (task.progress) {
            console.log(`${task.avid}: ${task.progress.percent}%`);
            updateProgressBar(task.avid, task.progress.percent);
        }
    });
}, 数据库架构

项目使用 SQLite 数据库存储所有元数据，主要模型包括：

- **AVResource**：视频资源主表，包含 AVID、标题、源信息、翻译状态等
- **Actor**：演员信息表
- **Genre**：类别信息表
- **AVResource_actors**：资源-演员多对多关系表
- **AVResource_genres**：资源-类别多对多关系表

详细字段说明和表结构请参考 [doc/database.md](doc/database.md)。

## 翻译系统

### 工作流程

1. **异步翻译任务**：通过 Celery 异步执行翻译任务，避免阻塞主线程
2. **状态机管理**：`translation_status` 字段记录翻译状态（pending/translating/completed/failed/skipped）
3. **结果清洗**：翻译结果经过 10+ 规则清洗，移除前缀、注释、格式标记等
4. **批量处理**：支持批量翻译脚本，可按条件筛选需要翻译的资源

### 翻译规则清洗

系统实现了以下清洗规则：

1. 移除翻译前缀（"翻译结果："、"标题："、"译文："等）
2. 移除引号包裹
3. 移除 Markdown 加粗标记（`**text**`）
4. 移除中文括号注释（`（注：...）`）
5. 移除英文括号注释（`(Note: ...)`）
6. 移除翻译说明段落
7. 移除尾部解释性文本
8. 过滤带编号的解释列表
9. 移除多余空行
10. 修剪首尾空白

### 配置示例

```yaml
Translator:
  active: ollama
  ollama:
    base_url: http://localhost:11434
    model: huihui_ai/hunyuan-mt-abliterated:latest
    temperature: 0.3
    timeout: 60
```

## 性能优化

- **条件请求**：元数据和封面接口支持 `ETag`/`Last-Modified`，返回 304 节省带宽
- **智能缓存**：封面缩略图按需生成并持久化，避免重复计算
- **数据库索引**：关键字段（avid, translation_status, file_exists）已添加索引
- **串行下载**：全局下载锁确保资源合理利用，避免并发冲突
- **Redis 缓存**：任务进度、队列状态等实时数据存储于 Redis

## 故障排查

### 常见问题

1. **翻译失败**：检查 Ollama 服务是否运行，模型是否已下载
2. **下载卡住**：检查全局下载锁状态，必要时手动删除 Redis 中的 `nassav:global_download_lock` 键
3. **任务重复**：系统已实现多层去重，若仍出现重复可检查 Redis 任务锁
4. **WebSocket 断连**：确保使用 ASGI 服务器（Uvicorn/Daphne），Django 开发服务器不支持 WebSocket

### 调试命令

```bash
# 检查 Redis 连接
redis-cli ping

# 查看所有任务锁
redis-cli keys "nassav:task_lock:*"

# 查看全局下载锁
redis-cli get nassav:global_download_lock

# 查看任务进度
redis-cli keys "nassav:task_progress:*"

# 清除所有锁（谨慎使用）
redis-cli del nassav:global_download_lock
redis-cli keys "nassav:task_lock:*" | xargs redis-cli del
```

## 更新日志

### v1.3.0 (2026-01-03)

**新功能：**
- 🖼️ **Javbus 女优头像集成**：自动从 Javbus 获取女优头像并保存，支持通过 `/api/actors/:id/avatar` API 访问
- 📷 **封面获取策略优化**：优先使用 Javbus 封面（质量更稳定），403 错误时自动回退到 Source 封面
- ⚙️ **用户设置 API**：新增 `/api/setting` 端点（GET/PUT），支持前端配置持久化到 `user_settings.ini`

**Bug 修复：**
- 🐛 修复后端女优头像处理逻辑错误，确保头像正确保存和返回
- 🐛 修复 Javbus 女优名解析问题：正确处理带括号的女优名（如"めぐり（藤浦めぐ）"）
- 🐛 修复女优列表筛选功能：添加 `has_avatar` 查询参数支持按头像状态筛选
- 🐛 修复视频时间排序接口返回未下载资源的问题：`sort_by=video_create_time` 时自动过滤未下载视频

**改进：**
- 🔍 女优名解析增强：改进正则表达式以支持复杂括号内容
- 🎯 封面下载鲁棒性：添加 HTTP 403 错误处理和自动重试机制
- 📊 API 增强：女优列表接口支持更多筛选条件

### v1.2.0 (2026-01-02)

**重大更新：**
- ✨ 添加 AI 翻译系统（Ollama + 多模型支持）
- 🗄️ 完成数据库全面迁移（文件系统 → SQLite）
- 🎯 实现细粒度刷新控制（m3u8/metadata/translate 独立开关）
- 📑 新增批量操作接口（batch add/refresh/delete）
- 🏷️ 添加演员/类别聚合统计接口
- 🖼️ 实现智能缩略图生成（多尺寸 + 按需生成）
- 🔄 优化条件请求支持（ETag/Last-Modified）

**改进：**
- 翻译质量提升：10+ 清洗规则移除杂质
- source_title 格式规范化：统一 AVID 大写格式
- 配置系统增强：DisplayTitle、Translator.active 配置
- API 简化：移除冗余接口，统一响应格式
- 测试覆盖：新增翻译、序列化器、API 测试用例

**废弃：**
- ❌ `GET /api/resource/list`（已被 `/api/resources/` 取代）
- ❌ `GET /api/downloads/list`（可用 `/api/resources/?status=downloaded` 替代）
- ❌ `html_saved` 字段（HTML 不再持久化）

## License

MIT License
