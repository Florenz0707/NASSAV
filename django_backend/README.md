# NASSAV Django Backend

基于 Django + Celery 构建的视频资源管理后端服务。

## 功能特性

- 🎬 **多源资源获取**：支持 8+ 视频源，自动按权重遍历获取
- 📥 **异步视频下载**：基于 Celery 的异步下载队列，支持 M3U8 流媒体
- 🔍 **元数据刮削**：从 JavBus 等站点获取详细元数据（发行日期、演员、类别等）
- 🔒 **智能去重机制**：多层去重检查（Redis 锁 + Celery 队列检查），确保同一 AVID 在队列中只出现一次
- 🚦 **全局下载锁**：确保同一时间只有一个下载任务执行，避免 N_m3u8DL-RE 多实例并发
- ⚡ **并发控制**：Celery Worker 配置为单并发，下载任务串行执行
- 📁 **统一资源管理**：所有资源按 AVID 分目录存储
- 🔌 **WebSocket 实时通知**：前端可实时接收任务队列状态和任务完成通知
- 📡 **Redis 消息支持**：基于 Redis 的消息队列和实时通信

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 运行环境 |
| Django | 5.1+ | Web 框架 |
| Django REST Framework | 3.15+ | API 框架 |
| Django Channels | 4.3+ | WebSocket 支持 |
| Celery | 5.4+ | 异步任务队列 |
| Redis | - | 消息队列 & 分布式锁 & Channel Layer |
| curl_cffi | - | HTTP 请求（绕过反爬） |
| N_m3u8DL-RE | - | M3U8 下载工具 |

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
│   ├── downloader/               # 下载器模块（8个下载源）
│   ├── scraper/                  # 刮削器模块
│   ├── services.py               # 服务层
│   ├── tasks.py                  # Celery 异步任务
│   ├── urls.py                   # API 路由
│   └── views.py                  # API 视图
├── resource/                      # 资源目录
│   └── {AVID}/                   # 按 AVID 分目录存储
│       ├── {AVID}.html          # HTML 源码缓存
│       ├── {AVID}.jpg           # 封面图片
│       ├── {AVID}.json          # 元数据
│       └── {AVID}.mp4           # 视频文件
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

详细接口说明请参考 [interfaces.md](./interfaces.md)

### REST API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/source/list` | 获取可用下载源列表 |
| POST | `/api/source/cookie` | 设置下载源cookie |
| GET | `/api/resource/list` | 获取所有资源列表 |
| GET | `/api/resource/cover` | 获取封面图片 |
| POST | `/api/resource` | 添加新资源 |
| POST | `/api/resource/refresh` | 刷新资源元数据 |
| GET | `/api/downloads/list` | 获取已下载列表 |
| GET | `/api/downloads/metadata` | 获取下载元数据 |
| POST | `/api/downloads` | 提交下载任务 |
| GET | `/api/tasks/queue/status` | 获取任务队列状态 |

### WebSocket 端点

| 端点 | 说明 |
|------|------|
| `ws://localhost:8000/ws/tasks/` | 实时任务队列通知 |

WebSocket 支持以下消息类型：
- `task_started`: 任务开始通知
- `task_completed`: 任务完成通知
- `task_failed`: 任务失败通知
- `queue_status`: 队列状态更新

详细使用说明请参考 [WEBSOCKET_GUIDE.md](./WEBSOCKET_GUIDE.md)

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
4. **串行执行**：确保同一时间只有一个下载任务在执行

### Celery 配置

```python
CELERY_WORKER_CONCURRENCY = 1          # 单并发
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

## License

MIT License
