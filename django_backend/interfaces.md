# API 接口文档

所有接口前缀：`/nassav`

## 统一响应格式

所有接口返回统一的 JSON 格式：

```json
{
    "code": 200,
    "message": "success",
    "data": "..."
}
```

| 字段      | 类型     | 说明               |
|---------|--------|------------------|
| code    | int    | 状态码              |
| message | string | 状态消息             |
| data    | any    | 响应数据，错误时为 `null` |

---

## 下载源管理

### GET /nassav/api/source/list

获取所有可用的下载源名称列表。

**响应示例：**

```json
{
    "code": 200,
    "message": "success",
    "data": ["Jable", "MissAV", "Hohoj", "Memo", "Kanav", "Avtoday", "Netflav", "Kissav"]
}
```

---

### POST /nassav/api/source/cookie

设置指定源的 Cookie（持久化到数据库）。

**请求体：**

```json
{
    "source": "jable",
    "cookie": "kt_tcookie=1; PHPSESSID=xxx; kt_member=xxx"
}
```

| 参数     | 类型     | 必填 | 说明           |
|--------|--------|----|--------------|
| source | string | 是  | 源名称（不区分大小写） |
| cookie | string | 是  | Cookie 字符串   |

**成功响应 (200)：**

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "source": "jable",
        "cookie_set": true
    }
}
```

**源不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "源 xxx 不存在",
    "data": {
        "available_sources": ["Jable", "MissAV", "Hohoj"]
    }
}
```

---

## 资源管理

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

**data 字段说明：**

| 字段           | 类型      | 说明      |
|--------------|---------|---------|
| avid         | string  | 视频编号    |
| title        | string  | 视频标题    |
| source       | string  | 下载来源    |
| release_date | string  | 发行日期    |
| has_video    | boolean | 是否已下载视频 |

---

### GET /nassav/api/resource/metadata

获取已下载视频的元数据。

**查询参数：**

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**成功响应：**

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
        "label": "发行商",
        "series": "系列名",
        "actors": ["演员1", "演员2"],
        "genres": ["类别1", "类别2"],
        "file_size": 1234567890,
        "file_exists": true
    }
}
```

---

### GET /nassav/api/resource/cover

根据 avid 获取封面图片。

**查询参数：**

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**成功响应：** 图片文件 (image/jpeg)

**错误响应：**

```json
{
    "code": 404,
    "message": "封面 SSIS-469 不存在",
    "data": null
}
```

---

### POST /nassav/api/resource

添加新资源，自动获取标题、下载封面、刮削元数据。

**请求体：**

```json
{
    "avid": "SSIS-469",
    "source": "jable"
}
```

| 参数     | 类型     | 必填 | 默认值   | 说明                  |
|--------|--------|----|-------|---------------------|
| avid   | string | 是  | -     | 视频编号                |
| source | string | 否  | "any" | 指定下载源，"any" 表示遍历所有源 |

**成功响应 (201)：**

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

**资源已存在响应 (409)：**

```json
{
    "code": 409,
    "message": "资源已存在",
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

**源不存在响应 (400)：**

```json
{
    "code": 400,
    "message": "源 xxx 不存在",
    "data": {
        "available_sources": ["Jable", "MissAV", "Hohoj"]
    }
}
```

**获取失败响应 (404)：**

```json
{
    "code": 404,
    "message": "无法从任何源获取 SSIS-469 的信息",
    "data": null
}
```

---

### POST /nassav/api/resource/refresh/{avid}

刷新已有资源的元数据和 m3u8 链接，使用原有 source 获取。

**路径参数：**

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**成功响应 (200)：**

```json
{
    "code": 200,
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

**资源不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "SSIS-469 的资源不存在，请先调用 /api/resource/new 添加资源",
    "data": null
}
```

**刷新失败响应 (502)：**

```json
{
    "code": 502,
    "message": "从 Jable 刷新 SSIS-469 失败",
    "data": null
}
```

---

### DELETE /nassav/api/resource/{avid}

删除整个资源目录（包括 HTML、封面、元数据、视频）。

**路径参数：**

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**成功响应 (200)：**

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "deleted_files": ["SSIS-469.html", "SSIS-469.jpg", "SSIS-469.json", "SSIS-469.mp4"]
    }
}
```

**资源不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "资源 SSIS-469 不存在",
    "data": null
}
```

