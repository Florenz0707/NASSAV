# NASSAV Django Backend

基于 Django + Celery 构建的视频资源管理后端服务。

## 功能特性

- 🎬 **多源资源获取**：支持 8+ 视频源，自动按权重遍历获取
- 📥 **异步视频下载**：基于 Celery 的异步下载队列，支持 M3U8 流媒体
- 🔍 **元数据刮削**：从 JavBus 等站点获取详细元数据（发行日期、演员、类别等）
- 🔒 **分布式锁**：Redis 分布式锁确保下载任务串行执行
- 📁 **统一资源管理**：所有资源按 AVID 分目录存储

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 运行环境 |
| Django | 5.1+ | Web 框架 |
| Django REST Framework | 3.15+ | API 框架 |
| Celery | 5.4+ | 异步任务队列 |
| Redis | - | 消息队列 & 分布式锁 |
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
    cookie: YOUR_COOKIE_HERE  # 可选
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

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

#### 启动 Celery Worker（异步下载）

```bash
uv run celery -A django_project worker -l info
```

## API 文档

详细接口说明请参考 [interfaces.md](./interfaces.md)

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/source/list` | 获取可用下载源列表 |
| GET | `/api/resource/list` | 获取所有资源列表 |
| GET | `/api/resource/cover` | 获取封面图片 |
| POST | `/api/resource/new` | 添加新资源 |
| POST | `/api/resource/refresh` | 刷新资源元数据 |
| GET | `/api/downloads/list` | 获取已下载列表 |
| GET | `/api/downloads/metadata` | 获取下载元数据 |
| POST | `/api/downloads/new` | 提交下载任务 |

## 开发命令

```bash
# 运行开发服务器
uv run python manage.py runserver 0.0.0.0:8000

# 启动 Celery Worker
uv run celery -A django_project worker -l info

# 进入 Django Shell
uv run python manage.py shell

# 检查项目配置
uv run python manage.py check
```

## License

MIT License
