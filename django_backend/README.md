# NASSAV Django Backend

基于 Django + Celery 构建的视频资源管理后端服务。

## 技术栈

- **Python** 3.12+
- **Django** 5.1+
- **Django REST Framework** 3.15+
- **Celery** 5.4+ (异步任务)
- **Redis** (消息队列)
- **SQLite** (数据库)

## 项目结构

```
django_backend/
├── manage.py                      # Django 管理脚本
├── pyproject.toml                 # 依赖配置
├── db.sqlite3                     # SQLite 数据库
├── config/
│   └── config.yaml               # 应用配置文件
├── django_project/                # Django 项目配置
│   ├── __init__.py               # Celery 初始化
│   ├── settings.py               # Django 配置
│   ├── urls.py                   # 根路由
│   ├── celery.py                 # Celery 配置
│   └── wsgi.py                   # WSGI 入口
├── nassav/                        # Django 应用
│   ├── models.py                 # 数据模型
│   ├── serializers.py            # 序列化器
│   ├── services.py               # 服务层
│   ├── tasks.py                  # Celery 异步任务
│   ├── urls.py                   # API 路由
│   └── views.py                  # API 视图
├── resource/
│   ├── cover/                    # 封面图片目录
│   └── video/                    # 视频文件目录
└── log/                          # 日志目录
```

## 快速开始

### 1. 安装依赖

```bash
cd django_backend
uv sync
```

### 2. 数据库迁移

```bash
uv run python manage.py migrate
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

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/resource/list` | 获取所有资源列表 |
| GET | `/api/resource/cover?avid=XXX` | 获取封面图片 |
| POST | `/api/resource/new` | 添加新资源 |

### 下载管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/resource/downloads/list` | 获取已下载视频列表 |
| GET | `/api/resource/downloads/metadata?avid=XXX` | 获取视频元数据 |
| POST | `/api/resource/downloads/new` | 提交下载任务 |

## API 详细说明

### GET /nassav/api/resource/list

获取数据库中所有资源的 avid 和 title。

**响应示例：**
```json
{
    "code": 0,
    "message": "success",
    "data": [
        {"avid": "SSIS-469", "title": "视频标题"}
    ]
}
```

### GET /nassav/api/resource/cover

根据 avid 获取封面图片。

**参数：**
- `avid`: 视频编号 (必填)

**响应：** 图片文件 (image/jpeg)

### POST /nassav/api/resource/new

添加新资源，自动获取标题并下载封面。

**请求体：**
```json
{
    "avid": "SSIS-469"
}
```

**响应示例：**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "title": "视频标题",
        "source": "MissAV",
        "cover_downloaded": true
    }
}
```

### GET /nassav/api/resource/downloads/list

获取已下载的所有视频 avid 列表。

**响应示例：**
```json
{
    "code": 0,
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
    "code": 0,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "title": "视频标题",
        "m3u8": "https://...",
        "source": "MissAV",
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
    "code": 0,
    "message": "下载任务已提交",
    "data": {
        "avid": "SSIS-469",
        "task_id": "abc123...",
        "status": "pending"
    }
}
```

## 配置说明

编辑 `config/config.yaml` 配置代理和下载源：

```yaml
Proxy:
  Enable: true
  url: http://127.0.0.1:7077

Source:
  missav:
    domain: missav.ai
    weight: 1000
  jable:
    domain: jable.tv
    weight: 800
```

## 数据模型

### AVInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| id | AutoField | 主键 |
| avid | CharField | 视频编号 (唯一) |
| title | CharField | 视频标题 |
| source | CharField | 来源 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

## 依赖服务

- **Redis**: Celery 消息队列，默认连接 `redis://localhost:6379/0`
- **FFmpeg**: 视频格式转换，需要在 `tools/` 目录或系统 PATH 中
- **m3u8-Downloader-Go**: M3U8 下载工具，需要在 `tools/` 目录中

## 开发命令

```bash
# 创建超级用户
uv run python manage.py createsuperuser

# 进入 Django Shell
uv run python manage.py shell

# 检查项目配置
uv run python manage.py check
```

## License

MIT License
