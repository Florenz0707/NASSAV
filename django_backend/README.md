# NASSAV Django Backend

基于 Django + Celery 构建的视频资源管理后端服务。

## 技术栈

- **Python** 3.12+
- **Django** 5.1+
- **Django REST Framework** 3.15+
- **Celery** 5.4+ (异步任务)
- **Redis** (消息队列)
- **curl_cffi** (HTTP 请求)

## 项目结构

```
django_backend/
├── manage.py                      # Django 管理脚本
├── pyproject.toml                 # 依赖配置
├── config/
│   ├── config.yaml               # 应用配置文件
│   └── template-config.yaml      # 配置模板
├── django_project/                # Django 项目配置
│   ├── __init__.py               # Celery 初始化
│   ├── settings.py               # Django 配置
│   ├── urls.py                   # 根路由
│   ├── celery.py                 # Celery 配置
│   └── wsgi.py                   # WSGI 入口
├── nassav/                        # Django 应用
│   ├── downloader/               # 下载器模块
│   │   ├── DownloaderBase.py    # 下载器基类
│   │   ├── MissAVDownloader.py  # MissAV 下载器
│   │   ├── JableDownloader.py   # Jable 下载器
│   │   ├── HohojDownloader.py   # Hohoj 下载器
│   │   ├── MemoDownloader.py    # Memo 下载器
│   │   ├── KanavDownloader.py   # Kanav 下载器
│   │   ├── AvtodayDownloader.py # Avtoday 下载器
│   │   ├── NetflavDownloader.py # Netflav 下载器
│   │   └── KissavDownloader.py  # Kissav 下载器
│   ├── scraper/                  # 刮削器模块
│   │   ├── AVDownloadInfo.py    # 下载信息数据类
│   │   ├── ScraperBase.py       # 刮削器基类
│   │   ├── ScraperManager.py    # 刮削器管理器
│   │   └── JavbusScraper.py     # JavBus 刮削器
│   ├── serializers.py            # 序列化器
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
│   ├── m3u8-Downloader-Go       # M3U8 下载工具
│   └── ffmpeg                   # 视频转换工具
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

### 3. 启动 Django 服务

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

### 4. 启动 Celery Worker (异步下载)

```bash
# 需要先启动 Redis 服务
uv run celery -A django_project worker -l info
```

## API 接口

所有接口前缀：`/nassav`

### 资源管理

| 方法   | 端点                             | 说明           |
|------|--------------------------------|--------------|
| GET  | `/api/resource/list`           | 获取所有资源列表     |
| GET  | `/api/resource/cover?avid=XXX` | 获取封面图片       |
| POST | `/api/resource/new`            | 添加新资源        |

### 下载管理

| 方法   | 端点                                          | 说明          |
|------|---------------------------------------------|-------------|
| GET  | `/api/resource/downloads/list`              | 获取已下载视频列表   |
| GET  | `/api/resource/downloads/metadata?avid=XXX` | 获取视频元数据     |
| POST | `/api/resource/downloads/new`               | 提交下载任务      |

## API 详细说明

### GET /nassav/api/resource/list

获取所有已保存资源的列表（从 resource 目录读取）。

**响应示例：**
```json
{
    "code": 200,
    "message": "success",
    "data": [
        {
            "avid": "SSIS-469",
            "title": "视频标题",
            "source": "Jable",
            "release_date": "2024-01-01",
            "has_video": true
        }
    ]
}
```

### GET /nassav/api/resource/cover

根据 avid 获取封面图片。

**参数：**
- `avid`: 视频编号 (必填)

**响应：** 图片文件 (image/jpeg)

### POST /nassav/api/resource/new

添加新资源，自动获取标题、下载封面、刮削元数据。

**请求体：**
```json
{
    "avid": "SSIS-469"
}
```

**响应示例：**
```json
{
    "code": 201,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "title": "视频标题",
        "source": "Jable",
        "cover_downloaded": true,
        "html_saved": true,
        "metadata_saved": true,
        "scraped": true
    }
}
```

### GET /nassav/api/resource/downloads/list

获取已下载的所有视频 avid 列表。

**响应示例：**
```json
{
    "code": 200,
    "message": "success",
    "data": ["SSIS-469", "SSIS-470"]
}
```

### GET /nassav/api/resource/downloads/metadata

获取已下载视频的元数据。

**参数：**
- `avid`: 视频编号 (必填)

**响应示例：**
```json
{
    "code": 200,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "title": "视频标题",
        "m3u8": "https://...",
        "source": "Jable",
        "release_date": "2024-01-01",
        "duration": "120分钟",
        "director": "导演名",
        "studio": "制作商",
        "actors": ["演员1", "演员2"],
        "genres": ["类别1", "类别2"],
        "file_size": 1234567890,
        "file_exists": true
    }
}
```

### POST /nassav/api/resource/downloads/new

提交视频下载任务（异步执行）。

**请求体：**
```json
{
    "avid": "SSIS-469"
}
```

**响应示例：**
```json
{
    "code": 202,
    "message": "下载任务已提交",
    "data": {
        "avid": "SSIS-469",
        "task_id": "abc123...",
        "status": "pending"
    }
}
```

## 配置说明

编辑 `config/config.yaml` 配置代理、下载源和刮削器：

```yaml
Proxy:
  Enable: true
  url: http://127.0.0.1:7077

# 刮削器配置（从 JavBus 获取详细元数据）
Scraper:
  javbus:
    domain: www.javbus.com
  busdmm:
    domain: www.busdmm.ink
  dmmsee:
    domain: www.dmmsee.bond

# 下载源配置（权重越高优先级越高）
Source:
  jable:
    domain: jable.tv
    weight: 800
    cookie: YOUR_COOKIE_HERE
  missav:
    domain: missav.ai
    weight: 200
  hohoj:
    domain: hohoj.tv
    weight: 700
  # ... 更多下载源
```

## 元数据结构

### AVDownloadInfo

| 字段           | 类型         | 说明       |
|--------------|------------|----------|
| avid         | str        | 视频编号     |
| title        | str        | 视频标题     |
| m3u8         | str        | M3U8 链接  |
| source       | str        | 下载来源     |
| release_date | str        | 发行日期     |
| duration     | str        | 时长       |
| director     | str        | 导演       |
| studio       | str        | 制作商      |
| label        | str        | 发行商      |
| series       | str        | 系列       |
| genres       | List[str]  | 类别列表     |
| actors       | List[str]  | 演员列表     |

## 架构设计

### 下载器模块 (Downloader)

```
DownloaderBase (基类)
├── MissAVDownloader
├── JableDownloader
├── HohojDownloader
├── MemoDownloader
├── KanavDownloader
├── AvtodayDownloader
├── NetflavDownloader
└── KissavDownloader

DownloaderManager (管理器)
└── 根据配置权重排序，遍历尝试获取资源
```

### 刮削器模块 (Scraper)

```
ScraperBase (基类)
├── JavbusScraper
├── BusdmmScraper
└── DmmseeScraper

ScraperManager (管理器)
└── 遍历刮削器获取详细元数据
```

## 依赖服务

- **Redis**: Celery 消息队列，默认连接 `redis://localhost:6379/0`
- **FFmpeg**: 视频格式转换，需要在 `tools/` 目录或系统 PATH 中
- **m3u8-Downloader-Go**: M3U8 下载工具，需要在 `tools/` 目录中

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