---

## 下载管理

### GET /nassav/api/downloads/list

获取已下载的所有视频 avid 列表。

**响应示例：**

```json
{
    "code": 200,
    "message": "success",
    "data": ["SSIS-469", "SSIS-470", "PRED-388"]
}
```

---

**资源不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "资源 SSIS-469 的元数据不存在",
    "data": null
}
```

---

### POST /nassav/api/downloads

提交视频下载任务（异步执行）。需要先调用 `POST /api/resource` 添加资源。
**任务去重机制：**
- 同一 AVID 在整个任务队列中只会出现一次
- 检查范围包括：正在执行、等待执行、已预取的任务
- 使用 Redis 锁和 Celery 队列双重检查

**全局下载锁：**
- 同一时间只有一个下载任务在执行 N_m3u8DL-RE
- 其他任务会在队列中等待（最多等待 30 分钟）
- 确保下载工具不会出现多实例并发
**请求体：**

```json
{
    "avid": "SSIS-469"
}
```

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**任务提交成功响应 (202)：**

```json
{
    "code": 202,
    "message": "下载任务已提交",
    "data": {
        "avid": "SSIS-469",
        "task_id": "abc123-def456-...",
        "status": "pending",
        "file_size": null
    }
}
```

**视频已下载响应 (409)：**

```json
{
    "code": 409,
    "message": "视频已下载",
    "data": {
        "avid": "SSIS-469",
        "task_id": null,
        "status": "completed",
        "file_size": 1234567890
    }
}
```

**任务已存在响应 (409)：**

```json
{
    "code": 409,
    "message": "下载任务已存在",
    "data": null
}
```

说明：当同一 AVID 的下载任务已经在队列中（正在执行或等待执行）时返回此响应。

**元数据不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "SSIS-469 的元数据不存在，请先调用 /api/resource/new 添加资源",
    "data": null
}
```

---

### DELETE /nassav/api/downloads/{avid}

删除已下载的视频文件（只删除 mp4 文件，保留元数据）。

**路径参数：**

| 参数   | 类型     | 必填 | 说明   |
|------|--------|----|------|
| avid | string | 是  | 视频编号 |

**成功响应 (200)：**

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "avid": "SSIS-469",
        "deleted_file": "SSIS-469.mp4",
        "file_size": 1234567890
    }
}
```

**视频不存在响应 (404)：**

```json
{
    "code": 404,
    "message": "视频 SSIS-469 不存在",
    "data": null
}
```

---

## 元数据结构

### AVDownloadInfo

资源元数据 JSON 文件 (`{AVID}.json`) 结构：

| 字段           | 类型       | 说明        |
|--------------|----------|-----------|
| avid         | string   | 视频编号      |
| title        | string   | 视频标题      |
| m3u8         | string   | M3U8 播放链接 |
| source       | string   | 下载来源      |
| release_date | string   | 发行日期      |
| duration     | string   | 时长        |
| director     | string   | 导演        |
| studio       | string   | 制作商       |
| label        | string   | 发行商       |
| series       | string   | 系列        |
| genres       | string[] | 类别列表      |
| actors       | string[] | 演员列表      |

---

## 状态码说明

| 状态码 | 说明               |
|-----|------------------|
| 200 | 请求成功             |
| 201 | 创建成功             |
| 202 | 任务已接受（异步处理）      |
| 400 | 请求参数错误           |
| 404 | 资源不存在            |
| 409 | 资源已存在/冲突         |
| 500 | 服务器内部错误          |
| 502 | 上游服务错误（如下载源无法访问） |
